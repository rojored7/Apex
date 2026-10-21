"""Auditoría append-only con cadena de hashes (US-015; RN-14, RN-16).

- `audit.audit_log`: cada fila lleva `seq` consecutivo, `prev_hash` (el `hash` de la
  anterior; 64 ceros en la primera) y `hash = SHA-256(prev_hash || canonical(fila))`.
- `canonical` es la serialización irreversible (ver docstring); `chain_hash` y
  `verify_chain` son puras y se prueban sin base.
- `append_entry` (síncrona, la usa el hook de US-016 dentro del flush) y `record`
  (async, para llamadas explícitas) asignan `seq = último + 1` bajo
  `pg_advisory_xact_lock(AUDIT_CHAIN_LOCK_KEY)`, así dos transacciones nunca toman el
  mismo `prev_hash`. El lock se libera solo al cerrar la transacción.
- La tabla se escribe siempre con `insert()` de Core, nunca con `session.add`, y la
  base rechaza `UPDATE`, `DELETE` y `TRUNCATE` (trigger `audit.forbid_mutation`).
- SHA-256 viene de `core/crypto/digest.py` (N-06): este módulo no importa `hashlib`.

US-016 agrega el hook `after_flush`, los listeners de sesión y `__audit_redact__`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any, Final, Literal
from uuid import UUID, uuid4

from sqlalchemy import CHAR, BigInteger, Text, insert, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import current_clock
from app.core.crypto.digest import sha256_hex
from app.core.db import Base

ZERO_HASH: Final = "0" * 64
# Lock asesor de la cadena (bigint fijo; distinto de MIGRATION_LOCK_KEY = 4_270_001).
AUDIT_CHAIN_LOCK_KEY: Final[int] = 4_270_002

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
MIRROR_KEYS: Final[tuple[tuple[str, str], ...]] = (
    ("created_at", "at"),
    ("updated_at", "at"),
    ("created_by", "user_id"),
)


class CanonicalError(ValueError):
    """Un valor no tiene representación canónica definida (RN-16: nunca "a ojo")."""


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
    """
    return json.dumps(
        _normalize(row), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def chain_hash(prev_hash: str, row: Mapping[str, object]) -> str:
    """`SHA-256(prev_hash || canonical(fila))` sobre las claves de `HASHED_KEYS`."""
    hashed = {k: row.get(k) for k in HASHED_KEYS}
    return sha256_hex(prev_hash.encode("ascii") + canonical(hashed))


def verify_chain(rows: Iterable[Mapping[str, object]]) -> VerifyResult:
    """Recorre las filas en orden y marca la primera ruptura (RN-16, N-30).

    Ruptura: `seq` no es el anterior más 1 (el primero debe ser 1), `prev_hash` no es el
    `hash` anterior (`ZERO_HASH` en la primera), el `hash` recalculado no coincide, o una
    columna espejo difiere de `at` o `user_id`.
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
    user_id: UUID,
) -> AuditRow:
    """Agrega una fila a la cadena dentro de la transacción de `conn` (síncrona)."""
    conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": AUDIT_CHAIN_LOCK_KEY})
    tabla = AuditEntry.__table__
    ultima = conn.execute(
        select(tabla.c.seq, tabla.c.hash).order_by(tabla.c.seq.desc()).limit(1)
    ).first()
    last_seq, prev_hash = (ultima.seq, ultima.hash) if ultima is not None else (0, ZERO_HASH)

    fila = AuditRow(
        id=uuid4(),
        seq=last_seq + 1,
        at=current_clock().now_utc(),
        user_id=user_id,
        action=action,
        table_name=table_name,
        record_id=record_id,
        before=_json_or_none(before),
        after=_json_or_none(after),
        prev_hash=prev_hash,
        hash="",
    )
    valores: dict[str, Any] = {k: getattr(fila, k) for k in HASHED_KEYS}
    fila = AuditRow(**{**valores, "prev_hash": prev_hash, "hash": chain_hash(prev_hash, valores)})
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
    user_id: UUID,
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
        )
    )
