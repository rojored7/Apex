"""`classes.service.check_in` con base real y puerto doble (S7-C1, US-159; S7-D12, S7-D25, S7-D27).

Reloj `T0`: miércoles 21 de octubre de 2026, 10:00 en Bogotá (15:00Z). La sesión de fábrica de
estas pruebas empieza a las 10:10 de hoy (15:10Z): dentro de la ventana de 30 minutos. El
check-in siempre registra; los únicos 409 son `already_checked_in` y `session_cancelled`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.classes import attendance, service
from app.modules.classes.exceptions import (
    AlreadyCheckedIn,
    CheckinSessionCancelled,
    MembershipPortNotRegistered,
    SessionNotFound,
)
from app.modules.classes.models import Attendance
from app.modules.classes.schemas import AttendanceCreate
from app.modules.members.exceptions import MemberNotFound
from tests.conftest import CrearUsuario
from tests.factories.classes import FakeMembershipPort, make_session
from tests.factories.members import make_member, make_members, unique_document

HOY = date(2026, 10, 21)
EN_VENTANA = datetime(2026, 10, 21, 15, 10, tzinfo=UTC)

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


def _datos(session_id: UUID, member_id: UUID) -> AttendanceCreate:
    return AttendanceCreate.model_validate({"session_id": session_id, "member_id": member_id})


async def _check_in(session: AsyncSession, actor: UUID, session_id: UUID, member_id: UUID) -> Any:
    with actor_scope(actor):
        salida = await service.check_in(session, _datos(session_id, member_id), by=actor)
        await session.commit()
    return salida


async def _filas(session: AsyncSession) -> int:
    return int(await session.scalar(text("SELECT count(*) FROM classes.attendance")) or 0)


@pytest.mark.parametrize(
    ("estado", "esperadas"),
    [
        ("active", []),
        ("expiring", []),
        ("expired", ["expired"]),
        ("none", ["no_membership"]),
        ("frozen", ["frozen"]),
        ("pending_payment", ["pending_payment"]),
    ],
)
async def test_201_con_banderas_sin_409(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    puerto: FakeMembershipPort,
    estado: str,
    esperadas: list[str],
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    puerto.status = estado
    salida = await _check_in(session, coach.id, sesion.id, socio.id)
    assert salida.flags == esperadas
    assert salida.flagged is bool(esperadas)
    assert salida.membership_status_at_checkin == estado
    assert salida.attendance_count == 1 and salida.capacity == 15
    fila = (
        await session.execute(
            text(
                "SELECT membership_id, membership_status_at_checkin, flags, checked_in_by, "
                "checked_in_at, removed_at FROM classes.attendance WHERE id = :i"
            ),
            {"i": salida.id},
        )
    ).one()
    assert fila.membership_id == puerto.membership_id
    assert fila.membership_status_at_checkin == estado and list(fila.flags) == esperadas
    assert fila.checked_in_by == coach.id and fila.removed_at is None
    assert fila.checked_in_at == datetime(2026, 10, 21, 15, 0, tzinfo=UTC)


async def test_over_capacity_registra_y_cuenta(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    socios = await make_members(session, 3)
    sesion = await make_session(session, starts_at=EN_VENTANA, capacity=2)
    salidas = [await _check_in(session, coach.id, sesion.id, s.id) for s in socios]
    assert [s.flags for s in salidas] == [[], [], ["over_capacity"]]
    assert [s.attendance_count for s in salidas] == [1, 2, 3]


async def test_las_quitadas_no_cuentan_para_el_cupo(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    uno, otro = await make_members(session, 2)
    sesion = await make_session(session, starts_at=EN_VENTANA, capacity=1)
    with actor_scope(SYSTEM_USER_ID):
        session.add(
            Attendance(
                session_id=sesion.id,
                member_id=uno.id,
                membership_id=None,
                membership_status_at_checkin="none",
                flags=["no_membership"],
                checked_in_at=EN_VENTANA,
                checked_in_by=SYSTEM_USER_ID,
                removed_at=EN_VENTANA,
                removed_by=SYSTEM_USER_ID,
                removed_reason="Error",
                created_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()
    salida = await _check_in(session, coach.id, sesion.id, otro.id)
    assert salida.flags == [] and salida.attendance_count == 1
    # y el mismo socio de la quitada puede volver a registrarse (CA5 de US-161)
    de_nuevo = await _check_in(session, coach.id, sesion.id, uno.id)
    assert de_nuevo.attendance_count == 2


async def test_409_duplicado(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    await _check_in(session, coach.id, sesion.id, socio.id)
    with pytest.raises(AlreadyCheckedIn) as error:
        await _check_in(session, coach.id, sesion.id, socio.id)
    assert error.value.status == 409 and error.value.code == "already_checked_in"
    await session.rollback()
    assert await _filas(session) == 1


async def test_409_sesion_cancelada(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(
        session,
        starts_at=EN_VENTANA,
        status="cancelled",
        cancel_reason="Feriado",
        cancelled_by=SYSTEM_USER_ID,
        cancelled_at=EN_VENTANA,
    )
    with pytest.raises(CheckinSessionCancelled) as error:
        await _check_in(session, coach.id, sesion.id, socio.id)
    assert error.value.status == 409 and error.value.code == "session_cancelled"
    await session.rollback()
    assert await _filas(session) == 0


async def test_sesion_de_hace_un_mes_registra_con_other_day_sin_409(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    vieja = await make_session(session, starts_at=datetime(2026, 9, 21, 15, 10, tzinfo=UTC))
    salida = await _check_in(session, coach.id, vieja.id, socio.id)
    assert "other_day" in salida.flags and salida.flagged is True
    futura = await make_session(session, starts_at=datetime(2026, 11, 3, 15, 10, tzinfo=UTC))
    otra = await _check_in(session, coach.id, futura.id, socio.id)
    assert "other_day" in otra.flags


@pytest.mark.parametrize(
    ("inicio", "on_date"),
    [
        (datetime(2026, 10, 20, 15, 10, tzinfo=UTC), date(2026, 10, 20)),  # ayer
        (EN_VENTANA, HOY),  # hoy
        (datetime(2026, 9, 21, 15, 10, tzinfo=UTC), date(2026, 9, 21)),  # hace un mes
        (datetime(2026, 11, 3, 15, 10, tzinfo=UTC), HOY),  # futura: min(session_date, hoy)
    ],
)
async def test_el_puerto_recibe_session_date(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    puerto: FakeMembershipPort,
    inicio: datetime,
    on_date: date,
) -> None:
    """S7-D25: `on_date = min(session_date, hoy_bogota())`."""
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=inicio)
    await _check_in(session, coach.id, sesion.id, socio.id)
    assert puerto.views == [(socio.id, on_date)]


async def test_404_socio_de_baja(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    baja = await make_member(
        session,
        document=unique_document(),
        phone=None,
        email=None,
        deleted_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    sesion = await make_session(session, starts_at=EN_VENTANA)
    with pytest.raises(MemberNotFound):
        await _check_in(session, coach.id, sesion.id, baja.id)
    await session.rollback()
    assert await _filas(session) == 0
    assert puerto.views == []


async def test_404_sesion_inexistente(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    with pytest.raises(SessionNotFound):
        await _check_in(session, coach.id, uuid4(), socio.id)


async def test_sin_puerto_falla_cerrado_y_no_escribe(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    anterior = service.membership_port()
    service.set_membership_port(None)
    try:
        with pytest.raises(MembershipPortNotRegistered):
            await _check_in(session, coach.id, sesion.id, socio.id)
    finally:
        service.set_membership_port(anterior)
    await session.rollback()
    assert await _filas(session) == 0


async def test_ensure_exists_repetido_tras_lock_member(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    puerto: FakeMembershipPort,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L-4: `ensure_exists`, `lock_member`, `ensure_exists` (una baja concurrente no deja
    asistencia en un socio dado de baja)."""
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    pasos: list[str] = []
    real_existe = attendance.members_service.ensure_exists
    real_candado = attendance.lock_member

    async def existe(*args: Any, **kwargs: Any) -> None:
        pasos.append("existe")
        await real_existe(*args, **kwargs)

    async def candado(*args: Any, **kwargs: Any) -> None:
        pasos.append("candado")
        await real_candado(*args, **kwargs)

    monkeypatch.setattr(attendance.members_service, "ensure_exists", existe)
    monkeypatch.setattr(attendance, "lock_member", candado)
    await _check_in(session, coach.id, sesion.id, socio.id)
    assert pasos == ["existe", "candado", "existe"]


