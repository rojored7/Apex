"""Sesiones por HTTP (S7-B2, US-157; S7-D19, S7-D32). Rojo B2.

- Roles: admin y coach entran; el socio recibe 403; sin token 401.
- Contrato: claves exactas de `SessionOut`/`SessionDetail`, `Cache-Control: no-store`, 201 en el
  alta; lista `{items, total, limit, offset}`; `extra="forbid"`.
- Errores: 422 con `field` (`week`, `reason`, `starts_at`, `to`), 404 y los dos 409 de cancelar.
- Tope: las escrituras comparten `classes-write` (30 por minuto).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.modules.classes.router import router
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import make_session

SESIONES = "/api/v1/class-sessions"
CAMPOS = {
    "id",
    "slot_id",
    "session_date",
    "starts_at",
    "duration_min",
    "capacity",
    "coach_id",
    "coach_name",
    "name",
    "status",
    "attendance_count",
    "cancel_reason",
    "cancelled_at",
}
TOPE_ESCRITURAS = 30

pytestmark = pytest.mark.usefixtures("reloj")


def _cuerpo(**cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {"starts_at": "2026-10-22T06:00:00-05:00", "duration_min": 60}
    valores.update(cambios)
    return valores


def test_el_router_publica_las_rutas_de_sesiones_y_ningun_delete() -> None:
    publicadas = {
        (metodo, ruta.path)
        for ruta in router.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
    }
    assert {
        ("GET", "/class-sessions"),
        ("POST", "/class-sessions"),
        ("GET", "/class-sessions/{session_id}"),
        ("POST", "/class-sessions/{session_id}/cancel"),
    } <= publicadas
    assert not any(m in {"DELETE", "PUT"} and "sessions" in p for m, p in publicadas)


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_crean_listan_leen_y_cancelan(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, rol: str
) -> None:
    usuario = await usuario_real(rol)
    h = cabeceras(usuario)
    creada = await app_http.post(SESIONES, json=_cuerpo(), headers=h)
    assert creada.status_code == 201, creada.text
    assert set(creada.json()) == CAMPOS
    assert creada.headers["cache-control"] == "no-store"
    sid = creada.json()["id"]
    lista = await app_http.get(SESIONES, params={"week": "2026-W43"}, headers=h)
    assert lista.status_code == 200 and lista.headers["cache-control"] == "no-store"
    cuerpo = lista.json()
    assert set(cuerpo) == {"items", "total", "limit", "offset"} and cuerpo["total"] == 1
    assert set(cuerpo["items"][0]) == CAMPOS
    detalle = await app_http.get(f"{SESIONES}/{sid}", headers=h)
    assert detalle.status_code == 200
    assert set(detalle.json()) == CAMPOS | {"attendees"} and detalle.json()["attendees"] == []
    cancelada = await app_http.post(
        f"{SESIONES}/{sid}/cancel", json={"reason": "Corte de luz"}, headers=h
    )
    assert cancelada.status_code == 200
    assert (cancelada.json()["status"], cancelada.json()["cancel_reason"]) == (
        "cancelled",
        "Corte de luz",
    )
    assert cancelada.headers["cache-control"] == "no-store"


async def test_el_socio_recibe_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    sid = (await make_session_via_admin(app_http, usuario_real, cabeceras))["id"]
    h = cabeceras(socio)
    for metodo, ruta, cuerpo in (
        ("GET", SESIONES, None),
        ("POST", SESIONES, _cuerpo()),
        ("GET", f"{SESIONES}/{sid}", None),
        ("POST", f"{SESIONES}/{sid}/cancel", {"reason": "x"}),
    ):
        r = await app_http.request(metodo, ruta, json=cuerpo, headers=h)
        assert r.status_code == 403, (metodo, ruta)
        sin = await app_http.request(metodo, ruta, json=cuerpo)
        assert sin.status_code == 401, (metodo, ruta)


async def make_session_via_admin(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> dict[str, Any]:
    admin = await usuario_real("admin", email="creador@test.apex")
    r = await app_http.post(SESIONES, json=_cuerpo(), headers=cabeceras(admin))
    assert r.status_code == 201, r.text
    return dict(r.json())


async def test_errores_422_404_y_409(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    h = cabeceras(coach)
    sid = (await make_session_via_admin(app_http, usuario_real, cabeceras))["id"]
    for params, campo in (
        ({"week": "2026-W99"}, "week"),
        ({"week": "9999-W52"}, "week"),
        ({"week": "2026-W43", "from": "2026-10-19", "to": "2026-10-25"}, None),
        ({"from": "2026-10-01", "to": "2026-12-31"}, "to"),
        ({"from": "no-es-fecha", "to": "2026-12-31"}, "from"),
        ({"from": "9999-12-31", "to": "9999-12-31"}, "from"),  # S7-B2b: antes 500 (overflow)
        ({"from": "0001-01-01", "to": "0001-01-02"}, "from"),
        ({"from": "2100-12-31", "to": "2101-01-01"}, "to"),
        ({"status": "otra"}, "status"),
    ):
        r = await app_http.get(SESIONES, params=params, headers=h)
        assert r.status_code == 422, (params, r.text)
        if campo is not None:
            assert r.json()["error"]["field"] == campo, params
    for cuerpo, campo in (
        (_cuerpo(starts_at="2026-10-22T06:00:00"), "starts_at"),  # sin zona
        (_cuerpo(starts_at="2030-01-01T06:00:00-05:00"), "starts_at"),
        (_cuerpo(duration_min=10), "duration_min"),
        (_cuerpo(capacity=0), "capacity"),
        (_cuerpo(name="x" * 41), "name"),
    ):
        r = await app_http.post(SESIONES, json=cuerpo, headers=h)
        assert r.status_code == 422, (campo, r.text)
        assert r.json()["error"]["field"] == campo
    assert (
        await app_http.post(SESIONES, json=_cuerpo(slot_id=str(uuid4())), headers=h)
    ).status_code == 422
    otro_coach = await usuario_real("coach", email="otro@test.apex")
    r = await app_http.post(SESIONES, json=_cuerpo(coach_id=str(otro_coach.id)), headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "coach_invalid"
    for cuerpo in ({}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 201}, {"reason": 5}):
        r = await app_http.post(f"{SESIONES}/{sid}/cancel", json=cuerpo, headers=h)
        assert r.status_code == 422, cuerpo
        assert r.json()["error"]["field"] == "reason", cuerpo
    extra = await app_http.post(
        f"{SESIONES}/{sid}/cancel", json={"reason": "x", "otro": 1}, headers=h
    )
    assert extra.status_code == 422
    falta = await app_http.get(f"{SESIONES}/{uuid4()}", headers=h)
    assert (falta.status_code, falta.json()["error"]["code"]) == (404, "session_not_found")
    falta = await app_http.post(f"{SESIONES}/{uuid4()}/cancel", json={"reason": "x"}, headers=h)
    assert falta.status_code == 404
    assert (
        await app_http.post(f"{SESIONES}/{sid}/cancel", json={"reason": "a"}, headers=h)
    ).status_code == 200
    dos = await app_http.post(f"{SESIONES}/{sid}/cancel", json={"reason": "b"}, headers=h)
    assert (dos.status_code, dos.json()["error"]["code"]) == (409, "session_already_cancelled")


async def test_cancelar_una_sesion_terminada_da_409_session_finished(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: Any
) -> None:
    from datetime import UTC, datetime

    admin = await usuario_real("admin")
    pasada = await make_session(session, starts_at=datetime(2026, 10, 21, 10, 0, tzinfo=UTC))
    r = await app_http.post(
        f"{SESIONES}/{pasada.id}/cancel", json={"reason": "tarde"}, headers=cabeceras(admin)
    )
    assert (r.status_code, r.json()["error"]["code"]) == (409, "session_finished")


async def test_cubeta_classes_write(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    for _ in range(TOPE_ESCRITURAS):
        r = await app_http.post(f"{SESIONES}/{uuid4()}/cancel", json={"reason": "x"}, headers=h)
        assert r.status_code == 404
    r = await app_http.post(f"{SESIONES}/{uuid4()}/cancel", json={"reason": "x"}, headers=h)
    assert r.status_code == 429


async def test_sesion_extra_duplicada_409_por_http(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    primera = await app_http.post(SESIONES, json=_cuerpo(), headers=h)
    segunda = await app_http.post(SESIONES, json=_cuerpo(), headers=h)
    assert primera.status_code == 201 and segunda.status_code == 409, segunda.text
    assert segunda.json()["error"]["code"] == "session_duplicate"
