"""Movimientos por HTTP (S8-A1, US-165; S8-D22). Rojo A1.

- Admin y coach leen y escriben; `member` 403; sin token 401.
- Contrato: claves exactas de `CatalogMovementOut`, `Cache-Control: no-store`, 201 en el alta, lista
  `{items, total, limit, offset}`; no existe `DELETE`.
- 422 con `field`, 409 `movement_exists` con `existing_id`, 404 `movement_not_found`.
- Topes: las escrituras comparten `wods-write` (30 por minuto); un 403 no consume cupo.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.modules.wods.router import router
from tests.conftest import Cabeceras, CrearUsuario

MOVS = "/api/v1/movements"
CAMPOS = {
    "id",
    "name",
    "category",
    "unit",
    "is_active",
    "wod_count",
    "created_at",
    "updated_at",
}
TOPE_ESCRITURAS = 30


def _cuerpo(**cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {"name": "Back Squat", "category": "weightlifting", "unit": "kg"}
    valores.update(cambios)
    return valores


def test_el_router_publica_las_rutas_de_movimientos_y_ningun_delete() -> None:
    """A2 suma las de benchmarks y A3 las de WODs al mismo router plano (S2-D3)."""
    publicadas = {
        (metodo, ruta.path)
        for ruta in router.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
    }
    assert publicadas == {
        ("GET", "/movements"),
        ("POST", "/movements"),
        ("PATCH", "/movements/{movement_id}"),
        ("GET", "/benchmarks"),
        ("POST", "/benchmarks"),
        ("PATCH", "/benchmarks/{benchmark_id}"),
        ("GET", "/wods"),
        ("POST", "/wods"),
        ("GET", "/wods/{wod_id}"),
        ("PATCH", "/wods/{wod_id}"),
    }
    assert not any(m == "DELETE" for m, _ in publicadas)


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_crean_y_listan(
    rol: str, app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    quien = await usuario_real(rol)
    r = await app_http.post(MOVS, json=_cuerpo(), headers=cabeceras(quien))
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    datos = r.json()
    assert set(datos) == CAMPOS
    assert (datos["is_active"], datos["wod_count"]) == (True, 0)
    lista = await app_http.get(MOVS, headers=cabeceras(quien))
    assert lista.status_code == 200
    cuerpo = lista.json()
    assert (cuerpo["total"], cuerpo["limit"], cuerpo["offset"]) == (1, 25, 0)
    assert cuerpo["items"][0]["id"] == datos["id"]


async def test_socio_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    for metodo, ruta, cuerpo in (
        ("GET", MOVS, None),
        ("POST", MOVS, _cuerpo()),
        ("PATCH", f"{MOVS}/{uuid4()}", {"unit": "reps"}),
    ):
        r = await app_http.request(metodo, ruta, json=cuerpo, headers=cabeceras(socio))
        assert r.status_code == 403, (metodo, r.text)
        assert r.json()["error"]["code"] == "forbidden"
    sin = await app_http.get(MOVS)
    assert sin.status_code == 401
    assert sin.json()["error"]["code"] == "unauthorized"


async def test_422_de_category_y_unit(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("coach"))
    for cuerpo, campo in (
        (_cuerpo(category="cardio"), "category"),
        (_cuerpo(unit="lb"), "unit"),
        (_cuerpo(name=""), "name"),
        (_cuerpo(name="x" * 61), "name"),
    ):
        r = await app_http.post(MOVS, json=cuerpo, headers=h)
        assert r.status_code == 422, (campo, r.text)
        assert r.json()["error"]["field"] == campo
    extra = await app_http.post(MOVS, json=_cuerpo(otro=1), headers=h)
    assert extra.status_code == 422
    falta = await app_http.post(MOVS, json={"name": "X"}, headers=h)
    assert falta.status_code == 422


async def test_409_404_y_patch(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("admin"))
    primero = (await app_http.post(MOVS, json=_cuerpo(name="Pull-up"), headers=h)).json()
    repetido = await app_http.post(MOVS, json=_cuerpo(name=" pull-UP "), headers=h)
    assert repetido.status_code == 409
    error = repetido.json()["error"]
    assert (error["code"], error["field"], error["existing_id"]) == (
        "movement_exists",
        "name",
        primero["id"],
    )
    ok = await app_http.patch(f"{MOVS}/{primero['id']}", json={"is_active": False}, headers=h)
    assert ok.status_code == 200 and ok.json()["is_active"] is False
    nulo = await app_http.patch(f"{MOVS}/{primero['id']}", json={"name": None}, headers=h)
    assert nulo.status_code == 422 and nulo.json()["error"]["field"] == "name"
    falta = await app_http.patch(f"{MOVS}/{uuid4()}", json={"unit": "reps"}, headers=h)
    assert falta.status_code == 404
    assert falta.json()["error"]["code"] == "movement_not_found"


async def test_sin_ruta_delete(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("admin"))
    creada = (await app_http.post(MOVS, json=_cuerpo(), headers=h)).json()
    borrar = await app_http.delete(f"{MOVS}/{creada['id']}", headers=h)
    assert borrar.status_code == 405


async def test_lista_pagina_y_busca(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("coach"))
    for nombre, cat in (
        ("Arranque", "weightlifting"),
        ("Muscle-up", "gymnastics"),
        ("Remo", "monostructural"),
    ):
        await app_http.post(MOVS, json=_cuerpo(name=nombre, category=cat), headers=h)
    r = await app_http.get(MOVS, params={"limit": 2, "offset": 1}, headers=h)
    cuerpo = r.json()
    assert (cuerpo["total"], cuerpo["limit"], cuerpo["offset"]) == (3, 2, 1)
    assert [m["name"] for m in cuerpo["items"]] == ["Muscle-up", "Remo"]
    r = await app_http.get(MOVS, params={"q": "MUSCLE"}, headers=h)
    assert [m["name"] for m in r.json()["items"]] == ["Muscle-up"]
    r = await app_http.get(MOVS, params={"category": "monostructural"}, headers=h)
    assert [m["name"] for m in r.json()["items"]] == ["Remo"]
    r = await app_http.get(MOVS, params={"active": "false"}, headers=h)
    assert r.json()["total"] == 0
    r = await app_http.get(MOVS, params={"category": "cardio"}, headers=h)
    assert r.status_code == 422
    r = await app_http.get(MOVS, params={"limit": 201}, headers=h)
    assert r.status_code == 422


async def test_cubeta_wods_write(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("admin"))
    creada = (await app_http.post(MOVS, json=_cuerpo(), headers=h)).json()
    ruta = f"{MOVS}/{creada['id']}"
    for i in range(TOPE_ESCRITURAS - 1):  # el alta ya consumió una
        r = await app_http.patch(ruta, json={"unit": "reps" if i % 2 == 0 else "kg"}, headers=h)
        assert r.status_code == 200, (i, r.text)
    r = await app_http.patch(ruta, json={"unit": "m"}, headers=h)
    assert r.status_code == 429
    assert "retry-after" in r.headers


async def test_un_403_no_consume_cupo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    for _ in range(TOPE_ESCRITURAS + 2):
        r = await app_http.post(MOVS, json=_cuerpo(), headers=cabeceras(socio))
        assert r.status_code == 403
