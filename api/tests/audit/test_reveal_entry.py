"""Fila `reveal` de la auditoría con el service real (S2-B6, S3-B10; US-107 y US-074; G-05, D19,
L-12, S2-D31).

`members.service.reveal` sobre un socio de la fábrica (`make_member`, ya no un `uuid4()`) deja
exactamente una fila nueva en la cadena: `action="reveal"`, `table_name="members.members"`, el
socio como `record_id` y `subject_member_id`, el actor como `user_id`, `before` nulo y
`after == {"field": <campo>, "ip": <ip>}`. El valor revelado no está en `before` ni en `after`, y
la cadena completa verifica (`verify_chain`).
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditEntry, verify_chain
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.modules.members import service
from tests.factories.members import KNOWN, KNOWN_NORMALIZED, make_member

ACTOR = UUID("0000000a-0000-4000-8000-0000000b1001")
IP = "198.51.100.23"


async def _total(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(AuditEntry)) or 0)


async def test_reveal_deja_exactamente_una_fila_sin_el_valor_revelado(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    session.expunge_all()  # como una petición nueva
    antes = await _total(session)

    with actor_scope(ACTOR):
        salida = await service.reveal(session, socio.id, "document", ip=IP)
        await session.commit()

    assert salida.value == KNOWN["document"]
    t = AuditEntry.__table__
    filas = [
        dict(f)
        for f in (
            await session.execute(
                select(t).where(t.c.record_id == socio.id, t.c.action == "reveal")
            )
        ).mappings()
    ]
    assert await _total(session) == antes + 1
    (guardada,) = filas
    assert guardada["table_name"] == "members.members"
    assert guardada["subject_member_id"] == socio.id
    assert guardada["user_id"] == ACTOR
    assert guardada["before"] is None
    assert guardada["after"] == {"field": "document", "ip": IP}
    volcado = json.dumps([guardada["before"], guardada["after"]])
    for valor in KNOWN_NORMALIZED:
        assert valor not in volcado, valor
    assert "apx1." not in volcado

    cadena = [dict(f) for f in (await session.execute(select(t).order_by(t.c.seq))).mappings()]
    assert verify_chain(cadena).ok
