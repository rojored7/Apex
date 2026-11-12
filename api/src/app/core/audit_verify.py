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
- Firmas (S6-A3, US-142; S6-D10, D62, D81; `0022`): `verify_signatures(session, through_seq=)`
  verifica TODAS las firmas de `audit.signatures` del tramo, por lotes de `SIGNATURE_BATCH_SIZE`,
  en proceso con `crypto_keys.public_key` de su `key_id` (cualquier estado) y el constructor de
  `audit_sign.PAYLOAD_BUILDERS[payload_version]`; una firma vale si también su hash es el que la
  cadena guarda hoy. Sin proveedor, keyring ni red (por eso funciona con el custodio sellado).
  `anti_rollback` (pura) compara con el mayor `last_valid_signature_seq` de las verificaciones `ok`
  anteriores y detecta firmas borradas. `signature_state` es pura (`none|ok|invalid`). Con la
  cadena sana, una firma inválida voltea `ok` y fija `broken_at_seq = first_invalid_signature_seq`.
- `format_verify_message(result) -> (texto, código)`: 0 íntegra, 1 rota o con firma inválida (CLI y
  logs); añade el estado de las firmas si la verificación las midió.

El candado de la verificación (`AUDIT_VERIFY_LOCK_KEY`, de sesión) lo toma quien llama en una
conexión dedicada `AUTOCOMMIT` (`modules/audit/verify.py`, S4A-D44); las sentencias son constantes
de módulo (`test_sql_literals_constant.py`). Importa de `core/audit`, `core/audit_sign` (tabla y
constructores de payload), `core/db`, `core/clock` y, para verificar firmas, de `core/crypto`
(`signature`, `models`, `errors`); nunca del bus ni de un proveedor (S4A-D12, S6-D81).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Final, Literal, cast
from uuid import UUID

from sqlalchemy import CHAR, BigInteger, Boolean, Integer, Row, Text, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core import audit_sign
from app.core.audit import (
    ZERO_HASH,
    AuditEntry,
    CanonicalError,
    VerifyResult,
    record,
    verify_chain,
)
from app.core.audit_sign import AuditSignature
from app.core.clock import current_clock
from app.core.crypto.errors import CryptoError
from app.core.crypto.models import CryptoKey
from app.core.crypto.signature import parse_signature, verify_ed25519
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
    # Firmas (S6-A3, S6-D10, `0022`): nulas en las verificaciones anteriores a la migración.
    signatures_checked: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signatures_valid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_invalid_signature_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_valid_signature_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_valid_signature_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_valid_signature_algorithm: Mapped[str | None] = mapped_column(Text, nullable=True)


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
    signatures_checked: int | None = None
    signatures_valid: int | None = None
    first_invalid_signature_seq: int | None = None
    last_valid_signature_seq: int | None = None
    last_valid_signature_at: datetime | None = None
    last_valid_signature_algorithm: str | None = None


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
        signatures_checked=row.signatures_checked,
        signatures_valid=row.signatures_valid,
        first_invalid_signature_seq=row.first_invalid_signature_seq,
        last_valid_signature_seq=row.last_valid_signature_seq,
        last_valid_signature_at=row.last_valid_signature_at,
        last_valid_signature_algorithm=row.last_valid_signature_algorithm,
    )


SignatureState = Literal["none", "ok", "invalid"]
SIGNATURE_BATCH_SIZE: Final = 100
"""Firmas por lote de `verify_signatures` (S6-D62)."""
SIGNATURE_ALGORITHM: Final = "Ed25519"
"""Único algoritmo que se verifica hoy con la clave pública guardada (`ML-DSA-65`: EP-26)."""
_SIG = AuditSignature.__table__


@dataclass(frozen=True)
class SignatureVerdict:
    """Veredicto de las firmas de un tramo (S6-D10, D62). `state` sale de `signature_state`."""

    state: SignatureState
    checked: int
    valid: int
    first_invalid_seq: int | None
    last_valid_seq: int | None
    last_valid_at: datetime | None
    last_valid_algorithm: str | None


def signature_state(checked: int, valid: int, first_invalid_seq: int | None) -> SignatureState:
    """Pura: `none` sin firmas, `invalid` con alguna inválida, `ok` si todas verifican."""
    if first_invalid_seq is not None or valid < checked:
        return "invalid"
    return "none" if checked == 0 else "ok"


def anti_rollback(
    prev_last_valid_seq: int | None, max_signed_seq: int | None, signatures_count: int
) -> bool:
    """Pura: `True` si hubo retroceso (firmas borradas desde la verificación anterior)."""
    if prev_last_valid_seq is None:
        return False
    if max_signed_seq is None or signatures_count == 0:
        return True
    return max_signed_seq < prev_last_valid_seq


