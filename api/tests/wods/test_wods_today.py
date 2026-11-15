"""`GET /wods/today` (S8-A4, US-168 CA1; S8-D9). El día es el de Bogotá (Q28)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.wods import make_movement, make_wod

HOY = "/api/v1/wods/today"


async def test_null_con_200(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, reloj: FrozenClock
) -> None:
    h = cabeceras(await usuario_real("coach"))
    r = await app_http.get(HOY, headers=h)
    assert r.status_code == 200 and r.json() is None
    assert r.headers["cache-control"] == "no-store"


async def test_trae_el_wod_de_hoy_con_movimientos(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    mov = await make_movement(session, admin.id)
    hoy = reloj.today_bogota()
    await make_wod(session, admin.id, [mov.id], date=hoy, title="Fran")
    await make_wod(session, admin.id, [mov.id], date=hoy + timedelta(days=1), title="Mañana")
    r = await app_http.get(HOY, headers=cabeceras(admin))
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["title"] == "Fran" and cuerpo["date"] == hoy.isoformat()
    assert [m["movement_name"] for m in cuerpo["movements"]] == ["Thruster"]


async def test_frozen_clock_01_00_utc_es_el_dia_anterior_de_bogota(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    """01:00Z del 22 es las 20:00 del 21 en Bogotá: el WOD de hoy es el del 21 (US-174 CA3)."""
    reloj.set(datetime(2026, 10, 22, 1, 0, tzinfo=UTC))
    admin = await usuario_real("admin")
    mov = await make_movement(session, admin.id)
    await make_wod(session, admin.id, [mov.id], date="2026-10-21", title="Ayer UTC")
    await make_wod(session, admin.id, [mov.id], date="2026-10-22", title="Hoy UTC")
    r = await app_http.get(HOY, headers=cabeceras(admin))
    assert r.json()["title"] == "Ayer UTC"


async def test_socio_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, reloj: FrozenClock
) -> None:
    h = cabeceras(await usuario_real("member"))
    assert (await app_http.get(HOY, headers=h)).status_code == 403
    assert (await app_http.get(HOY)).status_code == 401


pytestmark = pytest.mark.usefixtures("reloj")
