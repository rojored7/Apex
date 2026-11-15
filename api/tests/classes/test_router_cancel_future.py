"""`POST /class-slots/{id}/cancel-future-sessions` por HTTP (S7-B3, US-158; S7-D19). Rojo B3.

Solo admin (el coach y el socio reciben 403, sin token 401); motivo obligatorio (422);
franja inexistente 404; respuesta `{cancelled_count}` con `Cache-Control: no-store`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.classes.router import router
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import make_session, make_slot

pytestmark = pytest.mark.usefixtures("reloj")


def _ruta(slot_id: object) -> str:
    return f"/api/v1/class-slots/{slot_id}/cancel-future-sessions"


def test_el_router_publica_la_ruta() -> None:
    publicadas = {
        (metodo, ruta.path)
        for ruta in router.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
    }
    assert ("POST", "/class-slots/{slot_id}/cancel-future-sessions") in publicadas


async def test_admin_cancela_y_recibe_el_conteo(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    admin = await usuario_real("admin")
    franja = await make_slot(session)
    for dia in (26, 28):
        await make_session(
            session, slot_id=franja.id, starts_at=datetime(2026, 10, dia, 11, 0, tzinfo=UTC)
        )
    r = await app_http.post(
        _ruta(franja.id), json={"reason": "Cierre por festivo"}, headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"cancelled_count": 2}
    assert r.headers["cache-control"] == "no-store"
    otra = await app_http.post(
        _ruta(franja.id), json={"reason": "Otra vez"}, headers=cabeceras(admin)
    )
    assert otra.status_code == 200 and otra.json() == {"cancelled_count": 0}


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_socio_403_y_sin_token_401(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    rol: str,
) -> None:
    usuario = await usuario_real(rol)
    ruta = _ruta((await make_slot(session)).id)
    r = await app_http.post(ruta, json={"reason": "x"}, headers=cabeceras(usuario))
    assert r.status_code == 403
    sin = await app_http.post(ruta, json={"reason": "x"})
    assert sin.status_code == 401


@pytest.mark.parametrize(
    "cuerpo",
    [{}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 201}, {"reason": "a", "x": 1}],
)
async def test_422_sin_motivo_o_con_campos_de_mas(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    cuerpo: dict[str, object],
) -> None:
    admin = await usuario_real("admin")
    franja = await make_slot(session)
    r = await app_http.post(_ruta(franja.id), json=cuerpo, headers=cabeceras(admin))
    assert r.status_code == 422


async def test_franja_inexistente_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(_ruta(uuid4()), json={"reason": "x"}, headers=cabeceras(admin))
    assert r.status_code == 404 and r.json()["error"]["code"] == "slot_not_found"