def _signature_is_valid(
    fila: Row[Any], public_key: str | None, stored_chain_hash: str | None
) -> bool:
    """Una firma vale si firma el hash que la cadena tiene HOY en su `through_seq`, su blob
    corresponde a su fila y `Ed25519` verifica con la clave pública guardada. Cualquier defecto
    (blob ilegible, versión sin constructor, llave ausente) es «inválida», nunca una excepción."""
    constructor = audit_sign.PAYLOAD_BUILDERS.get(fila.payload_version)
    if constructor is None or public_key is None or fila.algorithm != SIGNATURE_ALGORITHM:
        return False
    if stored_chain_hash is None or str(stored_chain_hash) != str(fila.chain_hash):
        return False
    try:
        partes = parse_signature(fila.signature)
        payload = constructor(fila.through_seq, str(fila.chain_hash))
    except (CryptoError, CanonicalError, ValueError, TypeError):
        return False
    if partes.key_id != fila.key_id or partes.alg != fila.algorithm:
        return False
    return verify_ed25519(public_key, payload, partes.sig)


async def _public_keys(session: AsyncSession) -> dict[UUID, str | None]:
    """`{key_id: public_key}` de todas las filas `sign`, en cualquier estado (D81)."""
    filas = await session.execute(
        select(CryptoKey.id, CryptoKey.public_key).where(CryptoKey.purpose == "sign")
    )
    return {llave: publica for llave, publica in filas.all()}


async def _signature_batch(
    session: AsyncSession, after_seq: int, through_seq: int
) -> Sequence[Row[Any]]:
    """Hasta `SIGNATURE_BATCH_SIZE` firmas con `after_seq < through_seq <= through_seq`, ascendente
    (columnas, no entidades: nunca una fila obsoleta del identity map)."""
    lote = await session.execute(
        select(
            _SIG.c.through_seq,
            _SIG.c.hash.label("chain_hash"),
            _SIG.c.signature,
            _SIG.c.key_id,
            _SIG.c.algorithm,
            _SIG.c.payload_version,
            _SIG.c.signed_at,
        )
        .where(_SIG.c.through_seq > after_seq, _SIG.c.through_seq <= through_seq)
        .order_by(_SIG.c.through_seq)
        .limit(SIGNATURE_BATCH_SIZE)
    )
    return cast("Sequence[Row[Any]]", lote.all())


async def _stored_hashes(session: AsyncSession, seqs: list[int]) -> dict[int, str]:
    """`{seq: hash}` que la cadena guarda HOY para esos `seq`."""
    filas = await session.execute(select(_LOG.c.seq, _LOG.c.hash).where(_LOG.c.seq.in_(seqs)))
    return {int(seq): str(hash_) for seq, hash_ in filas.all()}


async def verify_signatures(session: AsyncSession, *, through_seq: int) -> SignatureVerdict:
    """Todas las firmas con `through_seq` dentro del tramo, por lotes de 100, con la clave pública
    guardada en `crypto_keys.public_key` de su `key_id` (cualquier estado de la llave), en proceso:
    sin proveedor, sin keyring y sin red (S6-D62, D81)."""
    llaves = await _public_keys(session)
    checked = valid = last_seq = 0
    first_invalid: int | None = None
    ultima: Row[Any] | None = None
    while lote := await _signature_batch(session, last_seq, through_seq):
        if checked:
            await _pause_between_batches()
        guardados = await _stored_hashes(session, [int(fila.through_seq) for fila in lote])
        for fila in lote:
            checked += 1
            if _signature_is_valid(
                fila, llaves.get(fila.key_id), guardados.get(int(fila.through_seq))
            ):
                valid += 1
                ultima = fila
            elif first_invalid is None:
                first_invalid = int(fila.through_seq)
        last_seq = int(lote[-1].through_seq)
    return SignatureVerdict(
        signature_state(checked, valid, first_invalid),
        checked,
        valid,
        first_invalid,
        None if ultima is None else int(ultima.through_seq),
        None if ultima is None else ultima.signed_at,
        None if ultima is None else str(ultima.algorithm),
    )