async def test_orden_de_candados_socio_sesion_membresia_y_recien_el_flush(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    """S7-D12: socio, sesión (`FOR UPDATE`), membresía (puerto) y recién el `INSERT` auditado."""
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    vistas: list[str] = []
    motor = session.get_bind()
    original = puerto.checkin_view

    def anotar(_c: Any, _cur: Any, sentencia: str, *_: Any) -> None:
        vistas.append(sentencia)

    async def ver(*args: Any, **kwargs: Any) -> Any:
        vistas.append("<<checkin_view>>")
        return await original(*args, **kwargs)

    puerto.checkin_view = ver  # type: ignore[method-assign]
    event.listen(motor, "before_cursor_execute", anotar)
    try:
        await _check_in(session, coach.id, sesion.id, socio.id)
    finally:
        event.remove(motor, "before_cursor_execute", anotar)
    socio_i = next(i for i, s in enumerate(vistas) if "hashtextextended" in s)
    sesion_i = next(i for i, s in enumerate(vistas) if "FOR UPDATE" in s and "class_sessions" in s)
    vista_i = vistas.index("<<checkin_view>>")
    insert_i = next(
        i for i, s in enumerate(vistas) if s.startswith("INSERT INTO classes.attendance")
    )
    assert socio_i < sesion_i < vista_i < insert_i


async def test_23505_traducido_a_already_checked_in(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    puerto: FakeMembershipPort,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dos tablets a la vez: la comprobación previa no vio la fila y el índice único la ataja."""
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    await _check_in(session, coach.id, sesion.id, socio.id)

    async def nadie(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(attendance, "alive_attendance_id", nadie)
    with pytest.raises(AlreadyCheckedIn):
        await _check_in(session, coach.id, sesion.id, socio.id)
    await session.rollback()
    assert await _filas(session) == 1


async def test_evento_y_auditoria(
    session: AsyncSession, usuario_real: CrearUsuario, puerto: FakeMembershipPort
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    puerto.status = "expired"
    vistos: list[service.MemberCheckedIn] = []

    async def capturar(evento: service.MemberCheckedIn, _: AsyncSession) -> None:
        vistos.append(evento)

    events.subscribe(service.MemberCheckedIn, capturar)
    salida = await _check_in(session, coach.id, sesion.id, socio.id)
    (evento,) = vistos
    assert evento.attendance_id == salida.id and evento.session_id == sesion.id
    assert evento.member_id == socio.id and evento.membership_id == puerto.membership_id
    assert evento.membership_status == "expired" and evento.flags == ("expired",)
    fila = (
        await session.execute(
            text(
                "SELECT action, user_id, subject_member_id FROM audit.audit_log "
                "WHERE table_name = 'classes.attendance' AND record_id = :r"
            ),
            {"r": salida.id},
        )
    ).one()
    assert (fila.action, fila.user_id, fila.subject_member_id) == ("insert", coach.id, socio.id)


@pytest.mark.parametrize("campo", ["membership_id", "flags", "checked_in_at", "removed_at"])
def test_extra_forbid_rechaza_membership_id_flags_y_checked_in_at(campo: str) -> None:
    cuerpo: dict[str, Any] = {"session_id": str(uuid4()), "member_id": str(uuid4())}
    cuerpo[campo] = "x"
    with pytest.raises(ValidationError) as error:
        AttendanceCreate.model_validate(cuerpo)
    assert error.value.errors()[0]["type"] == "extra_forbidden"
