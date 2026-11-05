"""Apoyo de S5-B2 (Rojo B2): migración de proveedor, rotación de la KEK de OpenBao y retiro de la
KEK local (S5-D18, D19, D55a, D73, D131).

- `Entorno`: la fábrica de sesiones de `rotacion_lista`, el proveedor `local` real, un
  `OpenBaoProvider` sobre `FakeTransit` y los resolvers de prueba.
- `migracion_lista`: `Entorno` listo (llaves `local` creadas por `ensure_keys`).
- `sembrada`: `migracion_lista` + 30 personas con `document` cifrado + las DEK en claro.
- `ProveedorEspia`: envuelve un proveedor, anota los argumentos de `wrap` (el objeto mismo y una
  copia) y puede fallar en la n-ésima llamada a `wrap`.
- `TransitCorrupto` y `TransitVersionVieja`: `FakeTransit` defectuosos.
- `migrar_a_mano`, `rewrapear_a_mano`: dejan la base en el estado posterior sin pasar por el código
  bajo prueba (cada prueba mide una sola cosa).
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select, text

from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoJob, CryptoKey
from app.core.crypto.openbao_provider import OpenBaoProvider
from app.core.crypto.openbao_wire import parse_version
from app.core.crypto.provider import KeyInfo, KeyProvider, ProviderResolver, ProviderStatus
from tests.crypto._rotacion import LLAVE_RETIRO, Fabrica, filas_rotacion
from tests.factories.backup import make_backup_dir
from tests.factories.fake_transit import ADDR_FAKE, TOKEN_FAKE, FakeTransit

ACTOR = UUID(int=7)
KEK_REF = "apex-kek"
PROPOSITOS = ("encrypt", "index")


@dataclass
class Entorno:
    fabrica: Fabrica
    local: LocalFileProvider
    openbao: Any
    transit: FakeTransit
    token_file: Path

    def resolver(self, **cambios: KeyProvider) -> ProviderResolver:
        proveedores: dict[str, Any] = {"local": self.local, "openbao": self.openbao, **cambios}

        def resolver(nombre: str) -> KeyProvider:
            if nombre not in proveedores:
                raise CryptoError("kek_missing", f"sin proveedor {nombre} en esta prueba")
            return proveedores[nombre]  # type: ignore[no-any-return]

        return resolver

    def resolver_sin_local(self) -> ProviderResolver:
        abierto = self.openbao

        def resolver(nombre: str) -> KeyProvider:
            if nombre != "openbao":
                raise CryptoError("kek_missing", "la KEK local ya no existe")
            return abierto  # type: ignore[no-any-return]

        return resolver

    def con_transit(self, transit: FakeTransit) -> Entorno:
        """El mismo entorno con OTRO Transit (defectuoso): las envolturas se hacen con ese."""
        abierto = OpenBaoProvider(
            ADDR_FAKE, self.token_file, timeout_s=2.0, client=transit.cliente()
        )
        return replace(self, openbao=abierto, transit=transit)


@pytest.fixture
def migracion_lista(
    rotacion_lista: Fabrica, proveedor_local: LocalFileProvider, tmp_path: Path
) -> Entorno:
    carpeta = tmp_path / "openbao-token"
    carpeta.mkdir()
    token = carpeta / "token"
    token.write_text(TOKEN_FAKE + "\n", encoding="utf-8")
    token.chmod(0o600)
    transit = FakeTransit()
    abierto = OpenBaoProvider(ADDR_FAKE, token, timeout_s=2.0, client=transit.cliente())
    return Entorno(rotacion_lista, proveedor_local, abierto, transit, token)


@dataclass
class Sembrada:
    entorno: Entorno
    ids: list[UUID]
    blobs: dict[UUID, str]
    deks: dict[UUID, bytes]


@pytest.fixture
async def sembrada(migracion_lista: Entorno) -> AsyncIterator[Sembrada]:
    async with migracion_lista.fabrica() as sesion:
        ids = await filas_rotacion(sesion, 30)
        blobs = {
            i: b
            for i, b in (
                await sesion.execute(
                    text("SELECT id, document FROM test_crypto.crypto_test_person")
                )
            ).all()
        }
    yield Sembrada(migracion_lista, ids, blobs, await deks_de(migracion_lista))


# Lectura ---------------------------------------------------------------------------------------


async def filas_de_llaves(fabrica: Fabrica) -> list[CryptoKey]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(
            select(CryptoKey).order_by(CryptoKey.data_class, CryptoKey.purpose, CryptoKey.version)
        )
        return list(filas)


async def llaves_envueltas(fabrica: Fabrica) -> list[CryptoKey]:
    """Las filas `encrypt|index` en el orden del plan `(data_class, purpose, version)`."""
    return [f for f in await filas_de_llaves(fabrica) if f.purpose in PROPOSITOS]


async def deks_de(entorno: Entorno) -> dict[UUID, bytes]:
    """La DEK en claro de cada fila `encrypt|index`, abierta con el proveedor de su fila."""
    resolver = entorno.resolver()
    return {
        f.id: await resolver(f.provider).unwrap(f.wrapped_material)
        for f in await llaves_envueltas(entorno.fabrica)
    }


async def instantanea(fabrica: Fabrica) -> list[tuple[UUID, str, bytes, datetime]]:
    return [
        (f.id, f.provider, bytes(f.wrapped_material), f.updated_at)
        for f in await filas_de_llaves(fabrica)
    ]


async def jobs_de(fabrica: Fabrica, kind: str) -> list[CryptoJob]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(
            select(CryptoJob).where(CryptoJob.kind == kind).order_by(CryptoJob.created_at)
        )
        return list(filas)


async def todos_los_jobs(fabrica: Fabrica) -> int:
    async with fabrica() as sesion:
        return int(await sesion.scalar(text("SELECT count(*) FROM crypto.crypto_jobs")) or 0)


async def version_de_envoltura(fila: CryptoKey) -> int:
    return parse_version(bytes(fila.wrapped_material))


# Escritura directa (estado previo) -------------------------------------------------------------


async def _actualizar(fabrica: Fabrica, id_: UUID, provider: str, material: bytes) -> None:
    async with fabrica() as sesion, sesion.begin():
        await sesion.execute(
            text(
                "UPDATE crypto.crypto_keys SET wrapped_material = :m, provider = :p WHERE id = :i"
            ),
            {"m": material, "p": provider, "i": id_},
        )


async def migrar_a_mano(entorno: Entorno, desde: str = "local", hacia: str = "openbao") -> None:
    """Re-envuelve a mano cada fila `encrypt|index` de `desde` con `hacia` (sin el código nuevo)."""
    resolver = entorno.resolver()
    for fila in await llaves_envueltas(entorno.fabrica):
        if fila.provider != desde:
            continue
        dek = await resolver(desde).unwrap(fila.wrapped_material)
        await _actualizar(entorno.fabrica, fila.id, hacia, await resolver(hacia).wrap(dek))


async def rewrapear_a_mano(entorno: Entorno, *, terminado: datetime | None = None) -> None:
    """unwrap + wrap de cada fila `openbao` con la última versión; con `terminado`, deja además un
    job `rewrap` en `done` que acabó en ese instante."""
    resolver = entorno.resolver()
    filas = [f for f in await llaves_envueltas(entorno.fabrica) if f.provider == "openbao"]
    for fila in filas:
        dek = await entorno.openbao.unwrap(fila.wrapped_material)
        await _actualizar(entorno.fabrica, fila.id, "openbao", await resolver("openbao").wrap(dek))
    if terminado is not None:
        with actor_scope(SYSTEM_USER_ID):
            async with entorno.fabrica() as sesion, sesion.begin():
                sesion.add(
                    CryptoJob(
                        kind="rewrap",
                        data_class=None,
                        status="done",
                        total=len(filas),
                        done=len(filas),
                        started_at=terminado,
                        finished_at=terminado,
                        created_by=SYSTEM_USER_ID,
                    )
                )


async def volver_a_envoltura(entorno: Entorno, id_: UUID, material: bytes) -> None:
    await _actualizar(entorno.fabrica, id_, "openbao", material)


# Proveedores defectuosos -----------------------------------------------------------------------


class ProveedorEspia:
    """Proveedor que delega en `interno`, anota los argumentos de `wrap` y falla en la llamada
    número `fallar_wrap_en` (1 = la primera) con `CryptoUnavailable("unreachable")`."""

    def __init__(
        self,
        interno: KeyProvider,
        *,
        fallar_wrap_en: int | None = None,
        mensaje: str | None = None,
    ) -> None:
        self._interno = interno
        self.mensaje = mensaje
        self.name = interno.name
        self.fallar_wrap_en = fallar_wrap_en
        self.wrap_args: list[Any] = []
        self.instantaneas: list[bytes] = []

    async def wrap(self, dek: bytes) -> bytes:
        self.wrap_args.append(dek)
        self.instantaneas.append(bytes(dek))
        if self.fallar_wrap_en == len(self.wrap_args):
            raise CryptoUnavailable("unreachable", self.mensaje)
        return await self._interno.wrap(dek)

    async def unwrap(self, wrapped: bytes) -> bytes:
        return await self._interno.unwrap(wrapped)

    async def sign(self, key_ref: str, data: bytes) -> bytes:
        return await self._interno.sign(key_ref, data)

    async def verify(self, key_ref: str, data: bytes, signature: bytes) -> bool:
        return await self._interno.verify(key_ref, data, signature)

    async def rotate(self, key_ref: str) -> KeyInfo:
        return await self._interno.rotate(key_ref)

    async def key_info(self, key_ref: str) -> KeyInfo:
        return await self._interno.key_info(key_ref)

    async def status(self) -> ProviderStatus:
        return await self._interno.status()

    async def rewrap(self, wrapped: bytes) -> bytes:
        return await self._interno.rewrap(wrapped)


class TransitCorrupto(FakeTransit):
    """`decrypt` devuelve un texto claro con un bit cambiado: la comparación debe fallar."""

    def _descifrar(self, nombre: str, cuerpo: Any) -> httpx.Response:
        respuesta = super()._descifrar(nombre, cuerpo)
        if respuesta.status_code != 200:
            return respuesta
        claro = bytearray(base64.b64decode(json.loads(respuesta.content)["data"]["plaintext"]))
        claro[0] ^= 1
        enc = base64.b64encode(bytes(claro)).decode("ascii")
        return httpx.Response(200, json={"data": {"plaintext": enc}})


class TransitVersionVieja(FakeTransit):
    """`encrypt` envuelve con la versión anterior a la última (cuando hay más de una)."""

    def _cifrar(self, nombre: str, cuerpo: Any) -> httpx.Response:
        version = max(1, self.latest_version(nombre) - 1)
        return httpx.Response(
            200, json={"data": {"ciphertext": self._sellar(nombre, version, cuerpo)}}
        )


# Manifiestos -----------------------------------------------------------------------------------


def manifiesto_con_snapshot(
    carpeta: Path,
    *,
    antiguedad: timedelta = timedelta(hours=5),
    snapshot: bool = True,
    snapshot_verified: bool = True,
    tamper: str | None = None,
    verify: str = "ok",
) -> Path:
    """`latest.json` firmado con `LLAVE_RETIRO`; `created_at = ahora - antiguedad` (`reloj`)."""
    ahora = current_clock().now_utc()
    juego = make_backup_dir(
        carpeta,
        ahora,
        verify=verify,
        created_at=ahora - antiguedad,
        sign=LLAVE_RETIRO,
        snapshot=snapshot,
        snapshot_verified=snapshot_verified,
        tamper=tamper,
    )
    return juego.latest
