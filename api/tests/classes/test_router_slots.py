"""Franjas por HTTP (S7-A2, US-155; S7-D19). Rojo A2.

- Solo admin: el coach recibe 403 también al leer (`GET`); `member` 403; sin token 401.
- Contrato: claves exactas de `SlotOut`, `Cache-Control: no-store`, 201 en el alta, lista
  `{items, total, limit, offset}`; no existe `DELETE`.
- 422 con `field`, 409 `slot_conflict`, 404 `slot_not_found`, 422 `coach_invalid`.
- Topes: las escrituras comparten `classes-write` (30 por minuto); un 403 no consume cupo.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.modules.classes.router import router
from tests.conftest import Cabeceras, CrearUsuario

SLOTS = "/api/v1/class-slots"
CAMPOS = {
    "id",
    "name",
    "weekdays",
    "start_time",
    "duration_min",
    "capacity",
    "default_coach_id",
    "coach_name",
    "valid_from",
    "is_active",
    "created_at",
    "updated_at",
}
TOPE_ESCRITURAS = 30

pytestmark = pytest.mark.usefixtures("reloj")


def _cuerpo(**cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {"weekdays": [0, 2], "start_time": "06:00", "duration_min": 60}
    valores.update(cambios)
    return valores


def test_el_router_publica_tres_rutas_y_ningun_delete() -> None:
    publicadas = {
        (metodo, ruta.path)
        for ruta in router.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
    }
    assert publicadas == {
        ("GET", "/class-slots"),
        ("POST", "/class-slots"),
        ("PATCH", "/class-slots/{slot_id}"),
    }


async def test_admin_crea_y_lista(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(SLOTS, json=_cuerpo(name="WOD"), headers=cabeceras(admin))
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    datos = r.json()
    assert set(datos) == CAMPOS
    assert (datos["weekdays"], datos["start_time"], datos["capacity"]) == ([0, 2], "06:00", 15)
    lista = await app_http.get(SLOTS, headers=cabeceras(admin))
    assert lista.status_code == 200
    assert lista.headers["cache-control"] == "no-store"
    cuerpo = lista.json()
    assert (cuerpo["total"], cuerpo["limit"], cuerpo["offset"]) == (1, 25, 0)
    assert cuerpo["items"][0]["id"] == datos["id"]


async def test_filtros_de_la_lista(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    await app_http.post(SLOTS, json=_cuerpo(weekdays=[0]), headers=cabeceras(admin))
    await app_http.post(
        SLOTS, json=_cuerpo(weekdays=[1], start_time="07:00"), headers=cabeceras(admin)
    )
    r = await app_http.get(SLOTS, params={"weekday": 1}, headers=cabeceras(admin))
    assert [s["start_time"] for s in r.json()["items"]] == ["07:00"]
    r = await app_http.get(SLOTS, params={"is_active": "false"}, headers=cabeceras(admin))
    assert r.json()["total"] == 0
    r = await app_http.get(SLOTS, params={"weekday": 9}, headers=cabeceras(admin))
    assert r.status_code == 422


async def test_coach_403_tambien_en_get(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    for metodo, ruta, cuerpo in (
        ("GET", SLOTS, None),
        ("POST", SLOTS, _cuerpo()),
        ("PATCH", f"{SLOTS}/{uuid4()}", {"capacity": 5}),
    ):
        r = await app_http.request(metodo, ruta, json=cuerpo, headers=cabeceras(coach))
        assert r.status_code == 403, (metodo, r.text)
        assert r.json()["error"]["code"] == "forbidden"


async def test_member_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    r = await app_http.get(SLOTS, headers=cabeceras(socio))
    assert r.status_code == 403
    sin = await app_http.get(SLOTS)
    assert sin.status_code == 401
    assert sin.json()["error"]["code"] == "unauthorized"


async def test_patch_pausa_y_no_existe_delete(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    creada = (await app_http.post(SLOTS, json=_cuerpo(), headers=cabeceras(admin))).json()
    r = await app_http.patch(
        f"{SLOTS}/{creada['id']}", json={"is_active": False}, headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False
    borrar = await app_http.delete(f"{SLOTS}/{creada['id']}", headers=cabeceras(admin))
    assert borrar.status_code == 405


async def test_errores_409_422_y_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    socio = await usuario_real("member")
    h = cabeceras(admin)
    primera = (await app_http.post(SLOTS, json=_cuerpo(), headers=h)).json()
    choque = await app_http.post(SLOTS, json=_cuerpo(weekdays=[2, 3]), headers=h)
    assert choque.status_code == 409
    assert choque.json()["error"]["code"] == "slot_conflict"
    assert choque.json()["error"]["existing_id"] == primera["id"]
    for cuerpo, campo in (
        (_cuerpo(weekdays=[]), "weekdays"),
        (_cuerpo(weekdays=[0, 0]), "weekdays"),
        (_cuerpo(start_time="25:00"), "start_time"),
        (_cuerpo(duration_min=10), "duration_min"),
        (_cuerpo(capacity=0), "capacity"),
        (_cuerpo(name="x" * 41), "name"),
    ):
        r = await app_http.post(SLOTS, json=cuerpo, headers=h)
        assert r.status_code == 422, (campo, r.text)
        assert r.json()["error"]["field"] == campo
    extra = await app_http.post(SLOTS, json=_cuerpo(otro=1), headers=h)
    assert extra.status_code == 422
    coach = await app_http.post(
        SLOTS, json=_cuerpo(weekdays=[5], default_coach_id=str(socio.id)), headers=h
    )
    assert coach.status_code == 422
    assert coach.json()["error"]["code"] == "coach_invalid"
    falta = await app_http.patch(f"{SLOTS}/{uuid4()}", json={"capacity": 3}, headers=h)
    assert falta.status_code == 404
    assert falta.json()["error"]["code"] == "slot_not_found"


async def test_cubeta_classes_write(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    creada = (await app_http.post(SLOTS, json=_cuerpo(), headers=h)).json()
    ruta = f"{SLOTS}/{creada['id']}"
    for i in range(TOPE_ESCRITURAS - 1):  # el alta ya consumió una
        r = await app_http.patch(ruta, json={"capacity": 10 + (i % 5)}, headers=h)
        assert r.status_code == 200, (i, r.text)
    r = await app_http.patch(ruta, json={"capacity": 50}, headers=h)
    assert r.status_code == 429
    assert "retry-after" in r.headers
