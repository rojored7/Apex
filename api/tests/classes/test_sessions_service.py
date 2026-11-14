"""`classes.service` de sesiones con base real (S7-B2, US-157; S7-D11, S7-D32). Rojo B2.

Reloj `T0`: miércoles 21 de octubre de 2026, 10:00 en Bogotá (15:00Z), semana ISO 43
(lunes 19 a domingo 25). La sesión de fábrica es el jueves 22 a las 06:00 (11:00Z).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.pagination import PageParams
from app.modules.classes import service
from app.modules.classes.exceptions import (
    ClassValidationError,
    CoachInvalid,
    RangeTooLong,
    SessionAlreadyCancelled,
    SessionFinished,
    SessionNotFound,
)
from app.modules.classes.schemas import SessionCancel, SessionCreate, SessionListQuery, SessionOut
from tests.conftest import CrearUsuario
from tests.factories.classes import make_session

JUEVES_6AM = datetime(2026, 10, 22, 11, 0, tzinfo=UTC)
PAGINA = PageParams(limit=50, offset=0)

pytestmark = pytest.mark.usefixtures("reloj")


def _crear(**cambios: Any) -> SessionCreate:
    valores: dict[str, Any] = {"starts_at": JUEVES_6AM, "duration_min": 60}
    valores.update(cambios)
    return SessionCreate.model_validate(valores)


async def _extra(
    session: AsyncSession, actor: UUID, role: str = "admin", **cambios: Any
) -> SessionOut:
    with actor_scope(actor):
        salida = await service.create_extra(session, _crear(**cambios), by=actor, role=role)
        await session.commit()
    return salida


async def _cancelar(session: AsyncSession, actor: UUID, sid: UUID, motivo: str = "Lluvia") -> Any:
    with actor_scope(actor):
        salida = await service.cancel_session(
            session, sid, SessionCancel.model_validate({"reason": motivo}), by=actor
        )
        await session.commit()
    return salida


async def _fila(session: AsyncSession, sid: UUID) -> dict[str, Any]:
    consulta = text("SELECT * FROM classes.class_sessions WHERE id = :i")
    return dict((await session.execute(consulta, {"i": sid})).mappings().one())


# Sesión extra ----------------------------------------------------------------------------------


async def test_la_extra_queda_scheduled_sin_franja_con_cupo_por_omision_y_auditada(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    salida = await _extra(session, admin.id)
    fila = await _fila(session, salida.id)
    assert (fila["slot_id"], fila["status"], fila["capacity"]) == (None, "scheduled", 15)
    assert fila["created_by"] == admin.id and fila["starts_at"] == JUEVES_6AM
    assert (salida.status, salida.attendance_count, salida.slot_id) == ("scheduled", 0, None)
    auditoria = (
        await session.execute(
            text(
                "SELECT action, user_id FROM audit.audit_log "
                "WHERE table_name = 'classes.class_sessions' AND record_id = :i"
            ),
            {"i": salida.id},
        )
    ).all()
    assert [(a, u) for a, u in auditoria] == [("insert", admin.id)]


async def test_session_date_la_calcula_el_servidor_desde_starts_at_en_bogota(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """S7-D37: 23:30 del 31 de diciembre en Bogotá es el 1 de enero 04:30Z; la fecha es el 31."""
    admin = await usuario_real("admin")
    salida = await _extra(session, admin.id, starts_at="2026-12-31T23:30:00-05:00")
    fila = await _fila(session, salida.id)
    assert fila["session_date"] == date(2026, 12, 31)
    assert fila["starts_at"] == datetime(2027, 1, 1, 4, 30, tzinfo=UTC)
    otra = await _extra(session, admin.id, starts_at="2026-10-22T09:00:00+02:00")
    assert (await _fila(session, otra.id))["session_date"] == date(2026, 10, 22)


async def test_capacidad_nombre_y_coach_se_respetan(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach", email="sara@test.apex")
    salida = await _extra(
        session, admin.id, capacity=8, name="Open gym", coach_id=coach.id, duration_min=90
    )
    assert (salida.capacity, salida.name, salida.coach_id, salida.coach_name) == (
        8,
        "Open gym",
        coach.id,
        "sara",
    )
    assert salida.duration_min == 90


@pytest.mark.parametrize(
    "starts_at",
    ["2026-10-19T23:59:59-05:00", "2027-01-19T10:00:01-05:00"],
    ids=["antes_de_ayer", "mas_de_90_dias"],
)
async def test_starts_at_fuera_de_ayer_a_90_dias_da_422(
    session: AsyncSession, usuario_real: CrearUsuario, starts_at: str
) -> None:
    admin = await usuario_real("admin")
    with pytest.raises(ClassValidationError) as error:
        await _extra(session, admin.id, starts_at=starts_at)
    assert error.value.field == "starts_at"


async def test_coach_solo_se_asigna_a_si_mismo_o_nulo(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """L-3: un coach no pone a otro como coach de la sesión; el admin elige cualquier staff."""
    coach = await usuario_real("coach", email="coach1@test.apex")
    otro = await usuario_real("coach", email="coach2@test.apex")
    admin = await usuario_real("admin")
    socio = await usuario_real("member")
    propia = await _extra(session, coach.id, "coach", coach_id=coach.id)
    assert propia.coach_id == coach.id
    sin = await _extra(session, coach.id, "coach", coach_id=None)
    assert sin.coach_id is None
    with pytest.raises(CoachInvalid) as error:
        await _extra(session, coach.id, "coach", coach_id=otro.id)
    assert (error.value.status, error.value.code) == (422, "coach_invalid")
    elegido = await _extra(session, admin.id, "admin", coach_id=otro.id)
    assert elegido.coach_id == otro.id
    with pytest.raises(CoachInvalid):
        await _extra(session, admin.id, "admin", coach_id=socio.id)
    with pytest.raises(CoachInvalid):
        await _extra(session, admin.id, "admin", coach_id=uuid4())


# Cancelar --------------------------------------------------------------------------------------


async def test_cancelar_no_borra_nada_y_guarda_motivo_quien_y_cuando(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    creada = await make_session(session)
    salida = await _cancelar(session, coach.id, creada.id, "Corte de luz en el sector")
    assert (salida.status, salida.cancel_reason) == ("cancelled", "Corte de luz en el sector")
    fila = await _fila(session, creada.id)
    assert fila["status"] == "cancelled" and fila["cancelled_by"] == coach.id
    assert fila["cancelled_at"] == reloj.now_utc()
    cuantas = await session.scalar(text("SELECT count(*) FROM classes.class_sessions"))
    assert cuantas == 1
    acciones = (
        await session.execute(
            text(
                "SELECT action, user_id FROM audit.audit_log "
                "WHERE table_name = 'classes.class_sessions' AND record_id = :i ORDER BY seq"
            ),
            {"i": creada.id},
        )
    ).all()
    assert [(a, u) for a, u in acciones][-1] == ("update", coach.id)


async def test_cancelar_dos_veces_409(session: AsyncSession, usuario_real: CrearUsuario) -> None:
    admin = await usuario_real("admin")
    creada = await make_session(session)
    await _cancelar(session, admin.id, creada.id)
    with pytest.raises(SessionAlreadyCancelled) as error:
        await _cancelar(session, admin.id, creada.id, "Otro motivo")
    assert (error.value.status, error.value.code) == (409, "session_already_cancelled")
    assert (await _fila(session, creada.id))["cancel_reason"] == "Lluvia"


async def test_session_finished_409_siempre_aunque_ya_estuviera_cancelada(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """L-5: una sesión que ya terminó no se cancela; el titular decide a mano qué hacer con las
    asistencias, así que el api responde 409 `session_finished` (también si ya estaba cancelada)."""
    admin = await usuario_real("admin")
    pasada = await make_session(session, starts_at=reloj.now_utc() - timedelta(hours=5))
    with pytest.raises(SessionFinished) as error:
        await _cancelar(session, admin.id, pasada.id)
    assert (error.value.status, error.value.code) == (409, "session_finished")
    futura = await make_session(session)
    await _cancelar(session, admin.id, futura.id)
    reloj.advance(days=3)
    with pytest.raises(SessionFinished):
        await _cancelar(session, admin.id, futura.id)


async def test_cancelar_una_inexistente_da_404(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    with pytest.raises(SessionNotFound):
        await _cancelar(session, admin.id, uuid4())
    with pytest.raises(SessionNotFound):
        await service.get_session(session, uuid4())


async def test_session_cancelled_sin_motivo_en_el_evento(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    creada = await make_session(session)
    vistos: list[service.SessionCancelled] = []

    async def anotar(evento: service.SessionCancelled, _: AsyncSession) -> None:
        vistos.append(evento)

    events.subscribe(service.SessionCancelled, anotar)  # `restaurar_bus` lo quita
    await _cancelar(session, admin.id, creada.id, "Motivo con datos de Ana Pérez")
    (evento,) = vistos
    assert (evento.session_id, evento.slot_id, evento.starts_at) == (
        creada.id,
        None,
        creada.starts_at,
    )
    assert "Ana" not in repr(evento)
    assert not any("reason" in campo for campo in evento.__dataclass_fields__)


# Lectura ---------------------------------------------------------------------------------------


async def test_get_session_trae_el_detalle_con_asistentes_vacios(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach", email="sara@test.apex")
    creada = await make_session(session, coach_id=coach.id, name="Fuerza")
    detalle = await service.get_session(session, creada.id)
    assert (detalle.id, detalle.coach_name, detalle.name) == (creada.id, "sara", "Fuerza")
    assert detalle.attendees == [] and detalle.attendance_count == 0


async def test_la_semana_incluye_el_domingo_2330_y_excluye_el_lunes_00(
    session: AsyncSession,
) -> None:
    domingo = await make_session(session, starts_at=datetime(2026, 10, 26, 4, 30, tzinfo=UTC))
    lunes_43 = await make_session(session, starts_at=datetime(2026, 10, 19, 5, 0, tzinfo=UTC))
    lunes_44 = await make_session(session, starts_at=datetime(2026, 10, 26, 5, 0, tzinfo=UTC))
    antes = await make_session(session, starts_at=datetime(2026, 10, 19, 4, 59, tzinfo=UTC))
    w43 = await service.list_sessions(session, SessionListQuery(week="2026-W43"), PAGINA)
    assert {s.id for s in w43.items} == {domingo.id, lunes_43.id}
    w44 = await service.list_sessions(session, SessionListQuery(week="2026-W44"), PAGINA)
    assert {s.id for s in w44.items} == {lunes_44.id}
    assert antes.id not in {s.id for s in w43.items}


async def test_sin_filtros_de_fecha_es_la_semana_actual_y_ordena_por_hora(
    session: AsyncSession,
) -> None:
    tarde = await make_session(session, starts_at=datetime(2026, 10, 22, 23, 0, tzinfo=UTC))
    temprano = await make_session(session, starts_at=datetime(2026, 10, 22, 11, 0, tzinfo=UTC))
    await make_session(session, starts_at=datetime(2026, 11, 20, 11, 0, tzinfo=UTC))
    r = await service.list_sessions(session, SessionListQuery(), PAGINA)
    assert [s.id for s in r.items] == [temprano.id, tarde.id]
    assert (r.total, r.limit, r.offset) == (2, 50, 0)


async def test_from_y_to_incluyen_ambos_dias_de_bogota(session: AsyncSession) -> None:
    a = await make_session(session, starts_at=datetime(2026, 10, 26, 5, 0, tzinfo=UTC))
    b = await make_session(session, starts_at=datetime(2026, 10, 28, 4, 59, tzinfo=UTC))
    fuera = await make_session(session, starts_at=datetime(2026, 10, 28, 5, 0, tzinfo=UTC))
    consulta = SessionListQuery(from_date=date(2026, 10, 26), to_date=date(2026, 10, 27))
    ids = {s.id for s in (await service.list_sessions(session, consulta, PAGINA)).items}
    assert ids == {a.id, b.id} and fuera.id not in ids


async def test_el_rango_de_62_dias_se_acepta_y_el_de_63_da_422_range_too_long(
    session: AsyncSession,
) -> None:
    desde = date(2026, 10, 1)
    ok = SessionListQuery(from_date=desde, to_date=desde + timedelta(days=61))  # 62 días
    await service.list_sessions(session, ok, PAGINA)
    largo = SessionListQuery(from_date=desde, to_date=desde + timedelta(days=62))  # 63 días
    with pytest.raises(RangeTooLong) as error:
        await service.list_sessions(session, largo, PAGINA)
    assert (error.value.status, error.value.code) == (422, "range_too_long")


@pytest.mark.parametrize(
    "consulta",
    [
        {"week": "2026-W43", "from_date": date(2026, 10, 19), "to_date": date(2026, 10, 25)},
        {"from_date": date(2026, 10, 19)},
        {"to_date": date(2026, 10, 19)},
        {"from_date": date(2026, 10, 20), "to_date": date(2026, 10, 19)},
        {"week": "2026-W99"},
    ],
    ids=["semana_y_rango", "solo_from", "solo_to", "invertido", "week_inexistente"],
)
async def test_filtros_de_fecha_incoherentes_dan_422(
    session: AsyncSession, consulta: dict[str, Any]
) -> None:
    with pytest.raises(ClassValidationError):
        await service.list_sessions(session, SessionListQuery(**consulta), PAGINA)


async def test_filtra_por_coach_y_por_estado_incluido_done(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    ya = await make_session(session, starts_at=reloj.now_utc() - timedelta(hours=3))
    proxima = await make_session(session, coach_id=coach.id)
    cancelada = await make_session(
        session,
        starts_at=datetime(2026, 10, 23, 11, 0, tzinfo=UTC),
        status="cancelled",
        cancel_reason="Feriado",
        cancelled_by=coach.id,
        cancelled_at=reloj.now_utc(),
    )
    semana = {"week": "2026-W43"}

    async def ids(**filtros: Any) -> set[UUID]:
        r = await service.list_sessions(session, SessionListQuery(**semana, **filtros), PAGINA)
        return {s.id for s in r.items}

    assert await ids(coach_id=coach.id) == {proxima.id}
    assert await ids(status="done") == {ya.id}
    assert await ids(status="scheduled") == {proxima.id}
    assert await ids(status="cancelled") == {cancelada.id}
    todas = (await service.list_sessions(session, SessionListQuery(**semana), PAGINA)).items
    assert {s.id: s.status for s in todas} == {
        ya.id: "done",
        proxima.id: "scheduled",
        cancelada.id: "cancelled",
    }


async def test_la_lista_pagina(session: AsyncSession) -> None:
    for hora in (11, 12, 13):
        await make_session(session, starts_at=datetime(2026, 10, 22, hora, 0, tzinfo=UTC))
    r = await service.list_sessions(
        session, SessionListQuery(week="2026-W43"), PageParams(limit=2, offset=2)
    )
    assert (r.total, len(r.items), r.items[0].starts_at.hour) == (3, 1, 13)


async def test_q_busca_por_nombre_sin_tildes_y_los_comodines_no_coinciden_con_todo(
    session: AsyncSession,
) -> None:
    uno = await make_session(session, name="Fuerza AM")
    await make_session(session, name="Cardio", starts_at=datetime(2026, 10, 22, 12, 0, tzinfo=UTC))
    consulta = SessionListQuery(week="2026-W43")
    r = await service.list_sessions(session, consulta, PAGINA, q="FUERZA")
    assert [s.id for s in r.items] == [uno.id]
    for comodin in ("%", "_", "zzz"):
        assert (await service.list_sessions(session, consulta, PAGINA, q=comodin)).total == 0
