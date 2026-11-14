"""Firma de la cadena de auditoría (US-140; S6-D3, S6-D4, S6-D7, S6-D34, S6-D40; ADR-006).

Archivo hermano de `core/audit.py` y `core/audit_verify.py`: la serialización de la cadena es
irreversible (ADR-004) y no se toca. Importa solo `core.audit`, `core.crypto.bus`, `core.context` y
`core.db`; nunca `app.modules` ni `core.jobs`.

- `AuditSignature`: fila de `audit.signatures` (`0021_audit_signatures`; append-only por triggers).
  Sin `__audited__`: auditaría la auditoría; la firma deja `crypto_ops(verb=sign)`.
- `signature_payload`: `b"apex-audit-sig-v1\\n<through_seq>\\n<chain_hash>"` en ASCII (ADR-006).
- `check_unsigned_segment` (H-1, S6-D34): recalcula el tramo sin firmar con `core.audit.chain_hash`
  (el serializador canónico), por lotes, anclado al hash de la última firma. Solo lectura.
- `sign_latest`: bajo `pg_advisory_xact_lock(4_270_004)`, verifica el tramo y firma el hash de la
  última fila; si el tramo no cuadra devuelve `chain_broken` y no inserta nada. No confirma.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal, cast
from uuid import UUID

from sqlalchemy import CHAR, BigInteger, ForeignKey, SmallInteger, Text, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit import ZERO_HASH, AuditEntry, CanonicalError, chain_hash, verify_chain
from app.core.context import SYSTEM_USER_ID
from app.core.crypto.bus import sign as bus_sign
from app.core.db import Base, CommonColumnsMixin

AUDIT_SIGN_LOCK_KEY: Final[int] = 4_270_004
"""Candado asesor de transacción de la firma; distinto de 4_270_001, 4_270_002 y 4_270_003."""
SIGN_LOCK_SQL: Final = "SELECT pg_advisory_xact_lock(:key)"
SIGN_LOCK_STATEMENT: Final = text(SIGN_LOCK_SQL)
SIGNATURES_TABLE: Final = "audit.signatures"
SIGNATURE_CLASS: Final = "audit.signature"
PAYLOAD_PREFIX: Final = "apex-audit-sig-v"
PAYLOAD_VERSION: Final = 1
SEGMENT_BATCH_SIZE: Final = 500
LATE_THRESHOLD_H: Final = 48
_HASH_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_LOG = AuditEntry.__table__


class AuditSignature(CommonColumnsMixin, Base):
    """Fila de `audit.signatures` (`0021_audit_signatures`; append-only; S6-D7). Sin `__audited__`:
    auditaría la auditoría; la firma queda en `crypto_ops(verb=sign)`. La columna `hash` se mapea
    como `chain_hash`."""

    __tablename__ = "signatures"
    __table_args__ = {"schema": "audit"}  # noqa: RUF012

    through_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chain_hash: Mapped[str] = mapped_column("hash", CHAR(64), nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    key_id: Mapped[UUID] = mapped_column(
        ForeignKey("crypto.crypto_keys.id", ondelete="RESTRICT"), nullable=False
    )
    algorithm: Mapped[str] = mapped_column(Text, nullable=False)
    payload_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    signed_at: Mapped[datetime] = mapped_column(nullable=False)


@dataclass(frozen=True)
class SegmentCheck:
    """Resultado de recorrer un tramo; `last_hash` es el de la última fila verificada."""

    ok: bool
    from_seq: int
    to_seq: int
    broken_at_seq: int | None
    last_hash: str | None = None


@dataclass(frozen=True)
class SignOutcome:
    """`through_seq`: lo firmado, lo último ya firmado (`nothing_new`) o el `seq` roto."""

    kind: Literal["signed", "nothing_new", "chain_broken"]
    through_seq: int
    signature_id: UUID | None


def _payload_v1(through_seq: int, chain_hash: str) -> bytes:
    """Constructor del payload `payload_version = 1` (ADR-006). Rechaza con `CanonicalError`."""
    if type(through_seq) is not int or through_seq < 1:
        raise CanonicalError("through_seq debe ser un entero mayor o igual a 1")
    if not isinstance(chain_hash, str) or _HASH_RE.fullmatch(chain_hash) is None:
        raise CanonicalError("chain_hash debe ser 64 hexadecimales en minúscula")
    return f"{PAYLOAD_PREFIX}1\n{through_seq}\n{chain_hash}".encode("ascii")


PAYLOAD_BUILDERS: Final[dict[int, Callable[[int, str], bytes]]] = {1: _payload_v1}
"""Constructores del payload por `payload_version` (S6-A3, S6-D62): quien firma o verifica elige el
de la fila. Una versión sin constructor es inválida (nunca una excepción para quien verifica)."""


def signature_payload(
    through_seq: int, chain_hash: str, *, version: int = PAYLOAD_VERSION
) -> bytes:
    """Los bytes que se firman (ADR-006). Rechaza con `CanonicalError` toda entrada inválida."""
    constructor = PAYLOAD_BUILDERS.get(version)
    if constructor is None:
        raise CanonicalError(f"versión de payload desconocida: {version!r}")
    return constructor(through_seq, chain_hash)


def needs_signature(last_seq: int, last_signed_seq: int) -> bool:
    """Hay filas posteriores a la última firmada."""
    return last_seq > last_signed_seq


def is_signature_late(
    last_seq: int,
    last_signed_seq: int,
    first_unsigned_at: datetime | None,
    now: datetime,
    threshold_h: int = LATE_THRESHOLD_H,
) -> bool:
    """«Firma atrasada»: hay filas sin firmar y la más antigua pasa el umbral (estricto).

    Una firma vieja sin filas nuevas no atrasa; sin `first_unsigned_at` no hay edad que medir y
    no se alerta (S6-D40).
    """
    if not needs_signature(last_seq, last_signed_seq) or first_unsigned_at is None:
        return False
    return now - first_unsigned_at > timedelta(hours=threshold_h)


async def _read_batch(
    session: AsyncSession, after_seq: int, until_seq: int
) -> Sequence[Mapping[str, object]]:
    lote = await session.execute(
        select(_LOG)
        .where(_LOG.c.seq > after_seq, _LOG.c.seq <= until_seq)
        .order_by(_LOG.c.seq)
        .limit(SEGMENT_BATCH_SIZE)
    )
    return cast("Sequence[Mapping[str, object]]", lote.mappings().all())


async def check_unsigned_segment(
    session: AsyncSession, *, from_seq: int, to_seq: int, anchor_hash: str
) -> SegmentCheck:
    """Recalcula `from_seq..to_seq` con `core.audit.chain_hash`, partiendo de `anchor_hash` (el
    hash firmado de la fila `from_seq - 1`, o `ZERO_HASH`). Se detiene en la primera ruptura; un
    hueco (filas que faltan) también rompe, en el primer `seq` ausente."""
    prev_seq, prev_hash = from_seq - 1, anchor_hash
    while prev_seq < to_seq:
        filas = await _read_batch(session, prev_seq, to_seq)
        if not filas:
            return SegmentCheck(False, from_seq, to_seq, prev_seq + 1, prev_hash)
        parcial = verify_chain(filas, start_prev_hash=prev_hash, start_seq=prev_seq + 1)
        if not parcial.ok:
            return SegmentCheck(False, from_seq, to_seq, parcial.broken_at_seq, prev_hash)
        prev_seq, prev_hash = int(parcial.last_seq or 0), str(parcial.last_hash)
    return SegmentCheck(True, from_seq, to_seq, None, prev_hash)


async def _anchor_holds(session: AsyncSession, previa: AuditSignature) -> bool:
    """La fila firmada conserva su contenido: existe, su `hash` guardado es el firmado y recalculado
    con `core.audit.chain_hash` también (una fila alterada sin tocar `hash` no pasa)."""
    fila = (
        (await session.execute(select(_LOG).where(_LOG.c.seq == previa.through_seq)))
        .mappings()
        .first()
    )
    if fila is None or fila["hash"] != previa.chain_hash:
        return False
    return (
        chain_hash(str(fila["prev_hash"]), cast("Mapping[str, object]", fila)) == previa.chain_hash
    )


async def latest_signature(session: AsyncSession) -> AuditSignature | None:
    """La firma de mayor `through_seq`, o `None`."""
    return await session.scalar(
        select(AuditSignature).order_by(AuditSignature.through_seq.desc()).limit(1)
    )


async def sign_latest(session: AsyncSession, *, by: UUID = SYSTEM_USER_ID) -> SignOutcome:
    """Firma el hash de la última fila de la cadena si hay filas sin firmar y el tramo es íntegro.

    El candado de transacción se toma ANTES de leer el último `seq` (dos firmantes no firman lo
    mismo). No confirma: quien llama hace `commit` (que libera el candado)."""
    await session.execute(SIGN_LOCK_STATEMENT, {"key": AUDIT_SIGN_LOCK_KEY})
    last_seq = int(await session.scalar(select(func.coalesce(func.max(_LOG.c.seq), 0))) or 0)
    previa = await latest_signature(session)
    signed_seq = 0 if previa is None else previa.through_seq
    if not needs_signature(last_seq, signed_seq):
        return SignOutcome("nothing_new", last_seq, None)
    if previa is not None and not await _anchor_holds(session, previa):
        return SignOutcome("chain_broken", previa.through_seq, None)  # el ancla ya no coincide
    anchor = ZERO_HASH if previa is None else previa.chain_hash
    segmento = await check_unsigned_segment(
        session, from_seq=signed_seq + 1, to_seq=last_seq, anchor_hash=anchor
    )
    if not segmento.ok or segmento.last_hash is None:
        return SignOutcome("chain_broken", segmento.broken_at_seq or last_seq, None)
    firma = await bus_sign(SIGNATURE_CLASS, signature_payload(last_seq, segmento.last_hash))
    partes = firma.split(".")
    # `clock_timestamp()` tras el candado y la firma: `now()` es el inicio de la transacción y una
    # sesión que esperó el candado firmaría con una hora anterior a la firma previa (H2).
    ahora = await session.scalar(select(func.clock_timestamp()))
    fila = AuditSignature(
        through_seq=last_seq,
        chain_hash=segmento.last_hash,
        signature=firma,
        key_id=UUID(partes[1]),
        algorithm=partes[2],
        payload_version=PAYLOAD_VERSION,
        signed_at=cast("datetime", ahora),
        created_by=by,
    )
    session.add(fila)
    await session.flush()
    return SignOutcome("signed", last_seq, fila.id)


async def limit_statement_time(session: AsyncSession, timeout_s: float) -> None:
    """`statement_timeout` local a la transacción (S6-A2): una consulta colgada no retiene el
    candado de la firma más allá del tope. `set_config(..., true)` es válido con parámetros."""
    milisegundos = max(1, int(timeout_s * 1000))
    await session.execute(select(func.set_config("statement_timeout", f"{milisegundos}ms", True)))


async def late_hours(session: AsyncSession, now: datetime) -> int | None:
    """Horas enteras de la fila sin firmar más antigua si la firma está atrasada
    (`is_signature_late` contra `now`), o `None`. Solo lectura, sin candado."""
    last_seq = int(await session.scalar(select(func.coalesce(func.max(_LOG.c.seq), 0))) or 0)
    previa = await latest_signature(session)
    signed_seq = 0 if previa is None else previa.through_seq
    primera = await session.scalar(select(func.min(_LOG.c.at)).where(_LOG.c.seq > signed_seq))
    if not is_signature_late(last_seq, signed_seq, primera, now):
        return None
    return int((now - cast("datetime", primera)).total_seconds() // 3600)
