"""`GET /class-sessions/{id}/attendance` (S8-B3, US-169 CA1; S8-D14). Base real."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.pagination import PageParams
from app.modules.classes.exceptions import SessionNotFound
from app.modules.results import service
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import make_attendance, make_session
from tests.factories.members import make_members
from tests.results._apoyo import Escena, escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

CAMPOS_FILA = {"member_id", "first_name", "last_name", "has_result", "result"}
SEGUNDO_ASISTENTE_A = datetime(2026, 10, 21, 15, 5, tzinfo=UTC)


async def _con_asistente_extra(session: AsyncSession, e: Escena, cuantos: int = 1) -> list[Any]:
    assert e.clase is not None
    otros = (await make_members(session, cuantos + 1))[1:]
    for otro in otros:
        await make_attendance(session, e.clase, otro.id, checked_in_at=SEGUNDO_ASISTENTE_A)
    return list(otros)


async def test_has_result_y_result_vigente(session: AsyncSession) -> None:
    e = await escena(session)
    (otro,) = await _con_asistente_extra(session, e)
    uno = await registrar(session, e, seconds=300)
    nuevo = await registrar(session, e, seconds=280, supersedes_id=uno.id)
    assert e.clase_id is not None
    with actor_scope(e.coach):
        salida = await service.session_attendance(session, e.clase_id, PageParams())
    filas = {f.member_id: f for f in salida.items}
    assert salida.total == 2 and len(salida.items) == 2
    con = filas[e.socio_id]
    assert con.has_result is True and con.result is not None and con.result.id == nuevo.id
    sin = filas[otro.id]
    assert sin.has_result is False and sin.result is None


async def test_wod_efectivo(session: AsyncSession) -> None:
    e = await escena(session)
    assert e.clase_id is not None
    salida = await service.session_attendance(session, e.clase_id, PageParams())
    assert salida.session.id == e.clase_id
    assert salida.wod is not None and salida.wod.id == e.wod_id
    vacia = await make_session(session, starts_at=datetime(2026, 10, 20, 11, 0, tzinfo=UTC))

    otra = await service.session_attendance(session, vacia.id, PageParams())
    assert otra.wod is None and all(f.result is None for f in otra.items)


async def test_sesion_inexistente_404(session: AsyncSession) -> None:
    with pytest.raises(SessionNotFound):
        await service.session_attendance(session, uuid4(), PageParams())


async def test_sin_campos_cifrados(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena(session)
    await registrar(session, e)
    admin = await usuario_real("admin")
    assert e.clase_id is not None
    r = await app_http.get(
        f"/api/v1/class-sessions/{e.clase_id}/attendance", headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.json()
    assert set(cuerpo) == {"session", "wod", "items", "total", "limit", "offset"}
    assert {set(f) == CAMPOS_FILA for f in cuerpo["items"]} == {True}
    texto = r.text
    for prohibido in ("document", "phone", "email", "birth_date", "emergency_contact"):
        assert prohibido not in texto


async def test_pagina_con_page_params(session: AsyncSession) -> None:
    e = await escena(session)
    await _con_asistente_extra(session, e, cuantos=2)
    assert e.clase_id is not None
    primera = await service.session_attendance(session, e.clase_id, _pagina(limit=2, offset=0))
    segunda = await service.session_attendance(session, e.clase_id, _pagina(limit=2, offset=2))
    assert (primera.total, primera.limit, primera.offset, len(primera.items)) == (3, 2, 0, 2)
    assert (segunda.total, segunda.offset, len(segunda.items)) == (3, 2, 1)
    ids = [f.member_id for f in primera.items + segunda.items]
    assert len(set(ids)) == 3


def _pagina(*, limit: int, offset: int) -> PageParams:
    return PageParams(limit=limit, offset=offset)
