"""WODs por HTTP (S8-A3, US-166, US-167; S8-D7, S8-D8). Rojo A3.

Admin y coach leen y escriben; `member` 403; sin token 401. Lecturas con `staff-read`, escrituras
con `wods-write` (30 por minuto). `GET /wods`: `week` o `q`/`benchmark`, no ambos.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.modules.wods.router import router
from tests.conftest import Cabeceras, CrearUsuario

WODS = "/api/v1/wods"
MOVS = "/api/v1/movements"
TOPE_ESCRITURAS = 30
CAMPOS = {
    "id", "date", "title", "score_type", "time_cap_s", "benchmark_id", "benchmark_name",
    "is_benchmark", "description", "movements", "result_count", "created_at", "updated_at",
}  # fmt: skip
CAMPOS_MOV = {
    "id", "movement_id", "movement_name", "position", "reps", "load_rx_m_g", "load_rx_f_g",
    "notes", "is_primary",
}  # fmt: skip
CAMPOS_FILA = {
    "id", "date", "title", "score_type", "time_cap_s", "benchmark_id", "benchmark_name",
    "is_benchmark", "movement_count", "movement_names", "result_count",
}  # fmt: skip


async def _movimiento(app_http: AsyncClient, h: dict[str, str], nombre: str = "Thruster") -> str:
    r = await app_http.post(
        MOVS, json={"name": nombre, "category": "weightlifting", "unit": "kg"}, headers=h
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _cuerpo(mid: str, **cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {
        "date": "2026-10-22",
        "title": "Fran",
        "score_type": "time",
        "time_cap_s": 600,
        "description": "21-15-9",
        "movements": [
            {"movement_id": mid, "position": 1, "reps": "21-15-9", "is_primary": True,
             "load_rx_m_g": 43_000, "load_rx_f_g": 30_000},
        ],
    }  # fmt: skip
    valores.update(cambios)
    return valores


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_crean_leen_y_editan(
    rol: str, app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real(rol))
    mid = await _movimiento(app_http, h)
    r = await app_http.post(WODS, json=_cuerpo(mid), headers=h)
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    creado = r.json()
    assert set(creado) == CAMPOS and set(creado["movements"][0]) == CAMPOS_MOV
    assert creado["movements"][0]["load_rx_m_g"] == 43_000
    g = await app_http.get(f"{WODS}/{creado['id']}", headers=h)
    assert g.status_code == 200 and g.json() == creado
    p = await app_http.patch(f"{WODS}/{creado['id']}", json={"title": "Fran RX"}, headers=h)
    assert p.status_code == 200 and p.json()["title"] == "Fran RX"
    assert (await app_http.get(f"{WODS}/{uuid4()}", headers=h)).status_code == 404
    falta = await app_http.patch(f"{WODS}/{uuid4()}", json={"title": "x"}, headers=h)
    assert falta.status_code == 404 and falta.json()["error"]["code"] == "wod_not_found"
    assert (await app_http.delete(f"{WODS}/{creado['id']}", headers=h)).status_code == 405


async def test_409_wod_date_taken_con_existing_id_y_422_de_forma(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("coach"))
    mid = await _movimiento(app_http, h)
    creado = (await app_http.post(WODS, json=_cuerpo(mid), headers=h)).json()
    repetido = await app_http.post(WODS, json=_cuerpo(mid, title="Otro"), headers=h)
    error = repetido.json()["error"]
    assert repetido.status_code == 409
    assert (error["code"], error["field"], error["existing_id"]) == (
        "wod_date_taken", "date", creado["id"]
    )  # fmt: skip
    casos: list[tuple[dict[str, Any], str]] = [
        ({"score_type": "xx"}, "score_type"),
        ({"time_cap_s": -5}, "time_cap_s"),
        ({"movements": []}, "movements"),
        ({"title": ""}, "title"),
        ({"date": "no-fecha"}, "date"),
        ({"extra": 1}, "extra"),
    ]
    for cambios, campo in casos:
        r = await app_http.post(
            WODS, json=_cuerpo(mid, **{"date": "2026-10-30", **cambios}), headers=h
        )
        assert r.status_code == 422, (campo, r.text)
        assert r.json()["error"]["field"] == campo, (campo, r.json())
    dos = _cuerpo(mid, date="2026-10-31")
    dos["movements"].append({**dos["movements"][0], "position": 2})  # dos principales
    r = await app_http.post(WODS, json=dos, headers=h)
    assert r.status_code == 422 and r.json()["error"]["field"] == "movements"


async def test_cargas_negativas_o_decimales_dan_422_con_field(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("coach"))
    mid = await _movimiento(app_http, h)
    for malo in (-1, 1_000_001, 43.5):
        cuerpo = _cuerpo(mid)
        cuerpo["movements"][0]["load_rx_m_g"] = malo
        r = await app_http.post(WODS, json=cuerpo, headers=h)
        assert r.status_code == 422, (malo, r.text)
        assert "load_rx_m_g" in r.json()["error"]["field"]


async def test_week_y_q_se_excluyen_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("coach"))
    for params in ({"week": "2026-W43", "q": "fran"}, {"week": "2026-W43", "benchmark": "true"}):
        r = await app_http.get(WODS, params=params, headers=h)
        assert r.status_code == 422 and r.json()["error"]["field"] == "week", params
    r = await app_http.get(WODS, params={"week": "2026-43"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["field"] == "week"
    assert (await app_http.get(WODS, params={"limit": 201}, headers=h)).status_code == 422


async def test_lista_trae_movement_count_names_y_result_count(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("coach"))
    thr = await _movimiento(app_http, h)
    pul = await _movimiento(app_http, h, "Pull-up")
    cuerpo = _cuerpo(thr)
    cuerpo["movements"].append({"movement_id": pul, "position": 2, "reps": "21-15-9"})
    await app_http.post(WODS, json=cuerpo, headers=h)
    r = await app_http.get(WODS, params={"week": "2026-W43"}, headers=h)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    cuerpo_r = r.json()
    assert (cuerpo_r["total"], len(cuerpo_r["items"])) == (1, 1)
    fila = cuerpo_r["items"][0]
    assert set(fila) == CAMPOS_FILA
    assert (fila["movement_count"], fila["movement_names"], fila["result_count"]) == (
        2, ["Thruster", "Pull-up"], 0
    )  # fmt: skip
    vacia = await app_http.get(WODS, params={"week": "2026-W44"}, headers=h)
    assert vacia.json()["items"] == []
    q = await app_http.get(WODS, params={"q": "fran", "benchmark": "false"}, headers=h)
    assert q.json()["total"] == 1


async def test_socio_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    uno = uuid4()
    for metodo, ruta, cuerpo in (
        ("GET", WODS, None),
        ("POST", WODS, _cuerpo(str(uno))),
        ("GET", f"{WODS}/{uno}", None),
        ("PATCH", f"{WODS}/{uno}", {"title": "x"}),
    ):
        r = await app_http.request(metodo, ruta, json=cuerpo, headers=cabeceras(socio))
        assert r.status_code == 403, (metodo, r.text)
        assert r.json()["error"]["code"] == "forbidden"
    sin = await app_http.get(WODS)
    assert sin.status_code == 401 and sin.json()["error"]["code"] == "unauthorized"


async def test_cubeta_wods_write(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("admin"))
    mid = await _movimiento(app_http, h)  # consume una
    creado = (await app_http.post(WODS, json=_cuerpo(mid), headers=h)).json()  # y esta, otra
    ruta = f"{WODS}/{creado['id']}"
    for i in range(TOPE_ESCRITURAS - 2):
        r = await app_http.patch(ruta, json={"title": f"Fran {i}"}, headers=h)
        assert r.status_code == 200, (i, r.text)
    r = await app_http.patch(ruta, json={"title": "Fran final"}, headers=h)
    assert r.status_code == 429 and "retry-after" in r.headers


def test_el_router_publica_las_cuatro_rutas_de_wods_y_ningun_delete() -> None:
    rutas = {(m, r.path) for r in router.routes if isinstance(r, APIRoute) for m in r.methods}
    assert {
        ("GET", "/wods"), ("POST", "/wods"), ("GET", "/wods/{wod_id}"), ("PATCH", "/wods/{wod_id}")
    } <= rutas  # fmt: skip
    assert not any(m == "DELETE" and "wods" in p for m, p in rutas)
    assert UUID  # el id de ruta es un UUID
