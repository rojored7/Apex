"""`PUT /results` por HTTP (S8-B1, US-169): admin y coach; socio 403; 401; `results-write`."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import USER_LIMITS
from tests.conftest import Cabeceras, CrearUsuario
from tests.results._apoyo import Escena, escena

RESULTADOS = "/api/v1/results"
CAMPOS = {
    "id", "wod_id", "member_id", "session_id", "wod_date", "benchmark_id", "level", "seconds",
    "rounds", "reps", "load_g", "capped", "scaled_movement_ids", "status", "recorded_by",
    "validated_by", "validated_at", "supersedes_id", "is_current", "source", "created_at",
    "updated_at", "voided_by", "voided_at", "void_reason",
}  # fmt: skip

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


def _json(e: Escena, **cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {
        "wod_id": str(e.wod_id),
        "member_id": str(e.socio_id),
        "session_id": str(e.clase_id) if e.clase_id is not None else None,
        "level": "rx",
        "seconds": 300,
    }
    valores.update(cambios)
    return {k: v for k, v in valores.items() if v is not None}


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    e = await escena(session)
    usuario = await usuario_real(rol)
    r = await app_http.put(RESULTADOS, json=_json(e), headers=cabeceras(usuario))
    assert r.status_code == 201, r.text
    assert set(r.json()) == CAMPOS
    assert r.json()["status"] == "validated" and r.json()["source"] == "desk"
    assert r.json()["recorded_by"] == str(usuario.id)
    otra_vez = await app_http.put(RESULTADOS, json=_json(e), headers=cabeceras(usuario))
    assert otra_vez.status_code == 409 and otra_vez.json()["error"]["code"] == "result_exists"
    assert otra_vez.json()["error"]["existing_id"] == r.json()["id"]


async def test_socio_403(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena(session)
    r = await app_http.put(
        RESULTADOS, json=_json(e), headers=cabeceras(await usuario_real("member"))
    )
    assert r.status_code == 403
    sin_token = await app_http.put(RESULTADOS, json=_json(e))
    assert sin_token.status_code == 401


async def test_extra_forbid(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena(session)
    h = cabeceras(await usuario_real("coach"))
    for extra in ({"source": "kiosk"}, {"status": "pending"}, {"recorded_by": str(e.wod_id)}):
        r = await app_http.put(RESULTADOS, json=_json(e, **extra), headers=h)
        assert r.status_code == 422, extra
    decimal = await app_http.put(RESULTADOS, json=_json(e, load_g=1.5, seconds=None), headers=h)
    assert decimal.status_code == 422
    grande = await app_http.put(
        RESULTADOS, json=_json(e, load_g=1_000_001, seconds=None), headers=h
    )
    assert grande.status_code == 422


async def test_cubeta_results_write(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena(session)
    h = cabeceras(await usuario_real("coach"))
    tope, _ventana = USER_LIMITS["results-write"]
    cuerpo = _json(e, wod_id=str(uuid4()))  # 422 del service: la cubeta ya contó
    for _ in range(tope):
        assert (await app_http.put(RESULTADOS, json=cuerpo, headers=h)).status_code == 422
    r = await app_http.put(RESULTADOS, json=cuerpo, headers=h)
    assert r.status_code == 429 and "retry-after" in r.headers


async def test_no_store(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena(session)
    r = await app_http.put(
        RESULTADOS, json=_json(e), headers=cabeceras(await usuario_real("admin"))
    )
    assert r.headers["cache-control"] == "no-store"
