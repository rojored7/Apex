"""`DELETE /attendance/{id}` por HTTP (S7-C3, US-161; S7-D13, E4, S7-D27 b).

Admin y coach; el socio recibe 403 y sin token 401. Cuerpo JSON opcional `{reason}`: con y sin
cuerpo responde 204. 404 `attendance_not_found`, 403 `attendance_locked` para el coach fuera de
hoy y ayer, 422 con campos de más o motivo vacío o de más de 200, cubeta `attendance-write`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.classes.router import router
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import FakeMembershipPort, make_session
from tests.factories.members import make_members

BASE = "/api/v1/attendance"
HOY = datetime(2026, 10, 21, 15, 10, tzinfo=UTC)
ANTEAYER = datetime(2026, 10, 19, 15, 10, tzinfo=UTC)
TOPE_ESCRITURAS = 60

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def _registrar(
    app_http: AsyncClient, headers: dict[str, str], session_id: UUID, member_id: UUID
) -> str:
    r = await app_http.post(
        BASE, json={"session_id": str(session_id), "member_id": str(member_id)}, headers=headers
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def test_el_router_publica_el_delete() -> None:
    publicadas = {
        (metodo, ruta.path)
        for ruta in router.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
    }
    assert ("DELETE", "/attendance/{attendance_id}") in publicadas


@pytest.mark.parametrize("cuerpo", [None, {}, {"reason": "Lo registré por error"}])
@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_con_y_sin_cuerpo(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
    rol: str,
    cuerpo: dict[str, Any] | None,
) -> None:
    usuario = await usuario_real(rol)
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=HOY)
    h = cabeceras(usuario)
    asistencia = await _registrar(app_http, h, sesion.id, socio.id)
    r = await app_http.request("DELETE", f"{BASE}/{asistencia}", json=cuerpo, headers=h)
    assert r.status_code == 204, r.text
    assert r.content == b"" and r.headers["cache-control"] == "no-store"
    fila = (
        await session.execute(
            text("SELECT removed_at, removed_reason FROM classes.attendance WHERE id = :i"),
            {"i": asistencia},
        )
    ).one()
    assert fila.removed_at is not None
    esperado = None if not cuerpo else cuerpo["reason"]
    assert fila.removed_reason == esperado


async def test_socio_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    url = f"{BASE}/{uuid4()}"
    assert (await app_http.delete(url, headers=cabeceras(socio))).status_code == 403
    assert (await app_http.delete(url)).status_code == 401


async def test_404_inexistente_y_al_quitar_dos_veces(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
) -> None:
    coach = await usuario_real("coach")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=HOY)
    h = cabeceras(coach)
    sesion_id, socio_id = sesion.id, socio.id  # la petición expira los objetos
    r = await app_http.delete(f"{BASE}/{uuid4()}", headers=h)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "attendance_not_found")
    asistencia = await _registrar(app_http, h, sesion_id, socio_id)
    assert (await app_http.delete(f"{BASE}/{asistencia}", headers=h)).status_code == 204
    r = await app_http.delete(f"{BASE}/{asistencia}", headers=h)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "attendance_not_found")


async def test_coach_403_attendance_locked_y_admin_204(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
) -> None:
    coach = await usuario_real("coach")
    admin = await usuario_real("admin")
    (socio,) = await make_members(session, 1)
    sesion = await make_session(session, starts_at=ANTEAYER)
    asistencia = await _registrar(app_http, cabeceras(admin), sesion.id, socio.id)
    r = await app_http.delete(f"{BASE}/{asistencia}", headers=cabeceras(coach))
    assert (r.status_code, r.json()["error"]["code"]) == (403, "attendance_locked")
    assert (
        await app_http.delete(f"{BASE}/{asistencia}", headers=cabeceras(admin))
    ).status_code == (204)


@pytest.mark.parametrize(
    "cuerpo",
    [{"reason": ""}, {"reason": "x" * 201}, {"reason": "   "}, {"otro": 1}, {"removed_by": "x"}],
)
async def test_422_con_motivo_invalido_o_campos_de_mas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    cuerpo: dict[str, Any],
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.request("DELETE", f"{BASE}/{uuid4()}", json=cuerpo, headers=cabeceras(coach))
    assert r.status_code == 422


async def test_422_con_id_que_no_es_uuid(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    assert (
        await app_http.delete(f"{BASE}/no-es-uuid", headers=cabeceras(coach))
    ).status_code == 422


async def test_cubeta_attendance_write(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    h = cabeceras(coach)
    for _ in range(TOPE_ESCRITURAS):
        assert (await app_http.delete(f"{BASE}/{uuid4()}", headers=h)).status_code == 404
    assert (await app_http.delete(f"{BASE}/{uuid4()}", headers=h)).status_code == 429
