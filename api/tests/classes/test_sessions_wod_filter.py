"""Filtro `wod_id` y campos de WOD de `GET /class-sessions` (S8-A4, S8-D9)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import make_session
from tests.factories.wods import make_movement, make_wod

SESIONES = "/api/v1/class-sessions"
JUEVES = datetime(2026, 10, 22, 11, 0, tzinfo=UTC)
JUEVES_TARDE = datetime(2026, 10, 22, 23, 0, tzinfo=UTC)
VIERNES = datetime(2026, 10, 23, 11, 0, tzinfo=UTC)

pytestmark = pytest.mark.usefixtures("reloj")


async def _wod(session: AsyncSession, actor: UUID, fecha: str, titulo: str) -> UUID:
    mov = await make_movement(session, actor, name=f"Mov {titulo}")
    return (await make_wod(session, actor, [mov.id], date=fecha, title=titulo)).id


async def _ids(app_http: AsyncClient, h: dict[str, str], **params: str) -> set[str]:
    r = await app_http.get(SESIONES, params={"week": "2026-W43", **params}, headers=h)
    assert r.status_code == 200, r.text
    return {i["id"] for i in r.json()["items"]}


async def test_semantica_efectiva(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    fran = await _wod(session, admin.id, "2026-10-22", "Fran")
    cindy = await _wod(session, admin.id, "2026-10-23", "Cindy")
    hereda = await make_session(session, starts_at=JUEVES)  # del 22, sin WOD: hereda Fran
    tarde = await make_session(session, starts_at=JUEVES_TARDE)  # también del 22
    con_cindy = await make_session(session, starts_at=JUEVES_TARDE, wod_id=cindy)  # asignado
    del_viernes = await make_session(session, starts_at=VIERNES)  # hereda Cindy
    assert await _ids(app_http, h, wod_id=str(fran)) == {str(hereda.id), str(tarde.id)}
    assert await _ids(app_http, h, wod_id=str(cindy)) == {str(con_cindy.id), str(del_viernes.id)}
    lista = (await app_http.get(SESIONES, params={"week": "2026-W43"}, headers=h)).json()["items"]
    por_id = {i["id"]: i for i in lista}
    assert por_id[str(hereda.id)]["wod_id"] is None
    assert por_id[str(hereda.id)]["effective_wod_id"] == str(fran)
    assert por_id[str(con_cindy.id)]["wod_id"] == str(cindy)
    assert por_id[str(con_cindy.id)]["effective_wod_id"] == str(cindy)


async def test_wod_inexistente_pagina_vacia(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    await make_session(session, starts_at=JUEVES)
    h = cabeceras(await usuario_real("coach"))
    r = await app_http.get(SESIONES, params={"week": "2026-W43", "wod_id": str(uuid4())}, headers=h)
    assert r.status_code == 200 and r.json()["items"] == [] and r.json()["total"] == 0


async def test_day_wod_ids_una_llamada_por_pagina(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    """Cinco sesiones de dos días: UNA consulta a `wods.wods` por página, no una por fila."""
    admin = await usuario_real("admin")
    await _wod(session, admin.id, "2026-10-22", "Fran")
    for inicio in (JUEVES, JUEVES_TARDE, JUEVES, VIERNES, VIERNES):
        await make_session(session, starts_at=inicio)
    vistas: list[str] = []
    motor = session.get_bind()

    def anotar(_c: object, _cur: object, sentencia: str, *_: object) -> None:
        vistas.append(sentencia)

    event.listen(motor, "before_cursor_execute", anotar)
    try:
        r = await app_http.get(SESIONES, params={"week": "2026-W43"}, headers=cabeceras(admin))
    finally:
        event.remove(motor, "before_cursor_execute", anotar)
    assert r.status_code == 200 and len(r.json()["items"]) == 5
    assert sum("FROM wods.wods" in s for s in vistas) == 1