async def _with_anti_rollback(
    session: AsyncSession, veredicto: SignatureVerdict, through_seq: int
) -> SignatureVerdict:
    """Aplica la regla anti-retroceso (S6-D62): si una verificación `ok` anterior dio por válida una
    firma más alta que la mayor que queda (o ya no hay firmas), el veredicto es `invalid` con
    `first_invalid_seq` = la firma que faltaba. Solo base de datos: sin proveedor ni red."""
    previo = await session.scalar(
        select(func.max(AuditVerification.last_valid_signature_seq)).where(
            AuditVerification.ok.is_(True),
            AuditVerification.last_valid_signature_seq
            <= through_seq,  # tramo menor: no es retroceso
        )
    )
    maximo = await session.scalar(
        select(func.max(_SIG.c.through_seq)).where(_SIG.c.through_seq <= through_seq)
    )
    if previo is None or not anti_rollback(previo, maximo, veredicto.checked):
        return veredicto
    primera = (
        previo if veredicto.first_invalid_seq is None else min(previo, veredicto.first_invalid_seq)
    )
    return replace(veredicto, state="invalid", first_invalid_seq=primera)


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
    firmas = await _with_anti_rollback(
        session, await verify_signatures(session, through_seq=through_seq), through_seq
    )
    if broken_at_seq is None and firmas.state == "invalid":
        broken_at_seq = firmas.first_invalid_seq  # cadena sana: manda la primera firma inválida
    through_hash = _verified_through_hash(scan, through_seq)
    row = await _persist(
        session,
        started_at=started_at,
        through_seq=through_seq,
        through_hash=through_hash,
        scan=scan,
        signatures=firmas,
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
    """`("Cadena íntegra ...", 0)` o `("Cadena rota en el registro seq N ...", 1)`, más el estado de
    las firmas si la verificación las midió (`Firmas: N de N válidas`, `Sin firmas que verificar`,
    `Firma inválida ...`). Nunca lleva ids, hashes, algoritmo, blobs, `before` ni `after` (sale en
    la CLI y en los logs)."""
    if result.ok:
        texto = (
            f"Cadena íntegra: {result.rows_checked} registros verificados hasta el seq "
            f"{result.through_seq}"
        )
        if result.anchor_seq is None:
            texto += ", sin verificación anterior que comparar"
        codigo = 0
    elif _only_signatures_broke(result):
        # Cadena sana: el prefijo es la firma (S6-A3, revisión de seguridad), no «Cadena rota».
        return _signatures_text(result) or "", 1
    else:
        texto = f"Cadena rota en el registro seq {result.broken_at_seq}"
        if result.anchor_broken:
            texto += ": no coincide con la verificación anterior"
        codigo = 1
    firmas = _signatures_text(result)
    return (f"{texto}." if firmas is None else f"{texto}. {firmas}"), codigo


def _only_signatures_broke(result: VerificationView) -> bool:
    """La verificación falló solo por las firmas: `broken_at_seq` es la primera firma inválida."""
    checked, valid = result.signatures_checked, result.signatures_valid
    if checked is None or valid is None or result.anchor_broken:
        return False
    estado = signature_state(checked, valid, result.first_invalid_signature_seq)
    return estado == "invalid" and result.broken_at_seq == result.first_invalid_signature_seq


def _signatures_text(result: VerificationView) -> str | None:
    """La frase de firmas, o `None` si la verificación es anterior a `0022` (sin datos)."""
    checked, valid = result.signatures_checked, result.signatures_valid
    if checked is None or valid is None:
        return None
    estado = signature_state(checked, valid, result.first_invalid_signature_seq)
    if estado == "invalid":
        return (
            f"Firma inválida en el seq {result.first_invalid_signature_seq}: "
            f"{valid} de {checked} válidas."
        )
    if estado == "none":
        return "Sin firmas que verificar."
    hasta = result.last_valid_signature_seq
    return f"Firmas: {valid} de {checked} válidas" + (
        "." if hasta is None else f", la última hasta el seq {hasta}."
    )


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


def _signature_columns(veredicto: SignatureVerdict) -> dict[str, Any]:
    """Las seis columnas de firmas de `audit.verifications` (`0022`) para un veredicto."""
    return {
        "signatures_checked": veredicto.checked,
        "signatures_valid": veredicto.valid,
        "first_invalid_signature_seq": veredicto.first_invalid_seq,
        "last_valid_signature_seq": veredicto.last_valid_seq,
        "last_valid_signature_at": veredicto.last_valid_at,
        "last_valid_signature_algorithm": veredicto.last_valid_algorithm,
    }


async def _persist(
    session: AsyncSession,
    *,
    started_at: datetime,
    through_seq: int,
    through_hash: str,
    scan: VerifyResult,
    signatures: SignatureVerdict,
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
        **_signature_columns(signatures),
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
