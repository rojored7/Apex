"""`remove_attendance` con base real y puerto doble (S7-C3, US-161; S7-D13, S7-D27 b).

Reloj `T0`: miércoles 21 de octubre de 2026, 10:00 en Bogotá (15:00Z). Quitar es un borrado
lógico: fija `removed_at`, `removed_by` y `removed_reason` (la auditoría lo ve como `update`),
emite `AttendanceRemoved` y se puede volver a registrar. El coach solo quita de sesiones de hoy o
de ayer (Bogotá); el admin, de cualquier día.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.modules.classes import service
from app.modules.classes.exceptions import (
    AttendanceLocked,
    AttendanceNotFound,
    MembershipPortNotRegistered,
)
from app.modules.classes.schemas import AttendanceCreate, AttendanceRemove
from tests.conftest import CrearUsuario
from tests.factories.classes import FakeMembershipPort, make_session
from tests.factories.members import make_members

HOY = datetime(2026, 10, 21, 15, 10, tzinfo=UTC)  # 10:10 de hoy en Bogotá
AYER = datetime(2026, 10, 20, 15, 10, tzinfo=UTC)
ANTEAYER = datetime(2026, 10, 19, 15, 10, tzinfo=UTC)
HACE_UN_MES = datetime(2026, 9, 21, 15, 10, tzinfo=UTC)

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def _registrar(session: AsyncSession, actor: UUID, session_id: UUID, member_id: UUID) -> UUID:
    datos = AttendanceCreate.model_validate({"session_id": session_id, "member_id": member_id})
    with actor_scope(actor):
        salida = await service.check_in(session, datos, by=actor)
        await session.commit()
    return salida.id


async def _quitar(
    session: AsyncSession,
    actor: UUID,
    attendance_id: UUID,
    *,
    role: str,
    reason: str | None = None,
    sin_cuerpo: bool = False,
) -> None:
    cuerpo = None if sin_cuerpo else AttendanceRemove(reason=reason)
    with actor_scope(actor):
        await service.remove_attendance(session, attendance_id, cuerpo, by=actor, role=role)
        await session.commit()


async def _fila(session: AsyncSession, attendance_id: UUID) -> Any:
    return (
        await session.execute(
            text(
                "SELECT removed_at, removed_by, removed_reason FROM classes.attendance "
                "WHERE id = :i"
            ),
            {"i": attendance_id},
        )
    ).one()


async def test_204_y_fila_update_con_removed(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=HOY)
    asistencia = await _registrar(session, coach.id, sesion.id, socio.id)
    socio_id, coach_id = socio.id, coach.id
    await _quitar(session, coach_id, asistencia, role="coach", reason="Se registró por error")
    fila = await _fila(session, asistencia)
    assert fila.removed_at == datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
    assert fila.removed_by == coach_id and fila.removed_reason == "Se registró por error"
    auditoria = (
        await session.execute(
            text(
                "SELECT action, user_id, subject_member_id, after FROM audit.audit_log "
                "WHERE table_name = 'classes.attendance' AND record_id = :r ORDER BY seq"
            ),
            {"r": asistencia},
        )
    ).all()
    assert [a.action for a in auditoria] == ["insert", "update"]
    cambio = auditoria[1]
    assert (cambio.user_id, cambio.subject_member_id) == (coach_id, socio_id)
    assert {"removed_at", "removed_by", "removed_reason"} <= set(cambio.after)


async def test_sin_cuerpo_deja_el_motivo_nulo(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    admin = await usuario_real("admin")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=HOY)
    asistencia = await _registrar(session, admin.id, sesion.id, socio.id)
    await _quitar(session, admin.id, asistencia, role="admin", sin_cuerpo=True)
    fila = await _fila(session, asistencia)
    assert fila.removed_at is not None and fila.removed_reason is None


async def test_emite_attendance_removed_y_devuelve_la_clase(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=HOY)
    puerto.status = "expiring"
    asistencia = await _registrar(session, coach.id, sesion.id, socio.id)
    vistos: list[service.AttendanceRemoved] = []

    async def capturar(evento: service.AttendanceRemoved, _: AsyncSession) -> None:
        vistos.append(evento)

    events.subscribe(service.AttendanceRemoved, capturar)
    socio_id, sesion_id, coach_id = socio.id, sesion.id, coach.id
    await _quitar(session, coach_id, asistencia, role="coach", reason="Error")
    (evento,) = vistos
    assert evento.attendance_id == asistencia and evento.session_id == sesion_id
    assert evento.member_id == socio_id and evento.membership_id == puerto.membership_id
    assert evento.membership_status == "expiring"
    assert puerto.locked == [puerto.membership_id]  # D3: la membresía se bloquea antes de emitir
    assert not hasattr(evento, "reason")  # el motivo es texto libre: no viaja (S3-D70)


async def test_sin_membresia_no_bloquea_ni_exige_puerto(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=HOY)
    puerto.status = "none"
    asistencia = await _registrar(session, coach.id, sesion.id, socio.id)
    service.set_membership_port(None)
    await _quitar(session, coach.id, asistencia, role="coach")
    assert puerto.locked == []
    assert (await _fila(session, asistencia)).removed_at is not None


async def test_con_membresia_y_sin_puerto_falla_cerrado_y_no_escribe(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=HOY)
    asistencia = await _registrar(session, coach.id, sesion.id, socio.id)
    service.set_membership_port(None)
    with pytest.raises(MembershipPortNotRegistered):
        await _quitar(session, coach.id, asistencia, role="coach")
    await session.rollback()
    assert (await _fila(session, asistencia)).removed_at is None


async def test_se_puede_volver_a_registrar(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=HOY)
    primera = await _registrar(session, coach.id, sesion.id, socio.id)
    await _quitar(session, coach.id, primera, role="coach")
    segunda = await _registrar(session, coach.id, sesion.id, socio.id)
    assert segunda != primera


async def test_vale_en_sesion_cancelada(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=HOY)
    asistencia = await _registrar(session, coach.id, sesion.id, socio.id)
    await session.execute(
        text(
            "UPDATE classes.class_sessions SET status = 'cancelled', cancel_reason = 'Feriado', "
            "cancelled_by = :u, cancelled_at = :a WHERE id = :i"
        ),
        {"u": coach.id, "a": HOY, "i": sesion.id},
    )
    await session.commit()
    await _quitar(session, coach.id, asistencia, role="coach")
    assert (await _fila(session, asistencia)).removed_at is not None


async def test_404_al_quitar_dos_veces(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=HOY)
    asistencia = await _registrar(session, coach.id, sesion.id, socio.id)
    await _quitar(session, coach.id, asistencia, role="coach")
    with pytest.raises(AttendanceNotFound) as error:
        await _quitar(session, coach.id, asistencia, role="coach")
    assert (error.value.status, error.value.code) == (404, "attendance_not_found")


async def test_404_de_un_id_inexistente(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    with pytest.raises(AttendanceNotFound):
        await _quitar(session, coach.id, UUID(int=1), role="coach")


@pytest.mark.parametrize("cuando", [HOY, AYER])
async def test_coach_quita_hoy_y_ayer(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort, cuando: datetime
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=cuando)
    asistencia = await _registrar(session, coach.id, sesion.id, socio.id)
    await _quitar(session, coach.id, asistencia, role="coach")
    assert (await _fila(session, asistencia)).removed_at is not None


@pytest.mark.parametrize("cuando", [ANTEAYER, HACE_UN_MES])
async def test_coach_403_attendance_locked_anteayer(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort, cuando: datetime
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=cuando)
    asistencia = await _registrar(session, coach.id, sesion.id, socio.id)
    puerto.locked.clear()
    with pytest.raises(AttendanceLocked) as error:
        await _quitar(session, coach.id, asistencia, role="coach")
    assert (error.value.status, error.value.code) == (403, "attendance_locked")
    await session.rollback()
    assert (await _fila(session, asistencia)).removed_at is None
    assert puerto.locked == []  # no se tocó la membresía


@pytest.mark.parametrize("cuando", [ANTEAYER, HACE_UN_MES])
async def test_admin_quita_cualquier_dia(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort, cuando: datetime
) -> None:
    admin = await usuario_real("admin")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=cuando)
    asistencia = await _registrar(session, admin.id, sesion.id, socio.id)
    admin_id = admin.id
    await _quitar(session, admin_id, asistencia, role="admin", reason="Corrección del mes")
    fila = await _fila(session, asistencia)
    assert fila.removed_by == admin_id and fila.removed_reason == "Corrección del mes"


async def test_la_quitada_deja_de_contar_en_el_cupo(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    uno, otro = await make_members(session, 2)
    sesion = await make_session(session, starts_at=HOY, capacity=1)
    primera = await _registrar(session, coach.id, sesion.id, uno.id)
    await _quitar(session, coach.id, primera, role="coach")
    datos = AttendanceCreate.model_validate({"session_id": sesion.id, "member_id": otro.id})
    with actor_scope(coach.id):
        salida = await service.check_in(session, datos, by=coach.id)
    assert salida.flags == [] and salida.attendance_count == 1


async def test_borde_de_medianoche_utc_el_coach_cuenta_dias_de_bogota(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    puerto: FakeMembershipPort,
    reloj: FrozenClock,
) -> None:
    """S7-C3b: a las 04:30Z del 22 son las 23:30 del 21 en Bogotá. «Ayer» es el 20 (204) y
    «anteayer» el 19 (403); contar días en UTC invertiría los dos resultados."""
    reloj.advance(hours=13, minutes=30)  # de 15:00Z a 04:30Z del día siguiente
    assert reloj.now_utc() == datetime(2026, 10, 22, 4, 30, tzinfo=UTC)
    coach = await usuario_real("coach")
    coach_id = coach.id
    uno, otro = await make_members(session, 2)
    ayer = await make_session(session, starts_at=datetime(2026, 10, 20, 15, 10, tzinfo=UTC))
    anteayer = await make_session(session, starts_at=datetime(2026, 10, 19, 15, 10, tzinfo=UTC))
    de_ayer = await _registrar(session, coach_id, ayer.id, uno.id)
    de_anteayer = await _registrar(session, coach_id, anteayer.id, otro.id)
    await _quitar(session, coach_id, de_ayer, role="coach")
    assert (await _fila(session, de_ayer)).removed_at is not None
    with pytest.raises(AttendanceLocked):
        await _quitar(session, coach_id, de_anteayer, role="coach")
