"""`POST /attendance` y `GET /attendance` por HTTP (S7-C1, US-159; S7-D12, L-1). Rojo C1.

Admin y coach; el socio recibe 403 y sin token 401. 201 con `flags`, nunca 409 ni 422 por cupo,
hora, día o membresía; cubeta `attendance-write` (60 por minuto); sin campos cifrados.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.classes.router import router
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import FakeMembershipPort, make_session
from tests.factories.members import make_members

RUTA = "/api/v1/attendance"
EN_VENTANA = datetime(2026, 10, 21, 15, 10, tzinfo=UTC)
TOPE_ESCRITURAS = 60
CAMPOS_CIFRADOS = {"document", "phone", "email", "birth_date", "emergency_contact"}

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


def _cuerpo(session_id: object, member_id: object, **extra: Any) -> dict[str, Any]:
    return {"session_id": str(session_id), "member_id": str(member_id), **extra}


def test_el_router_publica_las_rutas_de_asistencia() -> None:
    publicadas = {
        (metodo, ruta.path)
        for ruta in router.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
    }
    assert {("POST", "/attendance"), ("GET", "/attendance")} <= publicadas


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_staff_registra_con_201_y_flags(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
    rol: str,
) -> None:
    usuario = await usuario_real(rol)
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    puerto.status = "expired"
    r = await app_http.post(RUTA, json=_cuerpo(sesion.id, socio.id), headers=cabeceras(usuario))
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {
        "id",
        "flags",
        "flagged",
        "membership_status_at_checkin",
        "attendance_count",
        "capacity",
    }
    assert cuerpo["flags"] == ["expired"] and cuerpo["flagged"] is True
    assert cuerpo["attendance_count"] == 1 and cuerpo["capacity"] == 15
    assert r.headers["cache-control"] == "no-store"


async def test_socio_403_y_sin_token_401(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
) -> None:
    socio_usuario = await usuario_real("member")
    cuerpo = _cuerpo(uuid4(), uuid4())
    r = await app_http.post(RUTA, json=cuerpo, headers=cabeceras(socio_usuario))
    assert r.status_code == 403
    assert (await app_http.post(RUTA, json=cuerpo)).status_code == 401
    assert (await app_http.get(RUTA)).status_code == 401
    assert (await app_http.get(RUTA, headers=cabeceras(socio_usuario))).status_code == 403


async def test_el_duplicado_y_la_cancelada_son_409_con_su_codigo(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    h = cabeceras(coach)
    socio_id, sesion_id, coach_id = socio.id, sesion.id, coach.id  # la petición expira los objetos
    ok = await app_http.post(RUTA, json=_cuerpo(sesion_id, socio_id), headers=h)
    assert ok.status_code == 201
    r = await app_http.post(RUTA, json=_cuerpo(sesion_id, socio_id), headers=h)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "already_checked_in")
    cancelada = await make_session(
        session,
        starts_at=datetime(2026, 10, 21, 16, 10, tzinfo=UTC),
        status="cancelled",
        cancel_reason="Feriado",
        cancelled_by=coach_id,
        cancelled_at=EN_VENTANA,
    )
    r = await app_http.post(RUTA, json=_cuerpo(cancelada.id, socio_id), headers=h)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "session_cancelled")


async def test_cupo_hora_dia_y_membresia_nunca_dan_409_ni_422(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
) -> None:
    coach = await usuario_real("coach")
    socios = await make_members(session, 3)
    vieja = await make_session(
        session, starts_at=datetime(2026, 9, 21, 23, 0, tzinfo=UTC), capacity=1
    )
    puerto.status = "frozen"
    h = cabeceras(coach)
    banderas = []
    for socio in socios:
        r = await app_http.post(RUTA, json=_cuerpo(vieja.id, socio.id), headers=h)
        assert r.status_code == 201, r.text
        banderas.append(set(r.json()["flags"]))
    assert banderas[0] == {"frozen", "out_of_window", "other_day"}
    assert banderas[1] == {"frozen", "over_capacity", "out_of_window", "other_day"}


@pytest.mark.parametrize(
    "extra",
    [
        {"membership_id": str(uuid4())},
        {"flags": []},
        {"checked_in_at": "2026-10-21T15:00:00Z"},
    ],
)
async def test_422_con_campos_que_decide_el_servidor(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
    extra: dict[str, Any],
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.post(RUTA, json=_cuerpo(uuid4(), uuid4(), **extra), headers=cabeceras(coach))
    assert r.status_code == 422


async def test_404_de_socio_y_de_sesion(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    socio_id, sesion_id = socio.id, sesion.id
    h = cabeceras(coach)
    r = await app_http.post(RUTA, json=_cuerpo(sesion_id, uuid4()), headers=h)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "member_not_found")
    r = await app_http.post(RUTA, json=_cuerpo(uuid4(), socio_id), headers=h)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "session_not_found")


async def test_cubeta_attendance_write(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
) -> None:
    coach = await usuario_real("coach")
    h = cabeceras(coach)
    for _ in range(TOPE_ESCRITURAS):
        r = await app_http.post(RUTA, json=_cuerpo(uuid4(), uuid4()), headers=h)
        assert r.status_code == 404
    r = await app_http.post(RUTA, json=_cuerpo(uuid4(), uuid4()), headers=h)
    assert r.status_code == 429


async def test_get_attendance_lista_filtra_y_no_trae_campos_cifrados(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
) -> None:
    coach = await usuario_real("coach")
    uno, otro = await make_members(session, 2)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    h = cabeceras(coach)
    puerto.status = "expired"
    await app_http.post(RUTA, json=_cuerpo(sesion.id, uno.id), headers=h)
    puerto.status = "active"
    await app_http.post(RUTA, json=_cuerpo(sesion.id, otro.id), headers=h)

    r = await app_http.get(RUTA, headers=h)
    assert r.status_code == 200, r.text
    pagina = r.json()
    assert pagina["total"] == 2 and len(pagina["items"]) == 2
    fila = pagina["items"][0]
    assert CAMPOS_CIFRADOS.isdisjoint(fila)
    assert {"id", "member_id", "first_name", "last_name", "flags", "flagged"} <= set(fila)
    assert pagina["items"][0]["checked_in_at"] >= pagina["items"][1]["checked_in_at"]

    solo_marcadas = (await app_http.get(RUTA, params={"flagged": "true"}, headers=h)).json()
    assert [i["member_id"] for i in solo_marcadas["items"]] == [str(uno.id)]
    del_socio = (await app_http.get(RUTA, params={"member_id": str(otro.id)}, headers=h)).json()
    assert [i["member_id"] for i in del_socio["items"]] == [str(otro.id)]
    de_sesion = (await app_http.get(RUTA, params={"session_id": str(sesion.id)}, headers=h)).json()
    assert de_sesion["total"] == 2


@pytest.mark.parametrize(
    ("params", "campo"),
    [
        ({"from": "2019-01-01T00:00:00Z"}, "from"),
        ({"to": "2099-01-01T00:00:00Z"}, "to"),
        ({"from": "2026-10-21T12:00:00Z", "to": "2026-10-21T11:00:00Z"}, "to"),
        ({"from": "2026-10-21T12:00:00"}, "from"),  # sin zona horaria
    ],
)
async def test_get_attendance_rango_invalido_422(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    params: dict[str, str],
    campo: str,
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(RUTA, params=params, headers=cabeceras(coach))
    assert r.status_code == 422
    assert r.json()["error"].get("field") == campo


async def test_el_detalle_y_la_lista_de_sesiones_traen_asistentes_y_conteo(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
) -> None:
    """US-159: `GET /class-sessions/{id}` con asistentes y `attendance_count` real."""
    coach = await usuario_real("coach")
    uno, otro = await make_members(session, 2)
    sesion = await make_session(session, starts_at=EN_VENTANA)
    h = cabeceras(coach)
    puerto.status = "expired"
    await app_http.post(RUTA, json=_cuerpo(sesion.id, uno.id), headers=h)
    puerto.status = "active"
    await app_http.post(RUTA, json=_cuerpo(sesion.id, otro.id), headers=h)
    detalle = (await app_http.get(f"/api/v1/class-sessions/{sesion.id}", headers=h)).json()
    assert detalle["attendance_count"] == 2 and len(detalle["attendees"]) == 2
    marcados = {a["member_id"]: a for a in detalle["attendees"]}
    assert marcados[str(uno.id)]["flagged"] is True and marcados[str(uno.id)]["flags"] == [
        "expired"
    ]
    assert marcados[str(otro.id)]["flagged"] is False
    assert CAMPOS_CIFRADOS.isdisjoint(detalle["attendees"][0])
    lista = (await app_http.get("/api/v1/class-sessions", headers=h)).json()
    assert [s["attendance_count"] for s in lista["items"]] == [2]


async def test_get_attendance_busca_por_q_del_socio(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
) -> None:
    """Regla de datos 6: la lista acepta búsqueda (`q` por nombre del socio)."""
    coach = await usuario_real("coach")
    uno, otro = await make_members(session, 2)  # «Lucía 0» y «Lucía 1»
    sesion = await make_session(session, starts_at=EN_VENTANA)
    uno_id, otro_id, sesion_id = uno.id, otro.id, sesion.id
    h = cabeceras(coach)
    await app_http.post(RUTA, json=_cuerpo(sesion_id, uno_id), headers=h)
    await app_http.post(RUTA, json=_cuerpo(sesion_id, otro_id), headers=h)
    r = await app_http.get(RUTA, params={"q": "Lucía 1"}, headers=h)
    assert r.status_code == 200, r.text
    assert [i["member_id"] for i in r.json()["items"]] == [str(otro_id)]
    vacio = (await app_http.get(RUTA, params={"q": "Zzzzz"}, headers=h)).json()
    assert vacio["total"] == 0 and vacio["items"] == []
