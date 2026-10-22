"""Fila `reveal` de la auditoría (S2-B6; US-107 y US-074; G-05; DECISIÓN 31 del blueprint).

`core.audit.record(action="reveal", ...)` deja exactamente una fila en la cadena, con el socio
como `subject_member_id` y el nombre del campo revelado, nunca su valor. La tabla de socios nace
en B7: `audit_log` no tiene llave foránea hacia ella, así que el socio es un `uuid4()` (sin
`skip`, M-4). Cuando US-074 cree el endpoint (Sprint 3) se repunta a `tests/factories/members.py`.
"""

from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditEntry, record, verify_chain
from app.core.context import SYSTEM_USER_ID, actor_scope

DOCUMENTO_REVELADO = "1032456789"


async def test_reveal_deja_exactamente_una_fila_sin_el_valor_revelado(
    session: AsyncSession,
) -> None:
    socio = uuid4()
    antes = int(await session.scalar(select(func.count()).select_from(AuditEntry)) or 0)

    with actor_scope(SYSTEM_USER_ID):
        fila = await record(
            session,
            action="reveal",
            table_name="members.members",
            record_id=socio,
            before=None,
            after={"field": "document"},
            subject_member_id=socio,
        )

    t = AuditEntry.__table__
    filas = [
        dict(f)
        for f in (
            await session.execute(select(t).where(t.c.record_id == socio).order_by(t.c.seq))
        ).mappings()
    ]
    assert int(await session.scalar(select(func.count()).select_from(AuditEntry)) or 0) == antes + 1
    (guardada,) = filas
    assert guardada["id"] == fila.id
    assert guardada["action"] == "reveal"
    assert guardada["table_name"] == "members.members"
    assert guardada["subject_member_id"] == socio
    assert guardada["user_id"] == SYSTEM_USER_ID
    assert guardada["before"] is None
    assert guardada["after"] == {"field": "document"}
    assert DOCUMENTO_REVELADO not in json.dumps([guardada["before"], guardada["after"]])

    cadena = [dict(f) for f in (await session.execute(select(t).order_by(t.c.seq))).mappings()]
    assert verify_chain(cadena).ok
