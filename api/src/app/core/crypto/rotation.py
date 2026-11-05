"""Rotación de la KEK de OpenBao y recorte de versiones viejas (S5-B2; S5-D19, S5-D55a, S5-D185).

- `rotate_kek(provider)`: `provider.rotate("apex-kek")`; devuelve la versión nueva.
- `rewrap_all`: `CryptoJob(kind="rewrap", data_class=None)` (reanudable) sobre las filas `openbao`
  `encrypt|index` cuya envoltura no está en la última versión; por fila `unwrap` + `wrap` (NUNCA
  `provider.rewrap`, S5-D55a: `transit/rewrap` no conserva el AAD), `parse_version(nuevo) ==
  latest_version`, `unwrap` del nuevo y `compare_digest` antes del `UPDATE` (motor de `migration`).
- `trim_ready`: todas las filas `openbao` en la última versión Y el último job `rewrap` en `done`.
- `trim_kek(provider)`: sube `min_decryption_version` a la última (`keys/apex-kek/config`) y
  devuelve ese valor. Nunca `transit/keys/.../trim` (irreversible). Solo un proveedor que sepa
  fijar la versión mínima (`_Trimmable`, hoy `OpenBaoProvider`) lo admite; el local falla cerrado.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select

from app.core.crypto.errors import CryptoError
from app.core.crypto.migration import (
    PURPOSES,
    MigrationResult,
    Reenvoltura,
    SessionFactory,
    abrir_job,
    recorrer_llaves,
)
from app.core.crypto.models import CryptoJob, CryptoKey
from app.core.crypto.openbao_provider import KEK_KEY
from app.core.crypto.openbao_wire import parse_version
from app.core.crypto.provider import KeyProvider, ProviderResolver
from app.core.crypto.service import rotation_lock

PROVIDER: str = "openbao"
KEK_LOCK_CLASS: str = "kek"
"""Clase del candado `apex:rotate:kek` (S5-D188)."""


class TrimNotReady(Exception):
    """Entre la comprobación y el recorte cambió la KEK o una fila: no se recorta (S5-D188)."""


@runtime_checkable
class _Trimmable(Protocol):
    async def set_min_decryption_version(self, key_ref: str, version: int) -> None: ...


async def rotate_kek(provider: KeyProvider) -> int:
    return (await provider.rotate(KEK_KEY)).version


async def _filas_openbao(session_factory: SessionFactory) -> list[tuple[UUID, int]]:
    """`(id, versión de la envoltura)` de las filas `openbao`, en el orden del plan."""
    consulta = (
        select(CryptoKey.id, CryptoKey.wrapped_material)
        .where(CryptoKey.provider == PROVIDER, CryptoKey.purpose.in_(PURPOSES))
        .order_by(CryptoKey.data_class, CryptoKey.purpose, CryptoKey.version)
    )
    async with session_factory() as session:
        filas = (await session.execute(consulta)).all()
    return [(id_, parse_version(bytes(material))) for id_, material in filas]


async def _ultima_version(resolver: ProviderResolver) -> int:
    return (await resolver(PROVIDER).key_info(KEK_KEY)).version


async def rotate_or_resume(session_factory: SessionFactory, *, resolver: ProviderResolver) -> int:
    """Rota la KEK salvo que una rotación anterior haya quedado a medias (filas viejas): reanudar
    no rota otra vez. Devuelve la versión vigente."""
    ultima = await _ultima_version(resolver)
    if any(version < ultima for _, version in await _filas_openbao(session_factory)):
        return ultima
    return await rotate_kek(resolver(PROVIDER))


async def rewrap_all(
    session_factory: SessionFactory, *, resolver: ProviderResolver, actor: UUID
) -> MigrationResult:
    openbao = resolver(PROVIDER)
    ultima = await _ultima_version(resolver)
    pendientes = [i for i, version in await _filas_openbao(session_factory) if version < ultima]

    def aplicable(fila: CryptoKey) -> bool:
        return fila.provider == PROVIDER and parse_version(bytes(fila.wrapped_material)) < ultima

    job = await abrir_job(session_factory, "rewrap", len(pendientes), actor)
    reenvoltura = Reenvoltura(openbao, openbao, aplicable, version_esperada=ultima)
    return await recorrer_llaves(session_factory, job, pendientes, reenvoltura, actor=actor)


async def _ultimo_rewrap(session_factory: SessionFactory) -> CryptoJob | None:
    consulta = (
        select(CryptoJob)
        .where(CryptoJob.kind == "rewrap")
        .order_by(CryptoJob.created_at.desc())
        .limit(1)
    )
    async with session_factory() as session:
        return (await session.execute(consulta)).scalar()


async def trim_ready_version(
    session_factory: SessionFactory, *, resolver: ProviderResolver
) -> int | None:
    """La versión que se puede recortar (la última, con todas las filas `openbao` en ella y el
    último job `rewrap` en `done`) o `None` (S5-D188)."""
    ultimo = await _ultimo_rewrap(session_factory)
    if ultimo is None or ultimo.status != "done":
        return None
    ultima = await _ultima_version(resolver)
    filas = await _filas_openbao(session_factory)
    return ultima if all(version == ultima for _, version in filas) else None


async def trim_ready(session_factory: SessionFactory, *, resolver: ProviderResolver) -> bool:
    return await trim_ready_version(session_factory, resolver=resolver) is not None


async def ultimo_rewrap_terminado(session_factory: SessionFactory) -> datetime | None:
    """`finished_at` del último job `rewrap` en `done` (el respaldo debe ser posterior)."""
    ultimo = await _ultimo_rewrap(session_factory)
    return ultimo.finished_at if ultimo is not None and ultimo.status == "done" else None


async def trim_kek(provider: KeyProvider, version: int | None = None) -> int:
    """Sube `min_decryption_version` a `version` (por omisión la última). Sin comprobar nada más:
    el camino con comprobación es `trim_kek_checked`."""
    if not isinstance(provider, _Trimmable):
        raise CryptoError("unsupported", "este proveedor de llaves no recorta versiones")
    if version is None:
        version = (await provider.key_info(KEK_KEY)).version
    await provider.set_min_decryption_version(KEK_KEY, version)
    return version


@asynccontextmanager
async def kek_lock(session_factory: SessionFactory) -> AsyncIterator[None]:
    """Candado `apex:rotate:kek` en una conexión dedicada; `RotationInProgress` si está tomado."""
    async with session_factory() as session, rotation_lock(session, KEK_LOCK_CLASS):
        yield


async def trim_kek_checked(
    session_factory: SessionFactory, *, resolver: ProviderResolver, version: int
) -> int:
    """Recorta a `version` repitiendo la comprobación bajo el candado de la KEK (S5-D188): todas
    las filas `openbao` en `version`, el último `rewrap` en `done` y la última versión de Transit
    igual a `version`; si algo cambió desde que se validó, `TrimNotReady` y `config` no se llama."""
    async with kek_lock(session_factory):
        if await trim_ready_version(session_factory, resolver=resolver) != version:
            raise TrimNotReady("la KEK o las envolturas cambiaron desde la comprobación")
        return await trim_kek(resolver(PROVIDER), version)
