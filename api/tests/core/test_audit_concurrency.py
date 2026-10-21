"""Dos transacciones auditan a la vez y la cadena sigue válida (US-015 T10, criterio 5).

Usa dos conexiones independientes que confirman de verdad, fuera del savepoint del
fixture `session`; limpia la tabla con `DISABLE TRIGGER USER` + `TRUNCATE`, solo en
pruebas.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.audit import AuditEntry, AuditRow, append_entry, verify_chain

USER = UUID("00000000-0000-0000-0000-000000000001")


async def _vaciar(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE audit.audit_log DISABLE TRIGGER USER"))
        await conn.execute(text("TRUNCATE audit.audit_log"))
        await conn.execute(text("ALTER TABLE audit.audit_log ENABLE TRIGGER USER"))


@pytest.fixture
async def motor_limpio(engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    await _vaciar(engine)
    try:
        yield engine
    finally:
        await _vaciar(engine)


async def _auditar(engine: AsyncEngine, n: int) -> AuditRow:
    async with engine.begin() as conn:
        return await conn.run_sync(
            lambda sync_conn: append_entry(
                sync_conn,
                action="insert",
                table_name="members.members",
                record_id=uuid4(),
                before=None,
                after={"n": n},
                user_id=USER,
            )
        )


async def test_dos_transacciones_concurrentes_no_repiten_prev_hash(
    motor_limpio: AsyncEngine,
) -> None:
    a, b = await asyncio.gather(_auditar(motor_limpio, 1), _auditar(motor_limpio, 2))
    assert {a.seq, b.seq} == {1, 2}
    assert a.prev_hash != b.prev_hash
    primera, segunda = sorted([a, b], key=lambda r: r.seq)
    assert segunda.prev_hash == primera.hash

    async with motor_limpio.connect() as conn:
        consulta = select(AuditEntry.__table__).order_by(AuditEntry.__table__.c.seq)
        filas: list[dict[str, Any]] = [dict(m) for m in (await conn.execute(consulta)).mappings()]
    assert [f["seq"] for f in filas] == [1, 2]
    assert verify_chain(filas).ok is True


async def test_diez_transacciones_concurrentes_dejan_cadena_valida(
    motor_limpio: AsyncEngine,
) -> None:
    filas_escritas = await asyncio.gather(*(_auditar(motor_limpio, n) for n in range(10)))
    assert sorted(r.seq for r in filas_escritas) == list(range(1, 11))
    async with motor_limpio.connect() as conn:
        consulta = select(AuditEntry.__table__).order_by(AuditEntry.__table__.c.seq)
        filas = [dict(m) for m in (await conn.execute(consulta)).mappings()]
    assert verify_chain(filas).ok is True
