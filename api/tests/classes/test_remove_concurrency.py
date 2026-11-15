"""Quitar una asistencia contra una venta del mismo socio (S7-C3, US-161; S7-D40, revisión de C2).

Dos conexiones reales con commit. `DELETE /attendance/{id}` toma `lock_member` del socio ANTES de
emitir `AttendanceRemoved`: el handler de memberships hace `find_overlap` y, sin ese candado, una
venta paralela del mismo socio se colaría entre la lectura y la escritura. Orden: socio, asistencia
(`FOR UPDATE`), membresía (el handler), cadena de auditoría.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import actor_scope
from app.modules.classes import service
from app.modules.classes.schemas import AttendanceCreate, AttendanceRemove
from app.modules.memberships import service as memberships_service
from tests.factories.classes import FakeMembershipPort, make_session
from tests.factories.members import make_members
from tests.factories.plans import make_plan
from tests.factories.users import make_user

EN_VENTANA = datetime(2026, 10, 21, 15, 10, tzinfo=UTC)

pytestmark = pytest.mark.usefixtures("reloj", "bus_confirmado")


async def test_quitar_y_vender_al_mismo_socio_se_serializan(
    dos_sesiones: tuple[AsyncSession, AsyncSession], puerto: FakeMembershipPort
) -> None:
    """El quitar retiene el candado del socio 1 s (un suscriptor duerme); la venta llega a los
    0,4 s y espera. Sin el `lock_member` del quitar, la venta confirmaría primero."""
    del_quitar, de_la_venta = dos_sesiones
    coach = await make_user(del_quitar, role="coach")
    admin = await make_user(de_la_venta, role="admin")
    (socio,) = await make_members(del_quitar, 1)
    plan = await make_plan(del_quitar)
    sesion = await make_session(del_quitar, starts_at=EN_VENTANA)
    coach_id, admin_id, socio_id, plan_id = coach.id, admin.id, socio.id, plan.id
    with actor_scope(coach_id):
        entrada = await service.check_in(
            del_quitar,
            AttendanceCreate.model_validate({"session_id": sesion.id, "member_id": socio_id}),
            by=coach_id,
        )
        await del_quitar.commit()
    asistencia: UUID = entrada.id

    libre: list[bool] = []

    async def retener(_: service.AttendanceRemoved, __: AsyncSession) -> None:
        """Sondea desde la otra conexión si el candado del socio está libre; luego duerme."""
        sonda = await de_la_venta.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:m, 0))"), {"m": str(socio_id)}
        )
        libre.append(bool(sonda))
        await de_la_venta.rollback()
        await asyncio.sleep(1.0)

    events.subscribe(service.AttendanceRemoved, retener)
    orden: list[str] = []

    async def quitar() -> None:
        with actor_scope(coach_id):
            await service.remove_attendance(
                del_quitar, asistencia, AttendanceRemove(reason="Error"), by=coach_id, role="coach"
            )
            await del_quitar.commit()
        orden.append("quitar")

    async def vender() -> None:
        await asyncio.sleep(0.4)
        with actor_scope(admin_id):
            await memberships_service.sell(
                de_la_venta, member_id=socio_id, plan_id=plan_id, role="admin"
            )
            await de_la_venta.commit()
        orden.append("venta")

    await asyncio.wait_for(asyncio.gather(quitar(), vender()), timeout=30)
    assert libre == [False]  # el socio ya estaba bloqueado cuando se emitió el evento
    assert orden == ["quitar", "venta"]
