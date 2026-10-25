"""`sell.lock_membership` y `service.get_payment_target` (S3-B1; D1, D-3, S3-D59).

Nacen en B1 (Verde) aunque el gate de pagos que los consume llega en B4:
- `lock_membership` devuelve la fila con `FOR UPDATE` y `populate_existing=True` (relee de la base
  aunque el objeto ya esté en el mapa de identidad) y `None` si no existe;
- `get_payment_target` dice si la membresía existe, si está anulada y de qué socio es (el
  `member_id` que `payments` copiará, D9), sin leerlo nunca del cuerpo de la petición.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.modules.memberships import service
from app.modules.memberships.schemas import PaymentTarget
from app.modules.memberships.sell import lock_membership
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan


async def test_lock_membership_devuelve_none_si_no_existe(session: AsyncSession) -> None:
    assert await lock_membership(session, uuid4()) is None


async def test_lock_membership_relee_la_fila_de_la_base(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan, status="pending_payment")
    await session.execute(
        text("UPDATE memberships.memberships SET status = 'active' WHERE id = :id"),
        {"id": membresia.id},
    )
    bloqueada = await lock_membership(session, membresia.id)
    assert bloqueada is membresia  # el mismo objeto del mapa de identidad...
    assert bloqueada.status == "active"  # ...refrescado por `populate_existing`


async def test_get_payment_target_de_una_inexistente(session: AsyncSession) -> None:
    assert await service.get_payment_target(session, uuid4()) == PaymentTarget(
        exists=False, cancelled=False, member_id=None
    )


async def test_get_payment_target_de_una_vigente_y_de_una_anulada(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    vigente = await make_membership(session, socio, plan, status="active")
    anulada = await make_membership(
        session, socio, plan, status="cancelled", start=reloj.today_bogota()
    )
    assert await service.get_payment_target(session, vigente.id) == PaymentTarget(
        exists=True, cancelled=False, member_id=socio.id
    )
    assert await service.get_payment_target(session, anulada.id) == PaymentTarget(
        exists=True, cancelled=True, member_id=socio.id
    )
