"""Migración de proveedor de llaves y motor común de re-envoltura (S5-B2; S5-D18, D55a, D183).

Contrato (`tests/crypto/test_migrate_provider.py`, `test_rotate_kek.py`):
- `plan_provider_migration(rows, from_)`: ids de las filas `encrypt|index` con `provider == from_`,
  en cualquier `state` (también `retired`, S5-D18), ordenadas por `(data_class, purpose, version)`.
  Las filas `sign` NO entran (S5-D183): guardan una referencia (`local:sign-ed25519` o el nombre de
  la llave Transit), no material envuelto con la KEK (S5-D9); su cambio de proveedor es de EP-17.
- `migrate_provider` abre un `CryptoJob(kind="migrate_provider", data_class=None)` o reanuda el
  `failed` del mismo tipo y, por llave y en su propia transacción: `FOR UPDATE`, `unwrap` con el
  origen, `wrap` con el destino (el MISMO `bytearray` de la DEK), `unwrap` del nuevo,
  `hmac.compare_digest` y solo entonces `UPDATE wrapped_material, provider`; `crypto_ops` `unwrap`
  y `wrap` con `batch_id == job.id`; la DEK queda en ceros en `finally`, también si `wrap` falla.
- Un fallo del proveedor NO se propaga: el job queda `failed` con un código (`^[a-z_]+$`, nunca
  texto del servidor) y el resultado trae `failed_key_id`. Otro job abierto (`pending`/`running`,
  de cualquier clase) lanza `MigrationInProgress` sin tocar nada. `dry_run` no escribe ni llama.
- S5-D189: la red no corre bajo candado de fila: se lee la fila sin candado, se hace
  `unwrap`/`wrap`/`unwrap` y una transacción corta con `FOR UPDATE` escribe solo si la fila sigue
  igual (si cambió se salta y se reevalúa en la corrida siguiente). Un job `running` del mismo tipo
  se reanuda como el `failed`; una base ocupada deja el job `failed` con el código `busy`; toda
  otra excepción (también las que no son `Exception`) lo deja `failed` y se relanza.
- S5-D190: un job `rotate|reencrypt` abierto de cualquier clase impide migrar y re-envolver (y
  `service.start_rotation` rechaza si hay uno de estos), porque ambos cambian el mismo material.
- `verify_provider` cuenta las filas `encrypt|index` fuera de `expected` (solo lectura): comprueba
  la UBICACIÓN, no que cada envoltura abra.
- La auditoría (`audit.audit_log`) la escribe el `cli_ops`, no este módulo.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import current_clock
from app.core.context import actor_scope, batch_scope
from app.core.crypto import oplog
from app.core.crypto.errors import CryptoError
from app.core.crypto.models import CryptoJob, CryptoKey
from app.core.crypto.openbao_wire import parse_version
from app.core.crypto.provider import KeyProvider, ProviderResolver
from app.core.db import DatabaseBusy, translate_busy

SessionFactory = async_sessionmaker[AsyncSession]

PURPOSES: Final = ("encrypt", "index")
"""Propósitos con DEK envuelta por la KEK; `sign` guarda una referencia (S5-D183)."""
OPEN_STATES: Final = ("pending", "running")
RESUMABLE_STATES: Final = ("pending", "running", "failed")
ROTATION_KINDS: Final = ("rotate", "reencrypt")
"""Jobs de rotación de llaves de datos: no conviven con una migración ni con un rewrap (S5-D190)."""
MAX_ERROR: Final = 100


class MigrationInProgress(Exception):
    """Hay otro job de `crypto_jobs` abierto: no se inicia una migración (S5-D18)."""


@dataclass(frozen=True, slots=True)
class KeyRowView:
    """Lo que el plan necesita de una fila de `crypto_keys` (sin material)."""

    id: UUID
    purpose: str
    data_class: str
    version: int
    state: str
    provider: str


@dataclass(frozen=True, slots=True)
class MigrationResult:
    total: int
    done: int
    skipped: int
    failed_key_id: UUID | None = None
    job_id: UUID | None = field(default=None, compare=False)
    """Id del job (la auditoría del CLI lo usa como `record_id`); fuera de la igualdad."""
    error: str | None = field(default=None, compare=False)
    """Código del fallo (`^[a-z_]+$`, p. ej. `busy`); nunca texto del proveedor."""


@dataclass(frozen=True, slots=True)
class JobHandle:
    id: UUID
    total: int
    done: int


@dataclass(frozen=True)
class Reenvoltura:
    """Qué hacer con cada fila: abrirla con `origen`, cerrarla con `destino`.

    `aplicable` se evalúa bajo `FOR UPDATE`: si otro proceso ya la dejó lista, se salta.
    `version_esperada` (re-envoltura de OpenBao) exige que la envoltura nueva sea de esa versión.
    """

    origen: KeyProvider
    destino: KeyProvider
    aplicable: Callable[[CryptoKey], bool]
    version_esperada: int | None = None


def plan_provider_migration(rows: Sequence[KeyRowView], from_: str) -> tuple[UUID, ...]:
    elegidas = [f for f in rows if f.provider == from_ and f.purpose in PURPOSES]
    elegidas.sort(key=lambda f: (f.data_class, f.purpose, f.version))
    return tuple(f.id for f in elegidas)


async def listar_filas(session_factory: SessionFactory) -> list[KeyRowView]:
    consulta = select(
        CryptoKey.id,
        CryptoKey.purpose,
        CryptoKey.data_class,
        CryptoKey.version,
        CryptoKey.state,
        CryptoKey.provider,
    )
    async with session_factory() as session:
        return [KeyRowView(*fila) for fila in (await session.execute(consulta)).all()]


# Jobs ------------------------------------------------------------------------------------------


async def abrir_job(
    session_factory: SessionFactory, kind: str, pendientes: int, actor: UUID
) -> JobHandle:
    """Reanuda el job `failed` del mismo tipo o abre uno nuevo; otro abierto lo impide."""
    try:
        with actor_scope(actor):
            async with session_factory() as session, session.begin():
                return await _abrir(session, kind, pendientes, actor)
    except IntegrityError:
        raise MigrationInProgress("hay otro job de llaves en curso") from None


async def _abrir(session: AsyncSession, kind: str, pendientes: int, actor: UUID) -> JobHandle:
    conflicto = await session.scalar(
        select(CryptoJob.id)
        .where(
            or_(
                and_(CryptoJob.status.in_(OPEN_STATES), CryptoJob.kind != kind),
                and_(CryptoJob.kind.in_(ROTATION_KINDS), CryptoJob.status.in_(RESUMABLE_STATES)),
            )
        )
        .limit(1)
    )
    if conflicto is not None:
        raise MigrationInProgress("hay otro job de llaves en curso")
    previo = (
        await session.execute(
            select(CryptoJob)
            .where(CryptoJob.kind == kind, CryptoJob.status.in_(RESUMABLE_STATES))
            .order_by(CryptoJob.created_at.desc())
            .limit(1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar()
    if previo is None:
        job = CryptoJob(
            kind=kind,
            data_class=None,
            status="running",
            total=pendientes,
            done=0,
            started_at=current_clock().now_utc(),
            created_by=actor,
        )
        session.add(job)
    else:
        job = previo
        job.status, job.error, job.finished_at = "running", None, None
        job.total = max(job.total, job.done + pendientes)
    await session.flush()
    return JobHandle(job.id, job.total, job.done)


async def cerrar_job(session_factory: SessionFactory, job_id: UUID, *, error: str | None) -> None:
    """`done` (con `done = total`) o `failed` con un código; en su propia transacción."""
    consulta = (
        select(CryptoJob)
        .where(CryptoJob.id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    async with session_factory() as session, session.begin():
        job = (await session.execute(consulta)).scalar_one()
        job.finished_at = current_clock().now_utc()
        if error is None:
            job.status, job.done, job.error = "done", job.total, None
        else:
            job.status, job.error = "failed", error[:MAX_ERROR]


# Una llave -------------------------------------------------------------------------------------


def _poner_en_ceros(buffer: bytearray) -> None:
    buffer[:] = bytes(len(buffer))


async def _envolver_verificado(fila: CryptoKey, r: Reenvoltura) -> bytes:
    """`unwrap` con el origen, `wrap` con el destino y comprobación de la envoltura nueva.

    La DEK viaja como el mismo `bytearray` y queda en ceros aunque algo falle. Los `bytes` que
    devuelve un proveedor no se pueden borrar: es el límite de la interfaz.
    """
    dek, comprobada = bytearray(), bytearray()
    try:
        dek.extend(await r.origen.unwrap(bytes(fila.wrapped_material)))
        nuevo = await r.destino.wrap(dek)
        if r.version_esperada is not None and parse_version(nuevo) != r.version_esperada:
            raise CryptoError("unwrap_failed", "la envoltura nueva no es de la última versión")
        comprobada.extend(await r.destino.unwrap(nuevo))
        if not hmac.compare_digest(dek, comprobada):
            raise CryptoError("unwrap_failed", "la DEK verificada no coincide con la original")
        return nuevo
    finally:
        _poner_en_ceros(dek)
        _poner_en_ceros(comprobada)


async def _una_llave(
    session_factory: SessionFactory, key_id: UUID, job_id: UUID, actor: UUID, r: Reenvoltura
) -> bool:
    """Re-envuelve una llave sin sostener ningún candado mientras se habla con el proveedor
    (S5-D189): lectura sin candado, `unwrap`/`wrap`/`unwrap`, y una transacción corta con
    `FOR UPDATE` que solo escribe si la fila sigue igual. `True` si la escribió; `False` si ya
    estaba lista o cambió entretanto (se reevalúa en la corrida siguiente)."""
    with actor_scope(actor), batch_scope(job_id):
        async with session_factory() as lectura:
            fila = (await lectura.execute(_consulta(key_id))).scalar_one()
        nuevo = await _envolver_verificado(fila, r) if r.aplicable(fila) else None
        viejo = (fila.provider, bytes(fila.wrapped_material))
        async with session_factory() as session, session.begin():
            actual = (await session.execute(_consulta(key_id).with_for_update())).scalar_one()
            escribir = (
                nuevo is not None and (actual.provider, bytes(actual.wrapped_material)) == viejo
            )
            if escribir and nuevo is not None:
                for verbo in ("unwrap", "wrap"):
                    oplog.record(
                        verbo,
                        data_class=actual.data_class,
                        key_id=actual.id,
                        key_version=actual.version,
                    )
                actual.wrapped_material, actual.provider = nuevo, r.destino.name
            await session.execute(
                update(CryptoJob).where(CryptoJob.id == job_id).values(done=CryptoJob.done + 1)
            )
    return escribir


def _consulta(key_id: UUID) -> Select[Any]:
    return select(CryptoKey).where(CryptoKey.id == key_id).execution_options(populate_existing=True)


async def recorrer_llaves(
    session_factory: SessionFactory,
    job: JobHandle,
    ids: Sequence[UUID],
    r: Reenvoltura,
    *,
    actor: UUID,
) -> MigrationResult:
    """Re-envuelve `ids` en orden. Un `CryptoError` o una base ocupada (`lock_timeout`,
    `statement_timeout`, interbloqueo) dejan el job `failed` con un código y se devuelven, no se
    propagan; cualquier otra excepción, también las que no son `Exception`, lo deja `failed` y se
    relanza (S5-D189)."""
    hechas, saltadas = job.done, 0
    for key_id in ids:
        try:
            aplicada = await _una_llave(session_factory, key_id, job.id, actor, r)
        except BaseException as error:
            codigo = _codigo(error)
            await cerrar_job(session_factory, job.id, error=codigo or "unexpected")
            if codigo is None:
                raise
            return MigrationResult(job.total, hechas, saltadas, key_id, job.id, codigo)
        hechas, saltadas = hechas + 1, saltadas + (0 if aplicada else 1)
    await cerrar_job(session_factory, job.id, error=None)
    return MigrationResult(job.total, job.total, saltadas, None, job.id)


def _codigo(error: BaseException) -> str | None:
    """Código de un fallo recuperable (se informa y se reanuda) o `None` si debe propagarse."""
    if isinstance(error, CryptoError):
        return error.code
    if isinstance(error, DatabaseBusy) or (
        isinstance(error, DBAPIError) and translate_busy(error) is not None
    ):
        return "busy"
    return None


# Migración y verificación ----------------------------------------------------------------------


async def migrate_provider(
    session_factory: SessionFactory,
    *,
    from_: str,
    to: str,
    resolver: ProviderResolver,
    actor: UUID,
    dry_run: bool = False,
) -> MigrationResult:
    plan = plan_provider_migration(await listar_filas(session_factory), from_)
    if dry_run or not plan:
        return MigrationResult(len(plan), 0, 0)
    reenvoltura = Reenvoltura(resolver(from_), resolver(to), lambda fila: fila.provider == from_)
    job = await abrir_job(session_factory, "migrate_provider", len(plan), actor)
    return await recorrer_llaves(session_factory, job, plan, reenvoltura, actor=actor)


async def verify_provider(session_factory: SessionFactory, *, expected: str) -> int:
    """Filas `encrypt|index` que no están en `expected`; solo lectura (S5-D73, D183).

    Comprueba la UBICACIÓN (un `COUNT`), no que cada envoltura abra: eso lo hace la migración
    antes de cada `UPDATE` (S5-D186).
    """
    consulta = (
        select(func.count())
        .select_from(CryptoKey)
        .where(CryptoKey.purpose.in_(PURPOSES), CryptoKey.provider != expected)
    )
    async with session_factory() as session:
        return int(await session.scalar(consulta) or 0)
