"""Fábrica de la cadena de auditoría (plan del Sprint 4A, sección 2, bloque B3; S4A-D69).

- `make_audit_chain(session, n, *, table_name, user_id)`: agrega `n` filas a continuación de la
  última (`seq` y `prev_hash` reales) con `chain_hash` de `core/audit.py` (la misma `canonical`),
  por lotes de `INSERT_BATCH` con `insert(AuditEntry.__table__)` de Core (los 100.000 de la prueba
  perf no pasan por `record()`), y confirma (con la `session` de savepoint libera el savepoint).
  Cada fila lleva `after = {"n": seq, "marca": MARCA_AFTER}`: las pruebas de la CLI comprueban que
  esa marca nunca sale en la salida. Devuelve el último `seq`.
- `tamper_row(session, seq, column, value, *, rehash=False)`: altera una columna de una fila con
  `ALTER TABLE ... DISABLE TRIGGER USER` dentro de la transacción de quien llama y vuelve a encender
  los dos triggers por nombre con `ENABLE ALWAYS` (regla E1 del Sprint 3). Con `rehash=True`
  recalcula `hash` y `prev_hash` desde esa fila hasta el final: la cola queda internamente válida
  pero distinta (el caso "cola reemplazada" de H-1).
- `drop_rows(session, seqs)` y `drop_tail(session, n)`: borran filas con la misma regla.
- `table_digest(session, *, hasta=None)`: `md5` de todas las filas (texto de la fila completa, en
  orden de `seq`) hasta `hasta`: "la verificación no cambia ninguna fila".
- `hash_of(session, seq)` y `last_seq(session)`: lecturas de apoyo.
- `empty_audit(session)`: vacía `audit.audit_log` y `audit.verifications` dentro de la transacción
  de quien llama (con la `session` de la prueba se revierte al terminar).
`test_no_trigger_tampering.py` solo barre `app/`; las pruebas pueden apagar triggers.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import ZERO_HASH, AuditEntry, chain_hash
from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID
from tests.conftest import LIMPIAR_VERIFICATIONS

INSERT_BATCH: Final = 5000
MARCA_AFTER: Final = "marca-de-auditoria-7731"
"""Valor que viaja en `after` de cada fila de la fábrica; nunca debe salir en la CLI ni en logs."""

APAGAR: Final = "ALTER TABLE audit.audit_log DISABLE TRIGGER USER"
ENCENDER: Final = (
    "ALTER TABLE audit.audit_log ENABLE ALWAYS TRIGGER audit_log_forbid_mutation",
    "ALTER TABLE audit.audit_log ENABLE ALWAYS TRIGGER audit_log_forbid_truncate",
)
TABLA = AuditEntry.__table__
DIGEST_SQL: Final = (
    "SELECT md5(coalesce(string_agg(t::text, '|' ORDER BY t.seq), '')) "
    "FROM audit.audit_log t WHERE t.seq <= :hasta"
)


async def last_seq(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.coalesce(func.max(TABLA.c.seq), 0))) or 0)


async def hash_of(session: AsyncSession, seq: int) -> str | None:
    return await session.scalar(select(TABLA.c.hash).where(TABLA.c.seq == seq))


async def _ultimo(session: AsyncSession) -> tuple[int, str]:
    fila = (
        await session.execute(
            select(TABLA.c.seq, TABLA.c.hash).order_by(TABLA.c.seq.desc()).limit(1)
        )
    ).first()
    return (int(fila.seq), str(fila.hash)) if fila is not None else (0, ZERO_HASH)


def _fila(seq: int, prev_hash: str, at: Any, table_name: str, user_id: UUID) -> dict[str, Any]:
    valores: dict[str, Any] = {
        "id": uuid4(),
        "seq": seq,
        "at": at,
        "user_id": user_id,
        "action": "insert",
        "table_name": table_name,
        "record_id": uuid4(),
        "before": None,
        "after": {"n": seq, "marca": MARCA_AFTER},
    }
    valores["prev_hash"] = prev_hash
    valores["hash"] = chain_hash(prev_hash, valores)
    valores.update(created_at=at, updated_at=at, created_by=user_id)
    return valores


async def make_audit_chain(
    session: AsyncSession,
    n: int,
    *,
    table_name: str = "members.members",
    user_id: UUID = SYSTEM_USER_ID,
) -> int:
    """Agrega `n` filas válidas tras la última y confirma; devuelve el último `seq`."""
    seq, prev = await _ultimo(session)
    base = current_clock().now_utc() - timedelta(milliseconds=n)
    lote: list[dict[str, Any]] = []
    for i in range(1, n + 1):
        fila = _fila(seq + i, prev, base + timedelta(milliseconds=i), table_name, user_id)
        prev = fila["hash"]
        lote.append(fila)
        if len(lote) == INSERT_BATCH:
            await session.execute(insert(TABLA), lote)
            lote = []
    if lote:
        await session.execute(insert(TABLA), lote)
    await session.commit()
    return seq + n


async def _apagar(session: AsyncSession) -> None:
    await session.execute(text(APAGAR))


async def _encender(session: AsyncSession) -> None:
    for sql in ENCENDER:
        await session.execute(text(sql))


async def _rehash_from(session: AsyncSession, seq: int) -> None:
    """Recalcula `prev_hash` y `hash` desde `seq` hasta el final (con los triggers apagados)."""
    prev = await hash_of(session, seq - 1) if seq > 1 else ZERO_HASH
    filas = (
        (await session.execute(select(TABLA).where(TABLA.c.seq >= seq).order_by(TABLA.c.seq)))
        .mappings()
        .all()
    )
    for fila in filas:
        valores = dict(fila)
        nuevo = chain_hash(str(prev), valores)
        await session.execute(
            update(TABLA).where(TABLA.c.seq == valores["seq"]).values(prev_hash=prev, hash=nuevo)
        )
        prev = nuevo


async def tamper_row(
    session: AsyncSession, seq: int, column: str, value: Any, *, rehash: bool = False
) -> None:
    """Altera `column` de la fila `seq` (y, con `rehash`, recalcula la cola) y confirma."""
    await _apagar(session)
    await session.execute(update(TABLA).where(TABLA.c.seq == seq).values({column: value}))
    if rehash:
        await _rehash_from(session, seq)
    await _encender(session)
    await session.commit()


async def drop_rows(session: AsyncSession, seqs: Iterable[int]) -> None:
    """Borra las filas `seqs` (con los triggers apagados) y confirma."""
    await _apagar(session)
    await session.execute(TABLA.delete().where(TABLA.c.seq.in_(list(seqs))))
    await _encender(session)
    await session.commit()


async def drop_tail(session: AsyncSession, n: int) -> list[int]:
    """Borra las `n` filas de `seq` más alto y confirma; devuelve los `seq` borrados."""
    ultimo = await last_seq(session)
    borrados = list(range(max(1, ultimo - n + 1), ultimo + 1))
    await drop_rows(session, borrados)
    return borrados


async def table_digest(session: AsyncSession, *, hasta: int | None = None) -> str:
    """`md5` de las filas completas de `audit.audit_log` hasta `hasta` (todas si es `None`)."""
    limite = hasta if hasta is not None else await last_seq(session)
    return str(await session.scalar(text(DIGEST_SQL), {"hasta": limite}))


async def empty_audit(session: AsyncSession) -> None:
    """Vacía `audit.audit_log` y `audit.verifications` en la transacción de quien llama."""
    await session.execute(text(LIMPIAR_VERIFICATIONS))
    await _apagar(session)
    await session.execute(TABLA.delete())
    await _encender(session)
