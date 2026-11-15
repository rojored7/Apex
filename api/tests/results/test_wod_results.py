"""`GET /wods/{id}/results` (S8-B4, US-172). Base real."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.modules.auth import service as auth_service
from app.modules.results import service
from app.modules.wods.exceptions import WodNotFound
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_members
from tests.factories.results import make_result
from tests.factories.users import make_user
from tests.factories.wods import make_movement, make_wod

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

CAMPOS = {
    "id",
    "member_id",
    "first_name",
    "last_name",
    "level",
    "seconds",
    "rounds",
    "reps",
    "load_g",
    "capped",
    "status",
    "source",
    "is_current",
    "supersedes_id",
    "session_id",
    "recorded_by",
    "recorded_by_name",
    "created_at",
}


async def _wod(session: AsyncSession) -> tuple[UUID, UUID]:
    coach = await make_user(session, role="coach")
    mov = await make_movement(session, coach.id, name=f"Mov {uuid4().hex[:6]}", unit="kg")
    wod = await make_wod(
        session, coach.id, [mov.id], date="2026-10-21", score_type="time", time_cap_s=600
    )
    return coach.id, wod.id


async def test_include_superseded(session: AsyncSession) -> None:
    coach, wod = await _wod(session)
    a, b = await make_members(session, 2)
    primero = await make_result(session, coach, wod, a.id, seconds=300)
    nuevo = await make_result(session, coach, wod, a.id, seconds=250, supersedes_id=primero.id)
    await make_result(session, coach, wod, b.id, seconds=280)
    vigentes = await service.list_wod_results(session, wod, PageParams())
    assert vigentes.total == 2 and all(f.is_current for f in vigentes.items)
    todos = await service.list_wod_results(session, wod, PageParams(), include_superseded=True)
    assert todos.total == 3
    por_id = {f.id: f for f in todos.items}
    assert por_id[primero.id].is_current is False
    assert por_id[nuevo.id].supersedes_id == primero.id and por_id[nuevo.id].is_current


async def test_registro_con_user_names_for(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    coach, wod = await _wod(session)
    socios = await make_members(session, 2)
    for n, socio in enumerate(socios):
        await make_result(session, coach, wod, socio.id, seconds=200 + n)
    llamadas: list[int] = []
    original = auth_service.user_names_for

    async def espia(sesion: AsyncSession, ids: Any) -> Any:
        lista = list(ids)
        llamadas.append(len(lista))
        return await original(sesion, lista)

    monkeypatch.setattr(auth_service, "user_names_for", espia)
    salida = await service.list_wod_results(session, wod, PageParams())
    assert llamadas == [1]  # los dos los registró el mismo coach
    assert {f.recorded_by for f in salida.items} == {coach}
    assert all(f.recorded_by_name for f in salida.items)
    assert {f.first_name for f in salida.items} == {s.first_name for s in socios}


async def test_source_visible_y_utc(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach, wod = await _wod(session)
    (socio,) = await make_members(session, 1)
    await make_result(session, coach, wod, socio.id, seconds=210)
    admin = await usuario_real("admin")
    r = await app_http.get(f"/api/v1/wods/{wod}/results", headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    fila = r.json()["items"][0]
    assert set(fila) == CAMPOS and fila["source"] == "desk"
    assert fila["created_at"].endswith(("Z", "+00:00"))
    for prohibido in ("document", "phone", "birth_date", "emergency_contact"):
        assert prohibido not in r.text


async def test_404_422_y_403(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    _coach, wod = await _wod(session)
    admin = await usuario_real("admin")
    socio = await usuario_real("member")
    assert (
        await app_http.get(f"/api/v1/wods/{uuid4()}/results", headers=cabeceras(admin))
    ).status_code == 404
    r = await app_http.get(f"/api/v1/wods/{wod}/results?limit=500", headers=cabeceras(admin))
    assert r.status_code == 422 and r.json()["error"]["field"] == "limit"
    r = await app_http.get(f"/api/v1/wods/{wod}/results", headers=cabeceras(socio))
    assert r.status_code == 403
    with pytest.raises(WodNotFound):
        await service.list_wod_results(session, uuid4(), PageParams())
