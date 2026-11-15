"""Check-in concurrente (S7-C1, US-159; S7-D12, S7-D26, M-1). Rojo C1.

Dos conexiones reales con commit. La sesión se bloquea `FOR UPDATE` ANTES del primer flush
auditado, así que dos check-in de la misma sesión se serializan (el cupo lo ven completo) y un
check-in contra una cancelación masiva no forma ciclo con la cadena de auditoría (40P01).
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import actor_scope
from app.modules.classes import service
from app.modules.classes.exceptions import CheckinSessionCancelled
from app.modules.classes.schemas import AttendanceCreate, SessionCancel
from tests.factories.classes import FakeMembershipPort, make_session, make_slot
from tests.factories.members import make_members
from tests.factories.users import make_user

EN_VENTANA = datetime(2026, 10, 21, 15, 10, tzinfo=UTC)
FUTURA = datetime(2026, 10, 26, 11, 0, tzinfo=UTC)

pytestmark = pytest.mark.usefixtures("reloj", "bus_confirmado")


async def _entrar(session: AsyncSession, actor: UUID, session_id: UUID, member_id: UUID) -> object:
    with actor_scope(actor):
        datos = AttendanceCreate.model_validate({"session_id": session_id, "member_id": member_id})
        salida = await service.check_in(session, datos, by=actor)
        await session.commit()
    return salida


async def test_asistentes_16_y_17_a_la_vez_ambos_over_capacity(
    dos_sesiones: tuple[AsyncSession, AsyncSession], puerto: FakeMembershipPort
) -> None:
    """Cupo 15 con 15 dentro: el 16.º y el 17.º llegan a la vez; ambos `over_capacity` y los
    conteos 16 y 17 (la sesión bloqueada los serializa; ninguno ve 15 y pasa sin bandera)."""
    una, otra = dos_sesiones
    coach = await make_user(una, role="coach")
    socios = await make_members(una, 17)
    sesion = await make_session(una, starts_at=EN_VENTANA, capacity=15)
    for socio in socios[:15]:
        await _entrar(una, coach.id, sesion.id, socio.id)

    resultados = await asyncio.wait_for(
        asyncio.gather(
            _entrar(una, coach.id, sesion.id, socios[15].id),
            _entrar(otra, coach.id, sesion.id, socios[16].id),
        ),
        timeout=30,
    )
    assert all("over_capacity" in r.flags for r in resultados)  # type: ignore[attr-defined]
    assert sorted(r.attendance_count for r in resultados) == [16, 17]  # type: ignore[attr-defined]
    total = await una.scalar(text("SELECT count(*) FROM classes.attendance"))
    assert total == 17


async def test_cancelar_futuras_y_check_in_no_se_interbloquean(
    dos_sesiones: tuple[AsyncSession, AsyncSession], puerto: FakeMembershipPort
) -> None:
    """M-1: el check-in ya tiene la sesión y la cadena (un suscriptor lo retiene 1 s); la
    cancelación masiva (candado 006, `FOR UPDATE` de la sesión) espera y, al liberarse, la
    cancela. Sin 40P01: el único resultado posible de las dos es éxito."""
    del_checkin, de_la_cancelacion = dos_sesiones
    admin = await make_user(de_la_cancelacion, role="admin")
    coach = await make_user(del_checkin, role="coach")
    (socio,) = await make_members(del_checkin, 1)
    franja = await make_slot(del_checkin, weekdays=[0])
    sesion = await make_session(del_checkin, slot_id=franja.id, starts_at=FUTURA)

    async def retener(_: service.MemberCheckedIn, __: AsyncSession) -> None:
        await asyncio.sleep(1.0)

    events.subscribe(service.MemberCheckedIn, retener)

    async def entrar() -> object:
        return await _entrar(del_checkin, coach.id, sesion.id, socio.id)

    async def cancelar() -> int:
        await asyncio.sleep(0.4)
        with actor_scope(admin.id):
            salida = await service.cancel_future_sessions(
                de_la_cancelacion,
                franja.id,
                SessionCancel.model_validate({"reason": "Festivo"}),
                by=admin.id,
            )
            await de_la_cancelacion.commit()
        return salida.cancelled_count

    _, canceladas = await asyncio.wait_for(asyncio.gather(entrar(), cancelar()), timeout=30)
    assert canceladas == 1
    estado = await del_checkin.scalar(
        text("SELECT status FROM classes.class_sessions WHERE id = :i"), {"i": sesion.id}
    )
    assert estado == "cancelled"


async def test_check_in_tras_la_cancelacion_masiva_da_409_sin_interbloqueo(
    dos_sesiones: tuple[AsyncSession, AsyncSession], puerto: FakeMembershipPort
) -> None:
    """El orden inverso: la cancelación toma 006 y la sesión primero y duerme; el check-in
    espera la sesión y al verla cancelada da 409 `session_cancelled` (no un ciclo)."""
    del_checkin, de_la_cancelacion = dos_sesiones
    admin = await make_user(de_la_cancelacion, role="admin")
    coach = await make_user(del_checkin, role="coach")
    (socio,) = await make_members(del_checkin, 1)
    franja = await make_slot(del_checkin, weekdays=[0])
    sesion = await make_session(del_checkin, slot_id=franja.id, starts_at=FUTURA)

    async def retener(_: service.SessionCancelled, __: AsyncSession) -> None:
        await asyncio.sleep(1.0)

    events.subscribe(service.SessionCancelled, retener)

    async def cancelar() -> int:
        with actor_scope(admin.id):
            salida = await service.cancel_future_sessions(
                de_la_cancelacion,
                franja.id,
                SessionCancel.model_validate({"reason": "Festivo"}),
                by=admin.id,
            )
            await de_la_cancelacion.commit()
        return salida.cancelled_count

    async def entrar() -> str:
        await asyncio.sleep(0.4)
        try:
            await _entrar(del_checkin, coach.id, sesion.id, socio.id)
        except CheckinSessionCancelled:
            await del_checkin.rollback()
            return "409"
        return "201"

    canceladas, resultado = await asyncio.wait_for(asyncio.gather(cancelar(), entrar()), timeout=30)
    assert canceladas == 1 and resultado == "409"


def test_los_suscriptores_de_sesion_no_toman_candados() -> None:
    """S7-B3b (LOW 3): `SessionCancelled` y `SessionGenerated` se emiten con la cadena de
    auditoría (4_270_002) ya tomada; un suscriptor que pida un candado de socio, de membresía o
    asesor invertiría el orden de `core/locks.py` y abriría un ciclo."""
    prohibidos = ("with_for_update", "advisory", "lock_member", "lock_membership", "FOR UPDATE")
    for tipo in (service.SessionCancelled, service.SessionGenerated):
        for handler in events.subscribers_for(tipo):
            fuente = inspect.getsource(handler)
            assert not [p for p in prohibidos if p in fuente], f"{tipo.__name__}: {handler}"
