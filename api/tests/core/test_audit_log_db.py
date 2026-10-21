"""`audit.audit_log` con PostgreSQL real (US-015 T9): cadena, trigger append-only y UTC."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import ZERO_HASH, AuditEntry, record, verify_chain

USER = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
async def tabla_vacia(session: AsyncSession) -> AsyncSession:
    """Vacía la tabla dentro del savepoint de la prueba (TRUNCATE es transaccional)."""
    await session.execute(text("ALTER TABLE audit.audit_log DISABLE TRIGGER USER"))
    await session.execute(text("TRUNCATE audit.audit_log"))
    await session.execute(text("ALTER TABLE audit.audit_log ENABLE TRIGGER USER"))
    return session


async def _filas(session: AsyncSession) -> Sequence[dict[str, Any]]:
    consulta = select(AuditEntry.__table__).order_by(AuditEntry.__table__.c.seq)
    return [dict(m) for m in (await session.execute(consulta)).mappings().all()]


async def _tres(session: AsyncSession) -> None:
    for n in range(1, 4):
        await record(
            session,
            action="insert",
            table_name="members.members",
            record_id=uuid4(),
            before=None,
            after={"n": n, "nombre": "Ñandú"},
            user_id=USER,
        )


async def test_tres_record_encadenan_seq_1_2_3(tabla_vacia: AsyncSession) -> None:
    await _tres(tabla_vacia)
    filas = await _filas(tabla_vacia)
    assert [f["seq"] for f in filas] == [1, 2, 3]
    assert filas[0]["prev_hash"] == ZERO_HASH
    assert filas[1]["prev_hash"] == filas[0]["hash"]
    assert filas[2]["prev_hash"] == filas[1]["hash"]
    assert len({f["hash"] for f in filas}) == 3
    assert verify_chain(filas).ok is True
    assert all(f["created_at"] == f["at"] == f["updated_at"] for f in filas)
    assert all(f["created_by"] == f["user_id"] == USER for f in filas)


async def test_record_devuelve_la_fila_escrita(tabla_vacia: AsyncSession) -> None:
    fila = await record(
        tabla_vacia,
        action="verify",
        table_name="audit.audit_log",
        record_id=None,
        before=None,
        after=None,
        user_id=USER,
    )
    guardada = (await _filas(tabla_vacia))[0]
    assert fila.seq == 1 and fila.prev_hash == ZERO_HASH
    assert fila.hash == guardada["hash"] and fila.id == guardada["id"]
    assert guardada["record_id"] is None and guardada["after"] is None


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE audit.audit_log SET action = 'insert'",
        "DELETE FROM audit.audit_log",
        "TRUNCATE audit.audit_log",
    ],
    ids=["update", "delete", "truncate"],
)
async def test_la_base_rechaza_update_delete_y_truncate(tabla_vacia: AsyncSession, sql: str) -> None:
    await _tres(tabla_vacia)
    with pytest.raises(DBAPIError) as excinfo:
        async with tabla_vacia.begin_nested():
            await tabla_vacia.execute(text(sql))
    assert "append-only" in str(excinfo.value)
    assert len(await _filas(tabla_vacia)) == 3


async def test_accion_fuera_del_check_es_rechazada(tabla_vacia: AsyncSession) -> None:
    with pytest.raises(DBAPIError):
        async with tabla_vacia.begin_nested():
            await record(
                tabla_vacia,
                action="borrar",  # type: ignore[arg-type]
                table_name="x",
                record_id=None,
                before=None,
                after=None,
                user_id=USER,
            )


async def test_fila_alterada_rompe_la_cadena_en_seq_2(tabla_vacia: AsyncSession) -> None:
    await _tres(tabla_vacia)
    await tabla_vacia.execute(
        text("ALTER TABLE audit.audit_log DISABLE TRIGGER audit_log_forbid_mutation")
    )
    await tabla_vacia.execute(
        text("""UPDATE audit.audit_log SET "after" = '{"n": 99}'::jsonb WHERE seq = 2""")
    )
    resultado = verify_chain(await _filas(tabla_vacia))
    assert resultado.ok is False
    assert resultado.broken_at_seq == 2
    assert resultado.rows_checked == 2  # se detiene en la primera ruptura


async def test_at_es_timestamptz_en_utc(tabla_vacia: AsyncSession) -> None:
    await _tres(tabla_vacia)
    tipo = await tabla_vacia.scalar(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = 'audit' AND table_name = 'audit_log' AND column_name = 'at'"
        )
    )
    assert tipo == "timestamp with time zone"
    fila = (await _filas(tabla_vacia))[0]
    assert fila["at"].utcoffset() is not None
    assert fila["at"].astimezone(UTC) == fila["at"]
