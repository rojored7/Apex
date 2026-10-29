"""Verificación de la cadena de auditoría con ancla (US-104, US-105; S4A-D12, S4A-D43, S4A-D47).

- `AuditVerification`: fila de `audit.verifications` (nace en `0013_audit_verifications`;
  append-only por los triggers `verifications_forbid_mutation` y `verifications_forbid_truncate`
  sobre `audit.forbid_mutation()`). Sin `__audited__`: su resultado entra a la cadena como fila
  `verify` (N-30, S4A-D12; `test_audited_tables.EXCLUIDAS`).
- `run_verification(session, *, source, by) -> VerificationView`: `started_at`, `through_seq =
  max(seq)` (0 si vacía), el ancla (`_anchor`: la última verificación `ok`), el recorrido por lotes
  de `VERIFY_BATCH_SIZE` filas con `verify_chain(lote, start_prev_hash=..., start_seq=...)` y
  `_pause_between_batches()` entre lotes (cede el event loop, S4A-D47), parada en la primera
  ruptura, la comprobación del ancla (`_check_anchor`, H-1: `max(seq) >= ancla.through_seq` y la
  fila `ancla.through_seq` con `hash = ancla.through_hash`; si no, `ok = false` y
  `broken_at_seq = min(last_seq + 1, ancla.through_seq)`), y `_persist`: la fila de
  `audit.verifications` más la fila `verify` de la cadena (`table_name = "audit.verifications"`,
  `record_id = id`, `before = None`, `after = {ok, rows_checked, broken_at_seq, through_seq,
  through_hash, started_at, finished_at, source}`, `user_id = by`). Si `ok`, una línea de log
  `audit anchor` con `through_seq` y `through_hash` (nunca `before`/`after`). Solo una
  verificación `ok` mueve el ancla. Nunca modifica filas existentes de `audit.audit_log`.
- `format_verify_message(result) -> (texto, código)`: 0 íntegra, 1 rota (CLI y logs).

El candado de la verificación (`AUDIT_VERIFY_LOCK_KEY`, de sesión) lo toma quien llama en una
conexión dedicada `AUTOCOMMIT` (`modules/audit/verify.py`, S4A-D44); las sentencias son constantes
de módulo (`test_sql_literals_constant.py`). Importa solo de `core/audit`, `core/db`, `core/clock` y
`core/context` (S4A-D12).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final, Literal, cast
from uuid import UUID

from sqlalchemy import CHAR, BigInteger, Boolean, Text, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit import ZERO_HASH, AuditEntry, VerifyResult, record, verify_chain
from app.core.clock import current_clock
from app.core.db import Base, CommonColumnsMixin

logger = logging.getLogger("app.audit")

VERIFY_BATCH_SIZE: Final = 500
"""Filas por lote del recorrido (S4A-D47; 500 desde S4A-D120 para dejar el peor bloque síncrono
bajo 100 ms con margen también bajo carga); las pruebas lo bajan con `monkeypatch`."""
VERIFY_MAX_SECONDS: Final = 900
"""Plazo máximo de una verificación en segundo plano (S4A-D44, H-2)."""
AUDIT_VERIFY_LOCK_KEY: Final[int] = 4_270_003
"""Candado asesor de sesión de la verificación; distinto de `MIGRATION_LOCK_KEY` (4_270_001) y de
`AUDIT_CHAIN_LOCK_KEY` (4_270_002)."""
TRY_LOCK_SQL: Final = "SELECT pg_try_advisory_lock(:key)"
UNLOCK_SQL: Final = "SELECT pg_advisory_unlock(:key)"
TRY_LOCK_STATEMENT: Final = text(TRY_LOCK_SQL)
UNLOCK_STATEMENT: Final = text(UNLOCK_SQL)
"""Las dos sentencias ya compiladas: `modules/audit/verify.py` las usa tal cual (el SQL literal
vive solo aquí, `test_sql_literals_constant.py`)."""

VerifySource = Literal["api", "cli"]
VERIFY_SOURCES: Final[tuple[str, ...]] = ("api", "cli")
VERIFICATIONS_TABLE: Final = "audit.verifications"
_LOG = AuditEntry.__table__


class AuditVerification(CommonColumnsMixin, Base):
    """Fila de `audit.verifications` (S4A-D38 + `through_hash`, S4A-D43)."""

    __tablename__ = "verifications"
    __table_args__ = {"schema": "audit"}  # noqa: RUF012

    started_at: Mapped[datetime] = mapped_column(nullable=False)
    finished_at: Mapped[datetime] = mapped_column(nullable=False)
    through_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    through_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    rows_checked: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    broken_at_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    triggered_by: Mapped[UUID] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)


@dataclass(frozen=True)
class VerificationView:
    """Vista inmutable de una verificación. `anchor_seq` (el `through_seq` del ancla usada, `None`
    si no había) y `anchor_broken` (la ruptura la dio el ancla, no la cadena) no se guardan: solo
    los llena `run_verification` para `format_verify_message`."""

    id: UUID
    ok: bool
    rows_checked: int
    through_seq: int
    through_hash: str
    broken_at_seq: int | None
    started_at: datetime
    finished_at: datetime
    triggered_by: UUID
    source: str
    anchor_seq: int | None = None
    anchor_broken: bool = False


def view_of(row: AuditVerification) -> VerificationView:
    """La vista de una fila guardada (sin datos del ancla)."""
    return VerificationView(
        id=row.id,
        ok=row.ok,
        rows_checked=row.rows_checked,
        through_seq=row.through_seq,
        through_hash=row.through_hash,
        broken_at_seq=row.broken_at_seq,
        started_at=row.started_at,
        finished_at=row.finished_at,
        triggered_by=row.triggered_by,
        source=row.source,
    )


async def _pause_between_batches() -> None:
    """Cede el event loop entre lotes (S4A-D47). Las pruebas lo reemplazan para medir o alargar."""
    await asyncio.sleep(0)


async def run_verification(
    session: AsyncSession, *, source: VerifySource, by: UUID
) -> VerificationView:
    """Recorre la cadena, compara con el ancla y guarda el resultado (ver docstring del módulo).
    No confirma: quien llama hace `commit`."""
    started_at = current_clock().now_utc()
    through_seq = int(await session.scalar(select(func.coalesce(func.max(_LOG.c.seq), 0))) or 0)
    anchor = await _anchor(session)
    scan = await _scan_chain(session, through_seq)
    broken_at_seq = scan.broken_at_seq
    anchor_broken = False
    if scan.ok:
        broken_at_seq = await _check_anchor(session, anchor, scan)
        anchor_broken = broken_at_seq is not None
    through_hash = _verified_through_hash(scan, through_seq)
    row = await _persist(
        session,
        started_at=started_at,
        through_seq=through_seq,
        through_hash=through_hash,
        scan=scan,
        broken_at_seq=broken_at_seq,
        source=source,
        by=by,
    )
    if row.ok:
        logger.info(
            "audit anchor", extra={"through_seq": through_seq, "through_hash": through_hash}
        )
    anchor_seq = None if anchor is None else anchor.through_seq
    return replace(view_of(row), anchor_seq=anchor_seq, anchor_broken=anchor_broken)


def format_verify_message(result: VerificationView) -> tuple[str, int]:
    """`("Cadena íntegra ...", 0)` o `("Cadena rota en el registro seq N ...", 1)`. Nunca lleva
    ids, hashes, `before` ni `after` (sale en la CLI y en los logs)."""
    if result.ok:
        texto = (
            f"Cadena íntegra: {result.rows_checked} registros verificados hasta el seq "
            f"{result.through_seq}"
        )
        if result.anchor_seq is None:
            texto += ", sin verificación anterior que comparar"
        return f"{texto}.", 0
    texto = f"Cadena rota en el registro seq {result.broken_at_seq}"
    if result.anchor_broken:
        texto += ": no coincide con la verificación anterior"
    return f"{texto}.", 1


async def _anchor(session: AsyncSession) -> VerificationView | None:
    """La última verificación `ok` (por `finished_at`), o `None`."""
    row = await session.scalar(
        select(AuditVerification)
        .where(AuditVerification.ok.is_(True))
        .order_by(AuditVerification.finished_at.desc(), AuditVerification.created_at.desc())
        .limit(1)
    )
    return None if row is None else view_of(row)


def _verified_through_hash(scan: VerifyResult, through_seq: int) -> str:
    """El `hash` de la fila `through_seq` tal como lo VERIFICÓ el recorrido (`scan.last_hash`), sin
    releerlo con otra sentencia (en `READ COMMITTED` podría ser otro). Con la cadena vacía o rota
    no hay hash verificado: `ZERO_HASH` (una verificación rota nunca es ancla; S4A-D99)."""
    if scan.ok and scan.last_seq == through_seq and scan.last_hash is not None:
        return scan.last_hash
    return ZERO_HASH


async def _hash_at(session: AsyncSession, seq: int) -> str | None:
    """El `hash` guardado de la fila `seq`, o `None` si no existe. Solo lo usa `_check_anchor`."""
    valor = await session.scalar(select(_LOG.c.hash).where(_LOG.c.seq == seq))
    return None if valor is None else str(valor)


async def _read_batch(
    session: AsyncSession, after_seq: int, until_seq: int, limit: int
) -> Sequence[Mapping[str, object]]:
    """Filas con `after_seq < seq <= until_seq`, `seq` ascendente, a lo sumo `limit`. Devuelve
    los `RowMapping` tal cual, sin copiarlos a `dict` (S4A-D127: menos objetos por fila para el
    GC; `verify_chain` solo lee con `get` e `in`)."""
    lote = await session.execute(
        select(_LOG)
        .where(_LOG.c.seq > after_seq, _LOG.c.seq <= until_seq)
        .order_by(_LOG.c.seq)
        .limit(limit)
    )
    return cast("Sequence[Mapping[str, object]]", lote.mappings().all())


async def _scan_chain(session: AsyncSession, through_seq: int) -> VerifyResult:
    """Recorrido por lotes de `VERIFY_BATCH_SIZE` filas (`seq` ascendente) hasta `through_seq`,
    parado en la primera ruptura; cede el loop entre lotes. `VERIFY_BATCH_SIZE` y
    `_pause_between_batches` se leen del módulo en cada uso (las pruebas los cambian).

    Cada lote pide un rango acotado de `seq` (`last_seq < seq <= last_seq + VERIFY_BATCH_SIZE`,
    S4A-D120): el trabajo de la base por lote no depende del plan que elija con estadísticas
    viejas ni de las tuplas muertas fuera del rango. Si el rango entero falta (hueco), la fila
    siguiente que exista entra sola al lote y `verify_chain` marca la ruptura en ella, igual que
    con el rango abierto."""
    last_seq, last_hash, checked = 0, ZERO_HASH, 0
    while last_seq < through_seq:
        if checked:
            await _pause_between_batches()
        tope = min(last_seq + VERIFY_BATCH_SIZE, through_seq)
        filas = await _read_batch(session, last_seq, tope, VERIFY_BATCH_SIZE)
        if not filas and tope < through_seq:  # hueco que cubre todo el rango
            filas = await _read_batch(session, last_seq, through_seq, 1)
        if not filas:  # la cadena acaba antes de `through_seq` (filas borradas entre lotes)
            return VerifyResult(
                False, checked, last_seq + 1, last_seq or None, last_hash if last_seq else None
            )
        parcial = verify_chain(filas, start_prev_hash=last_hash, start_seq=last_seq + 1)
        checked += parcial.rows_checked
        if not parcial.ok:
            return replace(parcial, rows_checked=checked)
        last_seq, last_hash = int(parcial.last_seq or 0), str(parcial.last_hash)
    if through_seq == 0:
        return VerifyResult(True, 0, None)
    return VerifyResult(True, checked, None, last_seq, last_hash)


async def _check_anchor(
    session: AsyncSession, anchor: VerificationView | None, scan: VerifyResult
) -> int | None:
    """`broken_at_seq` por el ancla (H-1), o `None` si el ancla cuadra o no hay ancla: la cadena
    debe llegar hasta `ancla.through_seq` y esa fila debe conservar `ancla.through_hash`."""
    if anchor is None or anchor.through_seq == 0:
        return None
    last_seq = scan.last_seq or 0
    if last_seq < anchor.through_seq:
        return min(last_seq + 1, anchor.through_seq)
    if await _hash_at(session, anchor.through_seq) != anchor.through_hash:
        return anchor.through_seq
    return None


async def _persist(
    session: AsyncSession,
    *,
    started_at: datetime,
    through_seq: int,
    through_hash: str,
    scan: VerifyResult,
    broken_at_seq: int | None,
    source: VerifySource,
    by: UUID,
) -> AuditVerification:
    """Inserta la fila de `audit.verifications` y escribe la fila `verify` de la cadena."""
    finished_at = max(current_clock().now_utc(), started_at)
    row = AuditVerification(
        started_at=started_at,
        finished_at=finished_at,
        through_seq=through_seq,
        through_hash=through_hash,
        rows_checked=scan.rows_checked,
        ok=broken_at_seq is None,
        broken_at_seq=broken_at_seq,
        triggered_by=by,
        source=source,
        created_by=by,
    )
    session.add(row)
    await session.flush()
    await record(
        session,
        action="verify",
        table_name=VERIFICATIONS_TABLE,
        record_id=row.id,
        before=None,
        after={
            "ok": row.ok,
            "rows_checked": row.rows_checked,
            "broken_at_seq": broken_at_seq,
            "through_seq": through_seq,
            "through_hash": through_hash,
            "started_at": started_at,
            "finished_at": finished_at,
            "source": source,
        },
        user_id=by,
    )
    return row
