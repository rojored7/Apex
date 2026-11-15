"""Puntos M1, L4 y L5 de la revisión de S7-C2 (S7-C2b). Rojo C2b.

- M1: la renovación solo sale detrás de una tiquetera agotada por check-in (su fin es hoy, el
  recorte nunca lo deja después); una heredada agotada sin recorte (fin futuro) sigue
  bloqueando (S7-D30), también en la vista previa.
- L4: `MembershipExpired` no se emite si la fila ya estaba vencida (lo emitió el job diario).
- L5: los handlers comprueban que la membresía del evento sea del socio del evento.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import actor_scope
from app.modules.classes import service as classes_service
from app.modules.memberships import service
from app.modules.memberships.exceptions import MembershipOverlap
from app.modules.memberships.service import ClassConsumed, ClassReturned, MembershipExpired
from tests.conftest import CapturarEventos, CrearUsuario
from tests.factories.members import make_member, make_members
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import vender

HOY = date(2026, 10, 21)
ACTOR = UUID("00000000-0000-0000-0000-000000000001")

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def _tiquetera(session: AsyncSession, socio: Any, **cambios: Any) -> Any:
    plan = await make_plan(session, name=f"Tiquetera {uuid4()}", kind="classes", class_count=12)
    valores: dict[str, Any] = {
        "status": "active",
        "start": date(2026, 10, 1),
        "end": date(2026, 11, 30),
    }
    valores.update(cambios)
    return await make_membership(session, socio, plan, **valores)


async def _fila(session: AsyncSession, membership_id: UUID) -> dict[str, Any]:
    resultado = await session.execute(
        text(
            "SELECT classes_remaining, end_date, original_end_date, status "
            "FROM memberships.memberships WHERE id = :i"
        ),
        {"i": membership_id},
    )
    return dict(resultado.mappings().one())


def _entrada(member_id: UUID, membership_id: UUID | None, estado: str) -> Any:
    return classes_service.MemberCheckedIn(
        attendance_id=uuid4(),
        session_id=uuid4(),
        member_id=member_id,
        membership_id=membership_id,
        membership_status=estado,
        flags=(),
    )


def _quitada(member_id: UUID, membership_id: UUID | None, estado: str) -> Any:
    return classes_service.AttendanceRemoved(
        attendance_id=uuid4(),
        session_id=uuid4(),
        member_id=member_id,
        membership_id=membership_id,
        membership_status=estado,
    )


# M1 ------------------------------------------------------------------------------------------


async def test_renovar_sobre_una_agotada_heredada_sin_recorte_sigue_bloqueando(
    session: AsyncSession,
) -> None:
    """Fin futuro con 0 clases y sin `original_end_date`: no es un recorte; `renew` no la salta."""
    socio = await make_member(session)
    plan = await make_plan(session, name="Tiquetera", kind="classes", class_count=4)
    agotada = await make_membership(
        session,
        socio,
        plan,
        status="active",
        start=date(2026, 10, 1),
        end=date(2026, 11, 30),
        classes_remaining=0,
    )
    with pytest.raises(MembershipOverlap) as error:
        await vender(session, ACTOR, member_id=socio.id, plan_id=plan.id, renew=True)
    assert error.value.existing_id == agotada.id


async def test_la_vista_previa_sobre_una_heredada_agotada_sigue_bloqueando(
    session: AsyncSession,
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session, name="Tiquetera", kind="classes", class_count=4)
    await make_membership(
        session,
        socio,
        plan,
        status="active",
        start=date(2026, 10, 1),
        end=date(2026, 11, 30),
        classes_remaining=0,
    )
    with pytest.raises(MembershipOverlap):
        await service.renewal_preview(session, member_id=socio.id, plan_id=plan.id)


async def test_la_vista_previa_tras_agotar_hoy_empieza_manana(session: AsyncSession) -> None:
    """Lo que sí se salta: una tiquetera con fin hoy (el recorte de la última clase)."""
    socio = await make_member(session)
    plan = await make_plan(session, name="Tiquetera", kind="classes", class_count=4)
    await make_membership(
        session,
        socio,
        plan,
        status="expired",
        start=date(2026, 10, 1),
        end=HOY,
        classes_remaining=0,
    )
    previa = await service.renewal_preview(session, member_id=socio.id, plan_id=plan.id)
    assert previa.start_date == date(2026, 10, 22)


# L4 ------------------------------------------------------------------------------------------


async def test_agotar_una_fila_ya_vencida_no_emite_membership_expired(
    session: AsyncSession, usuario_real: CrearUsuario, capturar_eventos: CapturarEventos
) -> None:
    """El job diario ya la dejó `expired` y emitió el evento: la última clase no lo repite."""
    coach = await usuario_real("coach")
    socio = await make_member(session)
    tiquetera = await _tiquetera(session, socio, status="expired", classes_remaining=1)
    consumidos = capturar_eventos(ClassConsumed)
    vencidos = capturar_eventos(MembershipExpired)
    with actor_scope(coach.id):
        await events.emit(_entrada(socio.id, tiquetera.id, "active"), session)
    assert (await _fila(session, tiquetera.id))["classes_remaining"] == 0
    assert [e.classes_remaining for e in consumidos] == [0]
    assert vencidos == []


async def test_agotar_una_activa_si_emite_membership_expired(
    session: AsyncSession, usuario_real: CrearUsuario, capturar_eventos: CapturarEventos
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    tiquetera = await _tiquetera(session, socio, classes_remaining=1)
    vencidos = capturar_eventos(MembershipExpired)
    with actor_scope(coach.id):
        await events.emit(_entrada(socio.id, tiquetera.id, "active"), session)
    assert [e.membership_id for e in vencidos] == [tiquetera.id]


# L5 ------------------------------------------------------------------------------------------


async def test_descontar_con_la_membresia_de_otro_socio_no_hace_nada(
    session: AsyncSession, usuario_real: CrearUsuario, capturar_eventos: CapturarEventos
) -> None:
    coach = await usuario_real("coach")
    dueno, otro = await make_members(session, 2)
    tiquetera = await _tiquetera(session, dueno)
    consumidos = capturar_eventos(ClassConsumed)
    antes = await _fila(session, tiquetera.id)
    with actor_scope(coach.id):
        await events.emit(_entrada(otro.id, tiquetera.id, "active"), session)
    assert await _fila(session, tiquetera.id) == antes and consumidos == []


async def test_devolver_con_la_membresia_de_otro_socio_no_hace_nada(
    session: AsyncSession, usuario_real: CrearUsuario, capturar_eventos: CapturarEventos
) -> None:
    coach = await usuario_real("coach")
    dueno, otro = await make_members(session, 2)
    tiquetera = await _tiquetera(session, dueno, classes_remaining=5)
    devueltos = capturar_eventos(ClassReturned)
    antes = await _fila(session, tiquetera.id)
    with actor_scope(coach.id):
        await events.emit(_quitada(otro.id, tiquetera.id, "active"), session)
    assert await _fila(session, tiquetera.id) == antes and devueltos == []


async def test_el_mismo_socio_si_descuenta_y_devuelve(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    tiquetera = await _tiquetera(session, socio, classes_remaining=5)
    with actor_scope(coach.id):
        await events.emit(_entrada(socio.id, tiquetera.id, "active"), session)
    assert (await _fila(session, tiquetera.id))["classes_remaining"] == 4
    with actor_scope(coach.id):
        await events.emit(_quitada(socio.id, tiquetera.id, "active"), session)
    assert (await _fila(session, tiquetera.id))["classes_remaining"] == 5
