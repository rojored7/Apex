"""`GET /attendance/summary` con base real (S7-R1, US-162; S7-D15, M-5, L-1). Rojo R1.

Reloj `T0`: miércoles 21 de octubre de 2026, 10:00 en Bogotá. Semanas ISO de Bogotá: W42 desde
el lunes 12 y W43 desde el lunes 19. La asistencia se agrega en SQL (M-5): una sola consulta, sin
cargar una fila por asistencia. Solo cuentan sesiones programadas que ya empezaron y asistencias
vivas.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import USER_LIMITS
from app.modules.classes import service
from app.modules.classes.exceptions import ClassValidationError
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import make_attendance, make_session, make_slot
from tests.factories.members import make_members

RUTA = "/api/v1/attendance/summary"
LUNES_42 = datetime(2026, 10, 12, 11, 0, tzinfo=UTC)  # 06:00 de Bogotá
LUNES_43 = datetime(2026, 10, 19, 11, 0, tzinfo=UTC)
DESDE = date(2026, 10, 12)
HASTA = date(2026, 10, 25)

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def _siembra(session: AsyncSession) -> dict[str, Any]:
    """Franja «WOD» (06:00) con una sesión por semana más una extra en W43; 4 socios."""
    socios = await make_members(session, 4)
    franja = await make_slot(session, name="WOD", start_time="06:00")
    s42 = await make_session(session, slot_id=franja.id, starts_at=LUNES_42, capacity=10)
    s43 = await make_session(session, slot_id=franja.id, starts_at=LUNES_43, capacity=10)
    extra = await make_session(session, starts_at=LUNES_43 + timedelta(hours=7), capacity=5)
    await make_attendance(session, s42, socios[0].id)
    await make_attendance(session, s43, socios[0].id)
    await make_attendance(session, s43, socios[1].id, flags=["expired"])
    await make_attendance(session, s43, socios[2].id, flags=["other_day", "out_of_window"])
    await make_attendance(session, extra, socios[3].id)
    return {"socios": socios, "franja": franja, "s42": s42, "s43": s43, "extra": extra}


async def test_agrega_por_semana_y_franja(session: AsyncSession) -> None:
    datos = await _siembra(session)
    resumen = await service.attendance_summary(session, DESDE, HASTA)
    s42, s43 = resumen.weeks
    assert (s42.week, s42.week_start, s42.total, s42.flagged) == ("2026-W42", DESDE, 1, 0)
    assert (s43.week, s43.week_start) == ("2026-W43", date(2026, 10, 19))
    assert (s43.total, s43.flagged) == (4, 2)
    (wod42,) = s42.slots
    assert wod42.slot_id == datos["franja"].id and wod42.label == "WOD"
    assert (wod42.sessions, wod42.attendance, wod42.capacity_sum) == (1, 1, 10)
    assert wod42.occupancy_pct == 10
    wod43, extra43 = s43.slots
    assert (wod43.attendance, wod43.flagged, wod43.capacity_sum) == (3, 2, 10)
    assert wod43.occupancy_pct == 30
    assert (extra43.label, extra43.slot_id, extra43.start_time) == ("Extra", None, None)
    assert (extra43.attendance, extra43.capacity_sum, extra43.occupancy_pct) == (1, 5, 20)


async def test_semanas_sin_asistencias_vienen_en_cero(session: AsyncSession) -> None:
    await _siembra(session)
    resumen = await service.attendance_summary(session, date(2026, 9, 28), HASTA)
    assert [(s.week, s.total) for s in resumen.weeks] == [
        ("2026-W40", 0),
        ("2026-W41", 0),
        ("2026-W42", 1),
        ("2026-W43", 4),
    ]
    assert resumen.weeks[0].slots == []


async def test_semana_iso_de_bogota_no_de_utc(session: AsyncSession) -> None:
    """Domingo 18 a las 21:00 de Bogotá es lunes 19 01:00Z: pertenece a W42."""
    (socio,) = await make_members(session, 1)
    domingo = await make_session(session, starts_at=datetime(2026, 10, 19, 2, 0, tzinfo=UTC))
    assert domingo.session_date == date(2026, 10, 18)
    await make_attendance(session, domingo, socio.id)
    resumen = await service.attendance_summary(session, DESDE, HASTA)
    assert [(s.week, s.total) for s in resumen.weeks] == [("2026-W42", 1), ("2026-W43", 0)]


async def test_no_cuentan_quitadas_canceladas_futuras_ni_fuera_del_rango(
    session: AsyncSession,
) -> None:
    socios = await make_members(session, 4)
    base = await make_session(session, starts_at=LUNES_43, capacity=10)
    await make_attendance(session, base, socios[0].id)
    await make_attendance(session, base, socios[1].id, removed_at=LUNES_43, removed_reason="x")
    cancelada = await make_session(
        session,
        starts_at=LUNES_43 + timedelta(days=1),
        status="cancelled",
        cancel_reason="Lluvia",
        cancelled_by=socios[0].id,
        cancelled_at=LUNES_43,
    )
    await make_attendance(session, cancelada, socios[2].id)
    futura = await make_session(session, starts_at=datetime(2026, 10, 23, 11, 0, tzinfo=UTC))
    await make_attendance(session, futura, socios[3].id)
    vieja = await make_session(session, starts_at=LUNES_42 - timedelta(days=30))
    await make_attendance(session, vieja, socios[0].id)
    resumen = await service.attendance_summary(session, DESDE, HASTA)
    s43 = resumen.weeks[1]
    assert s43.total == 1
    (franja,) = s43.slots
    assert (franja.sessions, franja.capacity_sum) == (1, 10)
    assert resumen.weeks[0].total == 0


async def test_26_semanas(session: AsyncSession) -> None:
    desde = date(2026, 4, 27)  # lunes
    resumen = await service.attendance_summary(session, desde, desde + timedelta(days=7 * 26 - 1))
    assert len(resumen.weeks) == 26
    assert resumen.weeks[0].week_start == desde
    assert all(s.total == 0 and s.slots == [] for s in resumen.weeks)


async def test_mas_de_26_da_422_from(session: AsyncSession) -> None:
    desde = date(2026, 4, 27)
    with pytest.raises(ClassValidationError) as caught:
        await service.attendance_summary(session, desde, desde + timedelta(days=7 * 26))
    assert (caught.value.status, caught.value.field) == (422, "from")


async def test_from_mayor_que_to_da_422_from(session: AsyncSession) -> None:
    with pytest.raises(ClassValidationError) as caught:
        await service.attendance_summary(session, date(2026, 10, 31), date(2026, 10, 1))
    assert caught.value.field == "from"


@pytest.mark.parametrize("desde", [date(2019, 12, 1), date(2101, 1, 1)])
async def test_anio_fuera_de_rango_422(session: AsyncSession, desde: date) -> None:
    with pytest.raises(ClassValidationError) as caught:
        await service.attendance_summary(session, desde, desde + timedelta(days=3))
    assert caught.value.field == "from"


async def test_agrega_en_sql(session: AsyncSession) -> None:
    """M-5: una sola consulta que agrupa; 12 asistencias salen como un solo grupo."""
    franja = await make_slot(session, name="WOD")
    clase = await make_session(session, slot_id=franja.id, starts_at=LUNES_43, capacity=20)
    for socio in await make_members(session, 12):
        await make_attendance(session, clase, socio.id)
    motor = session.get_bind()
    consultas: list[str] = []

    def _anota(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            consultas.append(statement)

    event.listen(motor, "before_cursor_execute", _anota)
    try:
        resumen = await service.attendance_summary(session, DESDE, HASTA)
    finally:
        event.remove(motor, "before_cursor_execute", _anota)
    assert len(consultas) == 1, consultas
    texto = consultas[0].lower()
    assert "group by" in texto and "classes.attendance" in texto
    assert resumen.weeks[1].total == 12 and len(resumen.weeks[1].slots) == 1


# HTTP ------------------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_staff_lee_el_resumen(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    rol: str,
) -> None:
    usuario = await usuario_real(rol)
    await _siembra(session)
    r = await app_http.get(
        RUTA, params={"from": "2026-10-12", "to": "2026-10-25"}, headers=cabeceras(usuario)
    )
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.json()
    assert [s["week"] for s in cuerpo["weeks"]] == ["2026-W42", "2026-W43"]
    assert cuerpo["weeks"][1]["slots"][0]["occupancy_pct"] == 30


async def test_socio_403_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    params = {"from": "2026-10-12", "to": "2026-10-25"}
    assert (await app_http.get(RUTA, params=params)).status_code == 401
    assert (await app_http.get(RUTA, params=params, headers=cabeceras(socio))).status_code == 403


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-10-31", "to": "2026-10-01"},
        {"from": "2026-01-01", "to": "2026-12-31"},
        {"from": "2019-01-01", "to": "2019-01-07"},
    ],
)
async def test_http_422_con_field_from(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, params: dict[str, str]
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(RUTA, params=params, headers=cabeceras(coach))
    assert r.status_code == 422
    assert r.json()["error"]["field"] == "from"


@pytest.mark.parametrize("params", [{}, {"from": "2026-10-01"}, {"from": "ayer", "to": "hoy"}])
async def test_http_422_sin_fechas_o_mal_formadas(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, params: dict[str, str]
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(RUTA, params=params, headers=cabeceras(coach))
    assert r.status_code == 422


async def test_consume_la_cubeta_staff_read(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    tope = USER_LIMITS["staff-read"][0]
    h = cabeceras(await usuario_real("coach"))
    params = {"from": "2026-10-12", "to": "2026-10-18"}
    for _ in range(tope):
        assert (await app_http.get(RUTA, params=params, headers=h)).status_code == 200
    assert (await app_http.get(RUTA, params=params, headers=h)).status_code == 429
