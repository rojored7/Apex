"""Benchmarks por HTTP (S8-A2, US-166; S8-D6, L-6). Rojo A2.

Admin y coach leen y escriben; `member` 403; sin token 401. `GET /benchmarks` usa `PageParams` y
`staff-read`; las escrituras `wods-write`. No hay `DELETE`.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.conftest import Cabeceras, CrearUsuario

BENCH = "/api/v1/benchmarks"
CAMPOS = {"id", "name", "description", "score_type", "wod_count", "created_at", "updated_at"}


def _cuerpo(**cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {"name": "Fran", "description": "21-15-9", "score_type": "time"}
    valores.update(cambios)
    return valores


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach(
    rol: str, app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real(rol))
    r = await app_http.post(BENCH, json=_cuerpo(), headers=h)
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    assert set(r.json()) == CAMPOS
    creado = r.json()
    p = await app_http.patch(f"{BENCH}/{creado['id']}", json={"description": "x"}, headers=h)
    assert p.status_code == 200 and p.json()["description"] == "x"
    repetido = await app_http.post(BENCH, json=_cuerpo(name=" fran"), headers=h)
    assert repetido.status_code == 409
    error = repetido.json()["error"]
    assert (error["code"], error["field"], error["existing_id"]) == (
        "benchmark_exists",
        "name",
        creado["id"],
    )
    falta = await app_http.patch(f"{BENCH}/{uuid4()}", json={"name": "Z"}, headers=h)
    assert falta.status_code == 404 and falta.json()["error"]["code"] == "benchmark_not_found"
    borrar = await app_http.delete(f"{BENCH}/{creado['id']}", headers=h)
    assert borrar.status_code == 405


async def test_get_pagina_con_page_params_y_staff_read(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("coach"))
    for nombre, tipo in (("Annie", "time"), ("Cindy", "rounds_reps"), ("Mary", "rounds_reps")):
        await app_http.post(BENCH, json=_cuerpo(name=nombre, score_type=tipo), headers=h)
    r = await app_http.get(BENCH, params={"limit": 2, "offset": 1}, headers=h)
    cuerpo = r.json()
    assert (cuerpo["total"], cuerpo["limit"], cuerpo["offset"]) == (3, 2, 1)
    assert [b["name"] for b in cuerpo["items"]] == ["Cindy", "Mary"]
    r = await app_http.get(BENCH, params={"q": "CINDY"}, headers=h)
    assert [b["name"] for b in r.json()["items"]] == ["Cindy"]
    r = await app_http.get(BENCH, params={"score_type": "rounds_reps"}, headers=h)
    assert r.json()["total"] == 2
    assert (await app_http.get(BENCH, params={"score_type": "none"}, headers=h)).status_code == 422
    assert (await app_http.get(BENCH, params={"limit": 201}, headers=h)).status_code == 422
    ok = await app_http.get(BENCH, params={"limit": 25}, headers=h)
    assert ok.headers["cache-control"] == "no-store"


async def test_socio_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = cabeceras(await usuario_real("member"))
    for metodo, ruta, cuerpo in (
        ("GET", BENCH, None),
        ("POST", BENCH, _cuerpo()),
        ("PATCH", f"{BENCH}/{uuid4()}", {"name": "X"}),
    ):
        r = await app_http.request(metodo, ruta, json=cuerpo, headers=socio)
        assert r.status_code == 403, (metodo, r.text)
        assert r.json()["error"]["code"] == "forbidden"
    assert (await app_http.get(BENCH)).status_code == 401


async def test_422_de_los_campos(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("admin"))
    for cuerpo, campo in (
        (_cuerpo(score_type="none"), "score_type"),
        (_cuerpo(name=""), "name"),
        (_cuerpo(name="x" * 61), "name"),
        (_cuerpo(description="x" * 2001), "description"),
    ):
        r = await app_http.post(BENCH, json=cuerpo, headers=h)
        assert r.status_code == 422, (campo, r.text)
        assert r.json()["error"]["field"] == campo
    assert (await app_http.post(BENCH, json=_cuerpo(otro=1), headers=h)).status_code == 422
    assert (await app_http.post(BENCH, json={"name": "X"}, headers=h)).status_code == 422


async def test_el_tope_wods_write_se_agota_en_30_escrituras(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("admin"))
    creado = (await app_http.post(BENCH, json=_cuerpo(), headers=h)).json()
    ruta = f"{BENCH}/{creado['id']}"
    for i in range(29):  # el alta ya consumió una de las 30
        r = await app_http.patch(ruta, json={"description": f"d{i}"}, headers=h)
        assert r.status_code == 200, (i, r.text)
    r = await app_http.patch(ruta, json={"description": "ultima"}, headers=h)
    assert r.status_code == 429 and "retry-after" in r.headers
