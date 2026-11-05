"""Rotación reanudable de llaves y retiro con conteos confirmados (S4B-B3b, US-030).

Contrato (S4B-D39, D40, D63, D86, D95):
- `start_rotation` reanuda un job `rotate` de la clase en `pending`, `running` o `failed`; si no
  hay, pasa la llave `active` a `decrypt_only` bajo `FOR UPDATE`, crea la DEK `version + 1`,
  abre el job con `total` y registra el verbo `rotate`. Exclusión por clase con
  `pg_try_advisory_lock(hashtext(:clave))` (`ROTATE_LOCK_KEY_SQL`, clave `apex:rotate:<clase>`)
  en una conexión DEDICADA del pool, sin `isolation_level`: se toma, se confirma (el candado de
  sesión sobrevive al commit y la conexión no queda en transacción) y se suelta SIEMPRE en el
  `finally` con `pg_advisory_unlock`; si soltar falla, la conexión se invalida y el candado muere
  con ella. Nunca queda tomado en una conexión que vuelve al pool. Si otra conexión lo tiene,
  lanza `RotationInProgress` sin crear nada. Entre lotes la exclusión la dan los `FOR UPDATE` de
  las filas y el índice único de jobs en curso.
- `reencrypt_batch` recifra hasta `batch_size` filas con SQL de Core y conserva `updated_at`; salta
  con `skip_locked` las filas que otra transacción tiene bloqueadas (las recoge la pasada siguiente,
  S4B-D150); llama
  a `bus.decrypt` y `bus.encrypt` por atributo de módulo.
- `finish_rotation` recuenta bajo `FOR UPDATE` de la llave activa; con cero filas anteriores cierra
  el job en `done` y deja la llave anterior en `decrypt_only` (nunca `retired`).
- `retire_key` es el único camino a `retired`: exige estado `decrypt_only`, filas de negocio en
  cero (conteo bajo `FOR UPDATE` de la llave), el conteo de blobs de `audit.audit_log` que el
  operador confirmó, y registra el verbo `rotate`.
- Sin `core/audit` ni `app.modules`: la auditoría la escribe el CLI. Ningún mensaje de error lleva
  blobs, material ni el motivo recibido.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, Final, Literal
from uuid import UUID, uuid4

from sqlalchemy import Select, Text, bindparam, func, select, text, type_coerce, update
from sqlalchemy.engine import Result
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.core import db
from app.core.clock import current_clock
from app.core.config import get_settings
from app.core.context import SYSTEM_USER_ID
from app.core.crypto import bus, oplog
from app.core.crypto.bootstrap import DEK_LEN
from app.core.crypto.discovery import ColumnRef, encrypted_columns
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.keyring import current_keyring
from app.core.crypto.mac import hmac_sha256_hex
from app.core.crypto.models import CryptoJob, CryptoKey, CryptoOp, KeyState
from app.core.crypto.normalize import normalize_for_index
from app.core.crypto.provider import KeyProvider, current_provider
from app.core.crypto.registry import get_spec
from app.core.crypto.types import BlindIndexed
from app.core.db import Base, translate_busy

logger = logging.getLogger("app.crypto.service")

ROTATE_LOCK_KEY_SQL: Final = "SELECT pg_try_advisory_lock(hashtext(:clave))"
"""Candado de sesión por clase; `:clave` es `apex:rotate:<data_class>` (parámetro ligado)."""

ROTATE_UNLOCK_KEY_SQL: Final = "SELECT pg_advisory_unlock(hashtext(:clave))"
"""Suelta el candado de `ROTATE_LOCK_KEY_SQL` en la misma conexión."""

AUDIT_BLOBS_BY_KEY_SQL: Final = (
    "SELECT count(*) FROM audit.audit_log "
    "WHERE before::text LIKE :patron OR after::text LIKE :patron"
)
"""Blobs `apx1.<key_id>.` en `audit.audit_log` (S4B-D86); `:patron` es `%apx1.<key_id>.%`."""

ROTATE_LOCK_PREFIX: Final = "apex:rotate:"
BATCH_SIZE: Final = 500
MAX_REASON_LENGTH: Final = 200
MAX_INDEX_ROWS: Final = 50_000
MAX_ERROR_LENGTH: Final = 100
KEK_VERIFY_WINDOW: Final = timedelta(hours=24)
OPEN_JOB_STATES: Final = ("pending", "running", "failed")
CUSTODY_JOB_KINDS: Final = ("migrate_provider", "rewrap")
"""Jobs de custodia de la KEK: no conviven con una rotación de llaves de datos (S5-D190)."""

KeyEvent = Literal["rotate", "retire"]

_EMAIL = re.compile(r"\S+@\S+\.\S+")
_LONG_NUMBER = re.compile(r"\d{6,}")


class InvalidTransition(Exception):
    """Transición de estado de llave no permitida."""


class RotationInProgress(Exception):
    """Otra conexión tiene el candado de rotación de la clase."""


# Reglas puras --------------------------------------------------------------------------------


def next_key_state(current: KeyState, event: KeyEvent, purpose: str) -> KeyState:
    """Estado siguiente de una llave (pura); `InvalidTransition` si no es legal.

    `rotate`: `active -> decrypt_only`. `retire`: solo `decrypt_only -> retired`; retirar una
    llave `active` dejaría sin cifrar o sin buscar lo nuevo (el trigger lo
    admitiría, el servicio no).
    """
    if event == "rotate" and current == "active":
        return "decrypt_only"
    if event == "retire" and current == "decrypt_only":
        return "retired"
    raise InvalidTransition(f"la llave {purpose} en {current} no admite el evento {event}")


def validate_reason(reason: str) -> str:
    """`reason` ≤ 200, sin control, sin correo ni `\\d{6,}`; `ValueError` si no.

    Los mensajes no repiten el texto recibido (podría traer datos personales).
    """
    limpio = reason.strip()
    if not limpio:
        raise ValueError("el motivo es obligatorio")
    if len(limpio) > MAX_REASON_LENGTH:
        raise ValueError(f"el motivo supera {MAX_REASON_LENGTH} caracteres")
    if not limpio.isprintable():
        raise ValueError("el motivo no admite saltos de línea ni caracteres de control")
    if _EMAIL.search(limpio) or _LONG_NUMBER.search(limpio):
        raise ValueError("el motivo no admite correos ni números de seis o más dígitos")
    return limpio


# Ayudas --------------------------------------------------------------------------------------


async def _run(session: AsyncSession, stmt: Any) -> Result[Any]:
    """Ejecuta `stmt`; una espera agotada de candado (`lock_timeout`) sale como `DatabaseBusy`."""
    try:
        resultado: Result[Any] = await session.execute(stmt)
        return resultado
    except DBAPIError as error:
        ocupada = translate_busy(error)
        if ocupada is None:
            raise
        raise ocupada from error


def _class_of(job: CryptoJob) -> str:
    if job.data_class is None:
        raise ValueError("el job no tiene clase de dato")
    return job.data_class


def _provider() -> KeyProvider:
    """Proveedor de CREACIÓN de llaves nuevas (`CRYPTO_PROVIDER`, S5-D3); no el de la fila."""
    try:
        return current_provider()
    except CryptoError:
        # Sin proveedor fijado solo se tolera fuera de producción (pruebas, herramientas): el del
        # keyring. En producción no hay fallback (S5-D165).
        if _es_produccion():
            raise CryptoUnavailable(
                "not_loaded", "el proveedor de creación no está fijado"
            ) from None
        cargado = current_keyring().provider
        if cargado is None:
            raise
        return cargado


def _es_produccion() -> bool:
    try:
        return get_settings().ENV == "production"
    except Exception:  # sin configuración (pruebas): no es producción
        return False


def _key_stmt(purpose: str, data_class: str) -> Select[Any]:
    return (
        select(CryptoKey)
        .where(CryptoKey.purpose == purpose, CryptoKey.data_class == data_class)
        .order_by(CryptoKey.version)
        .execution_options(populate_existing=True)
    )


def _single_active(llaves: Sequence[CryptoKey], purpose: str) -> CryptoKey:
    for llave in llaves:
        if llave.state == "active":
            return llave
    raise CryptoError("key_missing", f"no hay llave {purpose} activa para rotar")


def _blob_key(ref: ColumnRef) -> Any:
    """Segundo campo del blob `apx1.<key_id>.<alg>...`, como texto."""
    return func.split_part(ref.column, ".", 2)


def _pending_stmt(ref: ColumnRef, active_id: UUID) -> Select[Any]:
    """`(id, blob)` de las filas cuyo blob no es de la llave activa (los `NULL` no cuentan)."""
    return (
        select(ref.table.c.id, type_coerce(ref.column, Text))
        .where(_blob_key(ref) != str(active_id))
        .order_by(ref.table.c.id)
    )


async def _count_where(session: AsyncSession, ref: ColumnRef, condition: Any) -> int:
    stmt = select(func.count()).select_from(ref.table).where(condition)
    return int(await session.scalar(stmt) or 0)


async def _pending_total(session: AsyncSession, refs: list[ColumnRef], active_id: UUID) -> int:
    return sum([await _count_where(session, r, _blob_key(r) != str(active_id)) for r in refs])


@asynccontextmanager
async def _rotation_lock(session: AsyncSession, data_class: str) -> AsyncIterator[None]:
    """Candado de sesión de la clase en una conexión dedicada; se suelta siempre al salir."""
    bind = session.bind
    motor = bind.engine if isinstance(bind, AsyncConnection) else bind
    if not isinstance(motor, AsyncEngine):
        raise RuntimeError("la sesión de rotación debe estar ligada a un AsyncEngine")
    clave = {"clave": f"{ROTATE_LOCK_PREFIX}{data_class}"}
    async with motor.connect() as conexion:
        tomado = await conexion.scalar(text(ROTATE_LOCK_KEY_SQL), clave)
        await conexion.commit()  # el candado es de sesión: sobrevive y la conexión queda libre
        if not tomado:
            raise RotationInProgress("otra rotación de esta clase está en curso")
        try:
            yield
        finally:
            await _release(conexion, clave)


async def _release(conexion: AsyncConnection, clave: dict[str, str]) -> None:
    try:
        await conexion.execute(text(ROTATE_UNLOCK_KEY_SQL), clave)
        await conexion.commit()
    except BaseException as error:
        logger.error("no se pudo soltar el candado de rotación; se invalida la conexión")
        await conexion.invalidate()  # el candado muere con la conexión
        if not isinstance(error, Exception):
            raise


async def _no_custody_job(session: AsyncSession) -> None:
    """Rechaza si hay una migración de proveedor o un rewrap de la KEK abierto (S5-D190)."""
    abierto = await session.scalar(
        select(CryptoJob.id)
        .where(CryptoJob.kind.in_(CUSTODY_JOB_KINDS), CryptoJob.status.in_(OPEN_JOB_STATES))
        .limit(1)
    )
    if abierto is not None:
        raise RotationInProgress("hay una migración o un rewrap de la KEK en curso")


async def _swap_key(
    session: AsyncSession, old: CryptoKey, actor: UUID
) -> tuple[CryptoKey, bytearray]:
    """`old` pasa a `decrypt_only` y nace la versión siguiente `active`; devuelve (nueva, DEK).

    Quien llama deja la DEK en ceros al terminar (S5-D151)."""
    next_key_state(old.state, "rotate", old.purpose)  # type: ignore[arg-type]
    old.state = "decrypt_only"
    old.rotated_at = current_clock().now_utc()
    old.rotated_by = actor
    await session.flush()  # libera el índice único de la activa antes de insertar la nueva
    dek = bytearray(os.urandom(DEK_LEN))
    proveedor = _provider()
    nueva = CryptoKey(
        id=uuid4(),
        purpose=old.purpose,
        data_class=old.data_class,
        algorithm=old.algorithm,
        provider=proveedor.name,
        version=old.version + 1,
        state="active",
        wrapped_material=await proveedor.wrap(dek),
        created_by=actor,
    )
    session.add(nueva)
    await session.flush()
    oplog.record("rotate", data_class=old.data_class, key_id=old.id, key_version=old.version)
    oplog.record("wrap", data_class=nueva.data_class, key_id=nueva.id, key_version=nueva.version)
    return nueva, dek


rotation_lock = _rotation_lock
"""Candado de sesión por clase; `rotation.py` lo usa con la clase `kek` (S5-D188)."""

# Rotación de la llave de cifrado -----------------------------------------------------------


def _open_job_stmt(data_class: str) -> Select[Any]:
    return (
        select(CryptoJob)
        .where(
            CryptoJob.kind == "rotate",
            CryptoJob.data_class == data_class,
            CryptoJob.status.in_(OPEN_JOB_STATES),
        )
        .order_by(CryptoJob.created_at.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )


async def start_rotation(
    session: AsyncSession, data_class: str, reason: str, actor: UUID
) -> CryptoJob:
    """Reanuda el job abierto de la clase o rota la llave `active` y abre uno nuevo."""
    validate_reason(reason)
    if not get_spec(data_class).encrypt:
        raise CryptoError("unsupported", f"la clase {data_class} no se cifra")
    await _no_custody_job(session)
    async with _rotation_lock(session, data_class):
        llaves = (await _run(session, _key_stmt("encrypt", data_class).with_for_update())).scalars()
        activa = _single_active(list(llaves), "encrypt")
        abierto = (await _run(session, _open_job_stmt(data_class).with_for_update())).scalar()
        if abierto is not None:
            abierto.status, abierto.error = "running", None
            return abierto  # type: ignore[no-any-return]
        nueva, dek = await _swap_key(session, activa, actor)
        dek[:] = bytes(len(dek))
        total = await _pending_total(
            session, encrypted_columns(Base.metadata, data_class), nueva.id
        )
        job = CryptoJob(
            kind="rotate",
            data_class=data_class,
            status="running",
            total=total,
            done=0,
            started_at=current_clock().now_utc(),
            created_by=actor,
        )
        session.add(job)
        await session.flush()
        return job


def _rewrite_params(rows: Sequence[Any], data_class: str) -> list[dict[str, Any]]:
    salida: list[dict[str, Any]] = []
    for fila in rows:
        id_, blob = fila[0], fila[1]
        aad = bus.aad_for(id_)
        claro = bus.decrypt(blob, aad, record_id=id_)
        salida.append({"b_id": id_, "b_valor": bus.encrypt(data_class, claro, aad, record_id=id_)})
    return salida


async def _write_back(
    session: AsyncSession, table: Any, column: str, params: list[dict[str, Any]]
) -> None:
    """`UPDATE` por `id` de Core que deja `updated_at` como estaba"""
    valores: dict[str, Any] = {column: bindparam("b_valor")}
    if "updated_at" in table.c:
        valores["updated_at"] = table.c.updated_at
    stmt = update(table).where(table.c.id == bindparam("b_id")).values(valores)
    await session.execute(stmt, params)


async def reencrypt_batch(
    session: AsyncSession, job: CryptoJob, batch_size: int = BATCH_SIZE
) -> int:
    """Recifra hasta `batch_size` filas con la llave anterior; devuelve las migradas (0 si no
    queda ninguna)."""
    if job.status == "done":
        return 0
    clase = _class_of(job)
    activa = current_keyring().active_for("encrypt", clase)
    vigente = await session.scalar(
        select(CryptoKey.id).where(
            CryptoKey.purpose == "encrypt",
            CryptoKey.data_class == clase,
            CryptoKey.state == "active",
        )
    )
    if vigente != activa.key_id:
        raise CryptoError("crypto_key_changed", "el keyring de este proceso no es el vigente")
    migradas = 0
    with oplog.batch("rotate", clase):
        for ref in encrypted_columns(Base.metadata, clase):
            if migradas >= batch_size:
                break
            consulta = _pending_stmt(ref, activa.key_id).with_for_update(skip_locked=True)
            filas = (await _run(session, consulta.limit(batch_size - migradas))).all()
            if filas:
                params = _rewrite_params(filas, clase)
                await _write_back(session, ref.table, ref.name, params)
            migradas += len(filas)
    job.done = min(job.done + migradas, job.total)
    return migradas


async def finish_rotation(session: AsyncSession, job: CryptoJob) -> bool:
    """Recuenta bajo `FOR UPDATE` de la llave activa; con cero filas anteriores cierra en `done`."""
    clase = _class_of(job)
    consulta = _key_stmt("encrypt", clase).where(CryptoKey.state == "active")
    activa = (await _run(session, consulta.with_for_update())).scalar()
    if activa is None:
        raise CryptoError("key_missing", f"no hay llave activa para {clase}")
    refs = encrypted_columns(Base.metadata, clase)
    if await _pending_total(session, refs, activa.id):
        return False
    job.status, job.done, job.error = "done", job.total, None
    job.finished_at = current_clock().now_utc()
    return True


async def fail_job(job_id: UUID, error_code: str) -> None:
    """Marca `failed` el job en curso, en su propia transacción; `error` es un código, no texto."""
    cambio = update(CryptoJob).where(
        CryptoJob.id == job_id, CryptoJob.status.in_(("pending", "running"))
    )
    async with db.get_sessionmaker()() as session, session.begin():
        await session.execute(cambio.values(status="failed", error=error_code[:MAX_ERROR_LENGTH]))


# Rotación de la llave de índice ciego -------------------------------------------------------


def _index_column(ref: ColumnRef, data_class: str) -> Any | None:
    for columna in ref.table.c:
        tipo = columna.type
        if (
            isinstance(tipo, BlindIndexed)
            and tipo.data_class == data_class
            and tipo.source == ref.name
        ):
            return columna
    return None


async def _reindex(
    session: AsyncSession,
    ref: ColumnRef,
    idx: Any,
    dek: bytes | bytearray,
    data_class: str,
    key: CryptoKey,
) -> int:
    """Recalcula `idx` de cada fila con `dek`; el valor se descifra con la llave de cifrado."""
    kind = get_spec(data_class).index_kind
    if kind is None:
        raise CryptoError("no_index", f"la clase {data_class} no tiene índice ciego")
    consulta: Select[Any] = select(ref.table.c.id, type_coerce(ref.column, Text)).where(
        ref.column.is_not(None)
    )
    filas: Sequence[Any] = (
        await _run(session, consulta.order_by(ref.table.c.id).with_for_update())
    ).all()
    params: list[dict[str, Any]] = []
    for fila in filas:
        id_, blob = fila[0], fila[1]
        claro = bus.decrypt(blob, bus.aad_for(id_), record_id=id_).decode("utf-8")
        valor = hmac_sha256_hex(dek, normalize_for_index(claro, kind).encode("utf-8"))
        oplog.record("index", data_class=data_class, key_id=key.id, key_version=key.version)
        params.append({"b_id": id_, "b_valor": valor})
    for desde in range(0, len(params), BATCH_SIZE):
        await _write_back(session, ref.table, idx.name, params[desde : desde + BATCH_SIZE])
    return len(params)


async def rotate_index(session: AsyncSession, data_class: str, reason: str, actor: UUID) -> int:
    """Nueva llave de índice y `*_idx` recalculados en UNA transacción; devuelve las filas."""
    validate_reason(reason)
    if get_spec(data_class).index_kind is None:
        raise CryptoError("no_index", f"la clase {data_class} no tiene índice ciego")
    await _no_custody_job(session)
    llaves = (await _run(session, _key_stmt("index", data_class).with_for_update())).scalars()
    activa = _single_active(list(llaves), "index")
    pares = [
        (r, _index_column(r, data_class)) for r in encrypted_columns(Base.metadata, data_class)
    ]
    total = sum([await _count_where(session, r, r.column.is_not(None)) for r, _ in pares])
    if total > MAX_INDEX_ROWS:
        raise ValueError(f"la clase tiene más de {MAX_INDEX_ROWS} filas; --index se niega")
    nueva, dek = await _swap_key(session, activa, actor)
    filas = 0
    try:
        with oplog.batch("index", data_class):
            for ref, idx in pares:
                if idx is not None:
                    filas += await _reindex(session, ref, idx, dek, data_class, nueva)
    finally:
        dek[:] = bytes(len(dek))
    return filas


# Conteos y retiro ----------------------------------------------------------------------------


async def _lock_key(session: AsyncSession, key_id: UUID) -> CryptoKey:
    consulta = (
        select(CryptoKey).where(CryptoKey.id == key_id).execution_options(populate_existing=True)
    )
    llave: CryptoKey | None = (await _run(session, consulta.with_for_update())).scalar()
    if llave is None:
        raise ValueError("la llave indicada no existe")
    return llave


async def count_rows_by_key(session: AsyncSession, key_id: UUID) -> dict[str, int]:
    """Filas con ese `key_id` por columna `esquema.tabla.columna`, bajo `FOR UPDATE` de la llave."""
    consulta = (
        select(CryptoKey).where(CryptoKey.id == key_id).execution_options(populate_existing=True)
    )
    llave = (await _run(session, consulta.with_for_update())).scalar()
    if llave is None:
        raise ValueError("la llave indicada no existe")
    if llave.purpose != "encrypt":
        return {}  # solo los blobs de cifrado llevan el `key_id`
    refs = encrypted_columns(Base.metadata, llave.data_class)
    return {r.qualified: await _count_where(session, r, _blob_key(r) == str(key_id)) for r in refs}


async def count_audit_blobs(session: AsyncSession, key_id: UUID) -> int:
    """Blobs de esa llave en `before`/`after` de `audit.audit_log` (S4B-D86)."""
    patron = f"%apx1.{key_id}.%"
    return int(await session.scalar(text(AUDIT_BLOBS_BY_KEY_SQL), {"patron": patron}) or 0)


async def retire_key(
    session: AsyncSession, key_id: UUID, *, confirmed_audit_blobs: int, actor: UUID
) -> int:
    """Pasa la llave a `retired`; devuelve los blobs de auditoría confirmados."""
    llave = await _lock_key(session, key_id)
    nuevo = next_key_state(llave.state, "retire", llave.purpose)  # type: ignore[arg-type]
    pendientes = sum((await count_rows_by_key(session, key_id)).values())
    if pendientes:
        raise ValueError(f"quedan {pendientes} filas de negocio con esa llave; no se retira")
    blobs = await count_audit_blobs(session, key_id)
    if blobs != confirmed_audit_blobs:
        raise ValueError("el conteo de blobs de auditoría confirmado no coincide con el real")
    llave.state = nuevo
    await session.flush()
    oplog.record("rotate", data_class=llave.data_class, key_id=llave.id, key_version=llave.version)
    return blobs


async def recent_kek_verify(session: AsyncSession, *, within: timedelta) -> bool:
    """Hay un `verify` `ok` de `kek.backup` de una persona (no el usuario técnico) en `within`."""
    desde = current_clock().now_utc() - within
    consulta = (
        select(func.count())
        .select_from(CryptoOp)
        .where(
            CryptoOp.verb == "verify",
            CryptoOp.data_class == "kek.backup",
            CryptoOp.result == "ok",
            CryptoOp.user_id != SYSTEM_USER_ID,
            CryptoOp.at >= desde,
        )
    )
    return int(await session.scalar(consulta) or 0) > 0
