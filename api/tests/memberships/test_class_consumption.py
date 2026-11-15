"""Descontar y devolver clases por check-in (S7-C2, US-160; S7-D14, S7-D25, S7-D29, L-5).

Con base real y el puerto REAL de `memberships` (el que registra `service.py` al importarse): el
check-in pasa por `classes.service.check_in`, que lee la membresía por el puerto y emite
`MemberCheckedIn`; `memberships` descuenta en la misma transacción. Reloj `T0`: miércoles 21 de
octubre de 2026, 10:00 en Bogotá. Quitar una asistencia (C3) todavía no tiene ruta: el evento
`AttendanceRemoved` se emite a mano con los datos de la fila de asistencia.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import actor_scope
from app.modules.classes import service as classes_service
from app.modules.classes.schemas import AttendanceCreate
from app.modules.memberships.service import ClassConsumed, ClassReturned, MembershipExpired
from app.modules.memberships.summary import SUMMARY_DIRTY_KEY
from tests.conftest import CapturarEventos, CrearUsuario
from tests.factories.classes import make_session
from tests.factories.members import make_member
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import leer_auditoria

HOY = date(2026, 10, 21)
EN_VENTANA = datetime(2026, 10, 21, 15, 10, tzinfo=UTC)  # 10:10 en Bogotá

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


async def _entrar(
    session: AsyncSession, coach: UUID, member_id: UUID, *, starts_at: datetime = EN_VENTANA
) -> Any:
    sesion = await make_session(session, starts_at=starts_at)
    datos = AttendanceCreate.model_validate({"session_id": sesion.id, "member_id": member_id})
    with actor_scope(coach):
        salida = await classes_service.check_in(session, datos, by=coach)
        await session.commit()
    return salida


async def _quitar(session: AsyncSession, coach: UUID, asistencia_id: UUID) -> None:
    """Lo que hará C3: emite `AttendanceRemoved` con los datos de la fila."""
    resultado = await session.execute(
        text(
            "SELECT session_id, member_id, membership_id, membership_status_at_checkin "
            "FROM classes.attendance WHERE id = :i"
        ),
        {"i": asistencia_id},
    )
    fila = resultado.mappings().one()
    evento = classes_service.AttendanceRemoved(
        attendance_id=asistencia_id,
        session_id=fila["session_id"],
        member_id=fila["member_id"],
        membership_id=fila["membership_id"],
        membership_status=fila["membership_status_at_checkin"],
    )
    with actor_scope(coach):
        await events.emit(evento, session)
        await session.commit()


async def _fila(session: AsyncSession, membership_id: UUID) -> dict[str, Any]:
    resultado = await session.execute(
        text(
            "SELECT classes_remaining, end_date, original_end_date, status "
            "FROM memberships.memberships WHERE id = :i"
        ),
        {"i": membership_id},
    )
    return dict(resultado.mappings().one())


async def test_12_a_11(
    session: AsyncSession, usuario_real: CrearUsuario, capturar_eventos: CapturarEventos
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    tiquetera = await _tiquetera(session, socio)
    consumidos = capturar_eventos(ClassConsumed)
    salida = await _entrar(session, coach.id, socio.id)
    assert salida.flags == []
    fila = await _fila(session, tiquetera.id)
    assert (fila["classes_remaining"], fila["end_date"], fila["original_end_date"]) == (
        11,
        date(2026, 11, 30),
        None,
    )
    assert fila["status"] == "active"
    assert [(e.membership_id, e.classes_remaining) for e in consumidos] == [(tiquetera.id, 11)]
    auditoria = [
        a
        for a in await leer_auditoria(session, "memberships.memberships", tiquetera.id)
        if a["action"] == "update"
    ]
    assert len(auditoria) == 1 and auditoria[0]["subject_member_id"] == socio.id
    assert "classes_remaining" in auditoria[0]["after"]


async def test_1_a_0_expira_recorta_y_emite(
    session: AsyncSession, usuario_real: CrearUsuario, capturar_eventos: CapturarEventos
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    tiquetera = await _tiquetera(session, socio, classes_remaining=1)
    consumidos = capturar_eventos(ClassConsumed)
    vencidos = capturar_eventos(MembershipExpired)
    await _entrar(session, coach.id, socio.id)
    fila = await _fila(session, tiquetera.id)
    assert fila["classes_remaining"] == 0 and fila["status"] == "expired"
    assert (fila["end_date"], fila["original_end_date"]) == (HOY, date(2026, 11, 30))
    assert [e.classes_remaining for e in consumidos] == [0]
    assert [(e.membership_id, e.on_date) for e in vencidos] == [(tiquetera.id, HOY)]


async def test_quitar_devuelve_y_reactiva(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    tiquetera = await _tiquetera(session, socio, classes_remaining=1)
    salida = await _entrar(session, coach.id, socio.id)
    assert (await _fila(session, tiquetera.id))["status"] == "expired"
    await _quitar(session, coach.id, salida.id)
    fila = await _fila(session, tiquetera.id)
    assert fila["classes_remaining"] == 1 and fila["status"] == "active"
    assert (fila["end_date"], fila["original_end_date"]) == (date(2026, 11, 30), None)


async def test_quitar_emite_class_returned(
    session: AsyncSession, usuario_real: CrearUsuario, capturar_eventos: CapturarEventos
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    tiquetera = await _tiquetera(session, socio)
    salida = await _entrar(session, coach.id, socio.id)
    devueltos = capturar_eventos(ClassReturned)
    await _quitar(session, coach.id, salida.id)
    assert [(e.membership_id, e.classes_remaining) for e in devueltos] == [(tiquetera.id, 12)]
    assert (await _fila(session, tiquetera.id))["classes_remaining"] == 12


async def test_quitar_con_solape_deja_el_recorte(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """Si el socio ya compró otra membresía en el hueco que dejó el recorte, restaurar el fin la
    cruzaría: la clase vuelve, el fin queda recortado y `original_end_date` se conserva."""
    coach = await usuario_real("coach")
    socio = await make_member(session)
    tiquetera = await _tiquetera(session, socio, classes_remaining=1)
    salida = await _entrar(session, coach.id, socio.id)
    plan = await make_plan(session, name="Mensual solape")
    await make_membership(
        session, socio, plan, status="active", start=date(2026, 10, 22), end=date(2026, 11, 21)
    )
    await _quitar(session, coach.id, salida.id)
    fila = await _fila(session, tiquetera.id)
    assert fila["classes_remaining"] == 1
    assert (fila["end_date"], fila["original_end_date"]) == (HOY, date(2026, 11, 30))


@pytest.mark.parametrize("caso", ["por_dias", "congelada", "pending_payment", "sin_membresia"])
async def test_por_dias_congelada_pending_y_sin_membresia_intactas(
    session: AsyncSession, usuario_real: CrearUsuario, caso: str
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    membresia = None
    if caso == "por_dias":
        plan = await make_plan(session)
        membresia = await make_membership(
            session, socio, plan, status="active", start=date(2026, 10, 1), end=date(2026, 11, 30)
        )
    elif caso == "congelada":
        membresia = await _tiquetera(session, socio)
        await make_freeze(session, membresia, HOY - timedelta(days=1), HOY + timedelta(days=2))
    elif caso == "pending_payment":
        membresia = await _tiquetera(session, socio, status="pending_payment")
    antes = None if membresia is None else await _fila(session, membresia.id)
    await _entrar(session, coach.id, socio.id)
    if membresia is not None:
        assert await _fila(session, membresia.id) == antes
        actualizaciones = [
            a
            for a in await leer_auditoria(session, "memberships.memberships", membresia.id)
            if a["action"] == "update"
        ]
        assert actualizaciones == []


async def test_vigente_por_dias_mas_futura_por_clases_no_descuenta(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    plan = await make_plan(session)
    vigente = await make_membership(
        session, socio, plan, status="active", start=date(2026, 10, 1), end=date(2026, 11, 20)
    )
    futura = await _tiquetera(session, socio, start=date(2026, 11, 21), end=date(2027, 1, 20))
    salida = await _entrar(session, coach.id, socio.id)
    assert salida.flags == []
    decidio = await session.scalar(
        text("SELECT membership_id FROM classes.attendance WHERE id = :i"), {"i": salida.id}
    )
    assert decidio == vigente.id
    assert (await _fila(session, futura.id))["classes_remaining"] == 12


async def test_vencida_mas_futura_por_clases_da_no_membership_y_futura_intacta(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """La futura no cuenta (S7-D25): ni descuenta ni decide. Lo que decide es la vencida: estado
    `expired` (bandera `expired`; el «no_membership» del plan es «sin membresía que descuente»)."""
    coach = await usuario_real("coach")
    socio = await make_member(session)
    plan = await make_plan(session)
    await make_membership(
        session, socio, plan, status="active", start=date(2026, 10, 1), end=date(2026, 10, 15)
    )
    futura = await _tiquetera(session, socio, start=date(2026, 10, 22), end=date(2026, 12, 21))
    antes = await _fila(session, futura.id)
    salida = await _entrar(session, coach.id, socio.id)
    assert salida.flags == ["expired"]
    assert await _fila(session, futura.id) == antes


async def test_check_in_de_ayer_usa_la_membresia_vigente_ayer(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    de_ayer = await _tiquetera(session, socio, start=date(2026, 10, 1), end=date(2026, 10, 20))
    de_hoy = await _tiquetera(session, socio, start=date(2026, 10, 21), end=date(2026, 11, 30))
    ayer = datetime(2026, 10, 20, 15, 10, tzinfo=UTC)
    salida = await _entrar(session, coach.id, socio.id, starts_at=ayer)
    assert "other_day" not in salida.flags
    assert (await _fila(session, de_ayer.id))["classes_remaining"] == 11
    assert (await _fila(session, de_hoy.id))["classes_remaining"] == 12


async def test_other_day_descuenta_de_la_vigente_en_on_date(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    vigente = await _tiquetera(session, socio, start=date(2026, 10, 1), end=date(2026, 10, 31))
    hace_diez_dias = datetime(2026, 10, 11, 15, 10, tzinfo=UTC)
    salida = await _entrar(session, coach.id, socio.id, starts_at=hace_diez_dias)
    assert "other_day" in salida.flags
    assert (await _fila(session, vigente.id))["classes_remaining"] == 11


async def test_sesion_futura_no_usa_tiquetera_futura(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    futura = await _tiquetera(session, socio, start=date(2026, 10, 22), end=date(2026, 12, 21))
    manana = datetime(2026, 10, 22, 15, 10, tzinfo=UTC)
    salida = await _entrar(session, coach.id, socio.id, starts_at=manana)
    # mañana: sin membresía que empiece hoy; además fuera de ventana y de otro día
    assert "no_membership" in salida.flags
    assert salida.membership_status_at_checkin == "none"
    assert (await _fila(session, futura.id))["classes_remaining"] == 12


async def test_agotar_vencida_no_alarga_end_date(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """Una sesión pasada que agota una tiquetera que hoy ya venció por fecha no alarga su fin
    (S7-D29: `min(end_date, ...)`) ni crea `original_end_date`."""
    coach = await usuario_real("coach")
    socio = await make_member(session)
    vencida = await _tiquetera(
        session, socio, start=date(2026, 10, 1), end=date(2026, 10, 15), classes_remaining=1
    )
    sesion_pasada = datetime(2026, 10, 10, 15, 10, tzinfo=UTC)
    await _entrar(session, coach.id, socio.id, starts_at=sesion_pasada)
    fila = await _fila(session, vencida.id)
    assert fila["classes_remaining"] == 0 and fila["status"] == "expired"
    assert (fila["end_date"], fila["original_end_date"]) == (date(2026, 10, 15), None)


async def test_fallo_del_handler_revierte_el_check_in(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    tiquetera = await _tiquetera(session, socio)
    tiquetera_id = tiquetera.id

    async def falla(evento: ClassConsumed, sesion: AsyncSession) -> None:
        raise RuntimeError("handler roto")

    events.subscribe(ClassConsumed, falla)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    datos = AttendanceCreate.model_validate({"session_id": sesion.id, "member_id": socio.id})
    with pytest.raises(RuntimeError, match="handler roto"), actor_scope(coach.id):
        await classes_service.check_in(session, datos, by=coach.id)
    await session.rollback()
    assert await session.scalar(text("SELECT count(*) FROM classes.attendance")) == 0
    assert (await _fila(session, tiquetera_id))["classes_remaining"] == 12


async def test_cache_del_resumen_marcada(session: AsyncSession, usuario_real: CrearUsuario) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    await _tiquetera(session, socio)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    datos = AttendanceCreate.model_validate({"session_id": sesion.id, "member_id": socio.id})
    session.info.pop(SUMMARY_DIRTY_KEY, None)
    with actor_scope(coach.id):
        await classes_service.check_in(session, datos, by=coach.id)
    assert session.info.get(SUMMARY_DIRTY_KEY) is True


async def test_devolver_sobre_cancelada_no_hace_nada(
    session: AsyncSession, usuario_real: CrearUsuario, capturar_eventos: CapturarEventos
) -> None:
    """L-5: `on_attendance_removed` sobre una membresía `cancelled` no cambia nada."""
    coach = await usuario_real("coach")
    socio = await make_member(session)
    tiquetera = await _tiquetera(session, socio)
    salida = await _entrar(session, coach.id, socio.id)
    with actor_scope(coach.id):
        await session.execute(
            text(
                "UPDATE memberships.memberships SET status = 'cancelled', "
                "cancel_reason = 'Cancelada por prueba', cancelled_by = :u, cancelled_at = now() "
                "WHERE id = :i"
            ),
            {"i": tiquetera.id, "u": coach.id},
        )
        await session.commit()
    antes = await _fila(session, tiquetera.id)
    devueltos = capturar_eventos(ClassReturned)
    await _quitar(session, coach.id, salida.id)
    assert await _fila(session, tiquetera.id) == antes and antes["classes_remaining"] == 11
    assert devueltos == []


async def test_devolver_sin_membresia_o_inexistente_no_rompe(
    session: AsyncSession, usuario_real: CrearUsuario, capturar_eventos: CapturarEventos
) -> None:
    """Un `membership_id` nulo o que no existe no rompe la devolución ni emite nada."""
    coach = await usuario_real("coach")
    socio = await make_member(session)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    devueltos = capturar_eventos(ClassReturned)
    for membership_id, estado in ((None, "none"), (sesion.id, "active")):
        with actor_scope(coach.id):
            await events.emit(
                classes_service.AttendanceRemoved(
                    attendance_id=sesion.id,
                    session_id=sesion.id,
                    member_id=socio.id,
                    membership_id=membership_id,
                    membership_status=estado,
                ),
                session,
            )
    assert devueltos == []
