"""`sell.lock_membership` y `service.membership_payability` (S3-B1 y S3-B4; D1, D-3, S3-D41,
S3-D59).

- `lock_membership` devuelve la fila con `FOR UPDATE` y `populate_existing=True` (relee de la base
  aunque el objeto ya esté en el mapa de identidad) y `None` si no existe;
- `service.membership_payability` (el gate real que `memberships/service.py` registra) dice si
  la membresía existe, si está anulada, de qué socio es (el `member_id` que `payments` copiará,
  D9, sin leerlo nunca del cuerpo de la petición) y su `agreed_price_cop`, como
  `payments.service.MembershipPayability` (S3-D41).

Antes `test_payment_target.py`: la revisión de Fase 4 del Sprint 3 (PL2) quitó
`get_payment_target` y `PaymentTarget`, el contrato de B1 que el gate de B4 reemplazó; sus dos
pruebas se fueron con él y `test_el_contrato_de_b1_ya_no_existe` lo fija.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.modules.memberships import schemas, service
from app.modules.memberships.sell import lock_membership
from app.modules.payments.service import MembershipPayability
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


def test_el_contrato_de_b1_ya_no_existe() -> None:
    """PL2: nada de producción usaba `get_payment_target` ni `PaymentTarget`."""
    assert not hasattr(service, "get_payment_target")
    assert "get_payment_target" not in service.__all__
    assert not hasattr(schemas, "PaymentTarget")


# `membership_payability`, el gate real de pagos (S3-B4, D1, S3-D41) -------------------------------


async def test_membership_payability_de_una_inexistente(session: AsyncSession) -> None:
    assert await service.membership_payability(session, uuid4()) == MembershipPayability(
        exists=False, cancelled=False, member_id=None, agreed_price_cop=None
    )


async def test_membership_payability_lleva_el_precio_pactado_de_la_fila(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """El precio es el pactado de la membresía (no el del plan, que pudo cambiar después)."""
    socio = await make_member(session)
    plan = await make_plan(session)
    vigente = await make_membership(session, socio, plan, status="active", price=99_000)
    anulada = await make_membership(
        session, socio, plan, status="cancelled", start=reloj.today_bogota()
    )
    assert await service.membership_payability(session, vigente.id) == MembershipPayability(
        exists=True, cancelled=False, member_id=socio.id, agreed_price_cop=99_000
    )
    assert await service.membership_payability(session, anulada.id) == MembershipPayability(
        exists=True, cancelled=True, member_id=socio.id, agreed_price_cop=120_000
    )


async def test_membership_payability_toma_la_fila_con_el_candado(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """Pasa por `lock_membership` (`FOR UPDATE`, `populate_existing`): ve lo que la base tiene
    aunque el objeto del mapa de identidad esté viejo."""
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan, status="active")
    await session.execute(
        text(
            "UPDATE memberships.memberships SET status = 'cancelled', "
            "cancel_reason = 'Anulada en la prueba', cancelled_by = created_by, "
            "cancelled_at = now() WHERE id = :id"
        ),
        {"id": membresia.id},
    )
    gate = await service.membership_payability(session, membresia.id)
    assert gate.cancelled is True
    assert membresia.status == "cancelled"
