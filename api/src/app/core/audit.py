"""Auditoría append-only: cadena de hashes y hook de sesión (US-015, US-016; RN-13, 14 y 16).

Cadena (US-015):
- `audit.audit_log`: cada fila lleva `seq` consecutivo, `prev_hash` (el `hash` de la
  anterior; 64 ceros en la primera) y `hash = SHA-256(prev_hash || canonical(fila))`.
- `canonical` es la serialización irreversible (ver docstring); `chain_hash` y
  `verify_chain` son puras y se prueban sin base.
- `append_entry` (síncrona, la usa el hook dentro del flush) y `record` (async, para
  llamadas explícitas: reveal, export, verify) asignan `seq = último + 1` bajo
  `pg_advisory_xact_lock(AUDIT_CHAIN_LOCK_KEY)`, así dos transacciones nunca toman el
  mismo `prev_hash`. El lock se libera solo al cerrar la transacción.
- La tabla se escribe siempre con `insert()` de Core, nunca con `session.add`, y la
  base rechaza `UPDATE`, `DELETE` y `TRUNCATE` (trigger `audit.forbid_mutation`).
- `subject_member_id` (G-05) entra al hash solo cuando no es nulo, así las filas sin
  sujeto conservan el hash de US-015.
- SHA-256 viene de `core/crypto/digest.py` (N-06): este módulo no importa la biblioteca
  de hashes de la biblioteca estándar (regla 8 del bus).

Hook (US-016), instalado con `install_audit_listeners()` desde `create_app`, el worker,
el CLI y `tests/conftest.py`:
- `before_flush`: todo objeto nuevo con `CommonColumnsMixin` y `created_by` vacío toma
  `get_actor()`; sin actor, el flush falla con `MissingActorError`.
- `after_flush`: por cada objeto de un modelo con `__audited__ = True` escribe `insert`
  (con `after` completo), `update` (solo las columnas que cambiaron, con `before` y
  `after`) o `delete` (con `before` completo), en la misma conexión y transacción.
  Un borrado lógico (`deleted_at`) es un `update`.
- Atributos de clase opcionales del modelo: `__audit_redact__` (valores sustituidos por
  `"***"`, por ejemplo `password_hash`), `__audit_exclude__` (columnas que no generan un
  `update`, por ejemplo `last_login_at`) y `__audit_subject__` (nombre del atributo que
  da el socio: `"id"` en `members`, `"member_id"` en `memberships` y `payments`).

Contratos:
- Para US-028: el atributo mapeado de una columna `Encrypted` contiene siempre el blob
  `apx1.…`; el valor en claro va en un accesor aparte, y el tipo expone
  `is_encrypted = True`. El hook reconoce la columna por ese atributo y rechaza el flush
  con `PlaintextInAuditError` si llega un valor sin el prefijo (RN-13).
- Para US-034: `current_user` fija el actor sin resetearlo (ver `core/context.py`).
- Los modelos auditados no usan columnas `deferred` y la sesión usa
  `expire_on_commit=False`: si una columna no estuviera cargada al modificarla,
  `history.deleted` vendría vacío y `before` quedaría incompleto.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any, Final, Literal
from uuid import UUID, uuid4

from sqlalchemy import CHAR, BigInteger, Text, event, insert, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, Session, UOWTransaction, class_mapper, mapped_column
from sqlalchemy.orm.attributes import instance_state
from sqlalchemy.orm.base import NO_VALUE

from app.core.clock import current_clock
from app.core.context import get_actor
from app.core.crypto.digest import sha256_hex
from app.core.db import Base, CommonColumnsMixin

ZERO_HASH: Final = "0" * 64
# Lock asesor de la cadena (bigint fijo; distinto de MIGRATION_LOCK_KEY = 4_270_001).
AUDIT_CHAIN_LOCK_KEY: Final[int] = 4_270_002
BLOB_PREFIX: Final = "apx1."
REDACTED: Final = "***"
TECHNICAL_COLUMNS: Final[frozenset[str]] = frozenset({"created_at", "updated_at"})

AuditAction = Literal[
    "insert", "update", "delete", "reveal", "export", "download", "login", "verify"
]
AUDIT_ACTIONS: Final[tuple[str, ...]] = (
    "insert",
    "update",
    "delete",
    "reveal",
    "export",
    "download",
    "login",
    "verify",
)
# Claves de la fila que entran al hash. Las columnas espejo (`created_at`, `updated_at`,
# `created_by`) quedan fuera: las fija un CHECK y `verify_chain` las compara aparte.
HASHED_KEYS: Final[tuple[str, ...]] = (
    "id",
    "seq",
    "at",
    "user_id",
    "action",
    "table_name",
    "record_id",
    "before",
    "after",
)
SUBJECT_KEY: Final = "subject_member_id"
MIRROR_KEYS: Final[tuple[tuple[str, str], ...]] = (
    ("created_at", "at"),
    ("updated_at", "at"),
    ("created_by", "user_id"),
)

JsonValue = None | bool | int | str | list["JsonValue"] | dict[str, "JsonValue"]


class CanonicalError(ValueError):
    """Un valor no tiene representación canónica definida (RN-16: nunca "a ojo")."""


class AuditSerializationError(CanonicalError):
    """Un valor de una fila auditada no tiene representación JSON definida."""


class PlaintextInAuditError(RuntimeError):
    """Una columna cifrada llegó a la auditoría sin el prefijo `apx1.` (RN-13)."""


class AuditEntry(Base):
    """Fila de `audit.audit_log`. No hereda el mixin: `created_at` debe ser igual a `at`."""

    __tablename__ = "audit_log"
    __table_args__ = {"schema": "audit"}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    at: Mapped[datetime] = mapped_column(nullable=False)
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    record_id: Mapped[UUID | None] = mapped_column(nullable=True)
    subject_member_id: Mapped[UUID | None] = mapped_column(nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(postgresql.JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(postgresql.JSONB, nullable=True)
    prev_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)
    created_by: Mapped[UUID] = mapped_column(nullable=False)


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    rows_checked: int
    broken_at_seq: int | None


@dataclass(frozen=True)
class AuditRow:
    id: UUID
    seq: int
    at: datetime
    user_id: UUID
    action: str
    table_name: str
    record_id: UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    prev_hash: str
    hash: str
    subject_member_id: UUID | None = None


# Serialización canónica ----------------------------------------------------------


def _normalize(value: object) -> object:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalError("datetime ingenuo: la auditoría exige instantes con zona")
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value).lower()
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, Mapping):
        return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_normalize(v) for v in value]
    raise CanonicalError(f"sin representación canónica: {type(value).__name__}")


def canonical(row: Mapping[str, object]) -> bytes:
    """Bytes canónicos de una fila. **Decisión irreversible** (ADR, US-119).

    Especificación:
    - `json.dumps(normalizada, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
      allow_nan=False).encode("utf-8")`;
    - `datetime`: exige un valor con zona, lo pasa a UTC y lo escribe como
      `YYYY-MM-DDTHH:MM:SS.ffffffZ`, siempre con 6 decimales;
    - `date`: `YYYY-MM-DD`;
    - `UUID`: texto en minúscula con guiones;
    - `None`: `null`;
    - `bool`, `int` y `str` quedan tal cual, sin normalizar Unicode;
    - `Enum`: su `.value`;
    - `dict` y `list` se recorren de forma recursiva (las claves se vuelven `str`);
    - `float`, `Decimal`, `bytes` y cualquier otro tipo lanzan `CanonicalError`.

    En la cadena entran las claves de `HASHED_KEYS` y, solo cuando no es nula,
    `subject_member_id` (G-05).
    """
    return json.dumps(
        _normalize(row), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _hashed_keys(row: Mapping[str, object]) -> dict[str, object]:
    hashed = {k: row.get(k) for k in HASHED_KEYS}
    if row.get(SUBJECT_KEY) is not None:
        hashed[SUBJECT_KEY] = row[SUBJECT_KEY]
    return hashed


def chain_hash(prev_hash: str, row: Mapping[str, object]) -> str:
    """`SHA-256(prev_hash || canonical(fila))` sobre las claves de `HASHED_KEYS`."""
    return sha256_hex(prev_hash.encode("ascii") + canonical(_hashed_keys(row)))


def verify_chain(rows: Iterable[Mapping[str, object]]) -> VerifyResult:
    """Recorre las filas en orden y marca la primera ruptura (RN-16, N-30).

    Ruptura: `seq` no es el anterior más 1 (el primero debe ser 1), `prev_hash` no es el
    `hash` anterior (`ZERO_HASH` en la primera), el `hash` recalculado no coincide, o una
    columna espejo difiere de `at` o `user_id`. `rows_checked` cuenta hasta la ruptura.
    """
    checked = 0
    prev_seq = 0
    prev_hash = ZERO_HASH
    for row in rows:
        checked += 1
        seq = int(str(row.get("seq")))
        mirrors_ok = all(row.get(k) == row.get(src) for k, src in MIRROR_KEYS if k in row)
        if (
            seq != prev_seq + 1
            or row.get("prev_hash") != prev_hash
            or row.get("hash") != chain_hash(prev_hash, row)
            or not mirrors_ok
        ):
            return VerifyResult(ok=False, rows_checked=checked, broken_at_seq=seq)
        prev_seq = seq
        prev_hash = str(row["hash"])
    return VerifyResult(ok=True, rows_checked=checked, broken_at_seq=None)


# Escritura -------------------------------------------------------------------------


def _json_or_none(value: Mapping[str, object] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    normalized = _normalize(value)
    assert isinstance(normalized, dict)  # noqa: S101 - _normalize de un Mapping da dict
    return normalized


def append_entry(
    conn: Connection,
    *,
    action: AuditAction,
    table_name: str,
    record_id: UUID | None,
    before: Mapping[str, object] | None,
    after: Mapping[str, object] | None,
    user_id: UUID | None = None,
    subject_member_id: UUID | None = None,
) -> AuditRow:
    """Agrega una fila a la cadena dentro de la transacción de `conn` (síncrona).

    Sin `user_id`, toma el actor del contexto (`get_actor()`).
    """
    actor = user_id if user_id is not None else get_actor()
    conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": AUDIT_CHAIN_LOCK_KEY})
    tabla = AuditEntry.__table__
    ultima = conn.execute(
        select(tabla.c.seq, tabla.c.hash).order_by(tabla.c.seq.desc()).limit(1)
    ).first()
    last_seq, prev_hash = (ultima.seq, ultima.hash) if ultima is not None else (0, ZERO_HASH)

    valores: dict[str, Any] = {
        "id": uuid4(),
        "seq": last_seq + 1,
        "at": current_clock().now_utc(),
        "user_id": actor,
        "action": action,
        "table_name": table_name,
        "record_id": record_id,
        "before": _json_or_none(before),
        "after": _json_or_none(after),
        SUBJECT_KEY: subject_member_id,
    }
    fila = AuditRow(**valores, prev_hash=prev_hash, hash=chain_hash(prev_hash, valores))
    conn.execute(
        insert(AuditEntry).values(
            **valores,
            prev_hash=fila.prev_hash,
            hash=fila.hash,
            created_at=fila.at,
            updated_at=fila.at,
            created_by=fila.user_id,
        )
    )
    return fila


async def record(
    session: AsyncSession,
    *,
    action: AuditAction,
    table_name: str,
    record_id: UUID | None,
    before: Mapping[str, object] | None,
    after: Mapping[str, object] | None,
    user_id: UUID | None = None,
    subject_member_id: UUID | None = None,
) -> AuditRow:
    """Versión async de `append_entry` para llamadas explícitas (reveal, export, verify)."""
    return await session.run_sync(
        lambda s: append_entry(
            s.connection(),
            action=action,
            table_name=table_name,
            record_id=record_id,
            before=before,
            after=after,
            user_id=user_id,
            subject_member_id=subject_member_id,
        )
    )


# Hook de auditoría (US-016) ---------------------------------------------------------


def serialize_value(value: object) -> JsonValue:
    """Valor JSON de una columna auditada; misma regla que `canonical`."""
    try:
        normalized = _normalize(value)
    except CanonicalError as error:
        raise AuditSerializationError(str(error)) from error
    return normalized  # type: ignore[return-value]


def serialize_row(
    values: Mapping[str, object], *, encrypted: frozenset[str], redacted: frozenset[str]
) -> dict[str, JsonValue]:
    """Fila lista para `before`/`after`: sin columnas técnicas, con redacción y guarda RN-13."""
    salida: dict[str, JsonValue] = {}
    for key, value in values.items():
        if key in TECHNICAL_COLUMNS:
            continue
        if key in redacted:
            salida[key] = REDACTED
            continue
        if (
            key in encrypted
            and value is not None
            and not (isinstance(value, str) and value.startswith(BLOB_PREFIX))
        ):
            raise PlaintextInAuditError(
                f"la columna cifrada '{key}' llegó a la auditoría sin el prefijo {BLOB_PREFIX}"
            )
        salida[key] = serialize_value(value)
    return salida


def diff_row(
    before: Mapping[str, object], after: Mapping[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    """Solo las claves cuyo valor cambió, incluido el cambio a `None`."""
    keys = [k for k in dict.fromkeys([*before, *after]) if before.get(k) != after.get(k)]
    return {k: before.get(k) for k in keys}, {k: after.get(k) for k in keys}


def _is_audited(obj: object) -> bool:
    return bool(getattr(type(obj), "__audited__", False))


def _table_name(obj: object) -> str:
    tabla = class_mapper(type(obj)).local_table
    nombre = str(getattr(tabla, "name", tabla))
    esquema = getattr(tabla, "schema", None)
    return f"{esquema}.{nombre}" if esquema else nombre


def _subject(obj: object) -> UUID | None:
    atributo = getattr(type(obj), "__audit_subject__", None)
    if atributo is None:
        return None
    valor = getattr(obj, atributo, None)
    return valor if isinstance(valor, UUID) else None


def _encrypted_columns(obj: object) -> frozenset[str]:
    mapper = class_mapper(type(obj))
    return frozenset(
        attr.key
        for attr in mapper.column_attrs
        if any(getattr(col.type, "is_encrypted", False) for col in attr.columns)
    )


def _bind_value(attr: Any, value: object) -> object:
    """Una columna cifrada (US-028) se serializa como la base la recibe: el blob.

    `process_bind_param` del tipo rechaza texto en claro, así el hook nunca lo guarda. La
    auditoría no importa `core.crypto`: reconoce el tipo por `is_encrypted`.
    """
    tipo = attr.columns[0].type
    if getattr(tipo, "is_encrypted", False) and value is not None:
        procesar = getattr(tipo, "process_bind_param", None)
        if procesar is not None:
            return procesar(value, None)
    return value


def _snapshot(obj: object) -> dict[str, object]:
    """Valores cargados del objeto, sin disparar cargas durante el flush."""
    estado = instance_state(obj)
    valores: dict[str, object] = {}
    for attr in estado.mapper.column_attrs:
        valor = estado.attrs[attr.key].loaded_value
        if valor is not NO_VALUE:
            valores[attr.key] = _bind_value(attr, valor)
    return valores


def _changes(obj: object) -> tuple[dict[str, object], dict[str, object]]:
    estado = instance_state(obj)
    excluded = frozenset(getattr(type(obj), "__audit_exclude__", frozenset()))
    before: dict[str, object] = {}
    after: dict[str, object] = {}
    for attr in estado.mapper.column_attrs:
        if attr.key in excluded or attr.key in TECHNICAL_COLUMNS:
            continue
        history = estado.attrs[attr.key].history
        if not history.has_changes():
            continue
        before[attr.key] = _bind_value(attr, history.deleted[0] if history.deleted else None)
        after[attr.key] = _bind_value(attr, history.added[0] if history.added else None)
    return diff_row(before, after)


def _serialize(obj: object, values: Mapping[str, object]) -> dict[str, JsonValue]:
    return serialize_row(
        values,
        encrypted=_encrypted_columns(obj),
        redacted=frozenset(getattr(type(obj), "__audit_redact__", frozenset())),
    )


def _before_flush(session: Session, flush_context: UOWTransaction, instances: object) -> None:
    for obj in session.new:
        if isinstance(obj, CommonColumnsMixin) and obj.__dict__.get("created_by") is None:
            obj.created_by = get_actor()


Pending = tuple[AuditAction, object, dict[str, JsonValue] | None, dict[str, JsonValue] | None]


def _after_flush(session: Session, flush_context: UOWTransaction) -> None:
    pendientes: list[Pending] = []
    for obj in session.new:
        if _is_audited(obj):
            pendientes.append(("insert", obj, None, _serialize(obj, _snapshot(obj))))
    for obj in session.dirty:
        if _is_audited(obj) and session.is_modified(obj):
            antes, despues = _changes(obj)
            if despues:
                pendientes.append(("update", obj, _serialize(obj, antes), _serialize(obj, despues)))
    for obj in session.deleted:
        if _is_audited(obj):
            pendientes.append(("delete", obj, _serialize(obj, _snapshot(obj)), None))
    if not pendientes:
        return
    actor = get_actor()
    conn = session.connection()
    for action, obj, before, after in pendientes:
        append_entry(
            conn,
            action=action,
            table_name=_table_name(obj),
            record_id=getattr(obj, "id", None),
            before=before,
            after=after,
            user_id=actor,
            subject_member_id=_subject(obj),
        )


def install_audit_listeners() -> None:
    """Registra los listeners sobre la clase `Session` síncrona (idempotente)."""
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
    if not event.contains(Session, "after_flush", _after_flush):
        event.listen(Session, "after_flush", _after_flush)
