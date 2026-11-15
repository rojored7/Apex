"""Historial del socio con filas de `classes.attendance` (S7-C3, US-161; S7-D17, E5).

El `insert` (check-in) y el `update` (quitar: borrado lógico) llegan con `subject_member_id` del
socio. `fields` solo trae nombres de campo, nunca valores (el motivo es texto libre). Las frases
las arma el front.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.pagination import PageParams
from app.modules.audit import queries as audit_queries
from app.modules.classes import service
from app.modules.classes.schemas import AttendanceCreate, AttendanceRemove
from tests.conftest import CrearUsuario
from tests.factories.classes import FakeMembershipPort, make_session
from tests.factories.members import make_members

HOY = datetime(2026, 10, 21, 15, 10, tzinfo=UTC)
MOTIVO = "Motivo reservado del coach"

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


@pytest.fixture
def puerto() -> Iterator[FakeMembershipPort]:
    """Un puerto doble de membresías (`tests/classes/conftest.py` no aplica a este paquete)."""
    doble = FakeMembershipPort("active")
    anterior = service.membership_port()
    service.set_membership_port(doble)
    try:
        yield doble
    finally:
        service.set_membership_port(anterior)


async def _insert_y_update(
    session: AsyncSession, actor: UUID, member_id: UUID
) -> list[audit_queries.MemberHistoryItem]:
    clase = await make_session(session, starts_at=HOY)
    with actor_scope(actor):
        salida = await service.check_in(
            session,
            AttendanceCreate.model_validate({"session_id": clase.id, "member_id": member_id}),
            by=actor,
        )
        await session.commit()
        await service.remove_attendance(
            session, salida.id, AttendanceRemove(reason=MOTIVO), by=actor, role="coach"
        )
        await session.commit()
    pagina = await audit_queries.member_history(session, member_id, PageParams(limit=50), None)
    return [i for i in pagina.items if i.table_name == "classes.attendance"]


async def test_insert_y_update_llegan_con_subject_member_id(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    items = await _insert_y_update(session, coach.id, socio.id)
    assert [i.action for i in items] == ["update", "insert"]  # seq descendente
    assert all(i.user_id == coach.id for i in items)
    assert items[0].record_id == items[1].record_id


async def test_history_fields_sin_valores(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    actualizar, insertar = await _insert_y_update(session, coach.id, socio.id)
    assert insertar.fields == []
    assert actualizar.fields == ["removed_at", "removed_by", "removed_reason"]
    assert MOTIVO not in repr(actualizar) and MOTIVO not in repr(insertar)
