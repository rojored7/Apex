"""`GET /members/{id}/results` (S8-B4, US-173). Base real."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.pagination import PageParams
from app.modules.members.exceptions import MemberNotFound
from app.modules.members.models import Member
from app.modules.results import service
from app.modules.results.models import WodResult
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_members
from tests.factories.results import make_result
from tests.factories.users import make_user
from tests.factories.wods import make_movement, make_wod

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def _wod(session: AsyncSession, coach: UUID, fecha: str, titulo: str, **cambios: Any) -> UUID:
    mov = await make_movement(session, coach, name=f"Mov {uuid4().hex[:6]}", unit="kg")
    datos: dict[str, Any] = {
        "date": fecha,
        "title": titulo,
        "score_type": "time",
        "time_cap_s": 600,
    }
    datos.update(cambios)
    return (await make_wod(session, coach, [mov.id], **datos)).id


async def test_orden_wod_date_desc(session: AsyncSession) -> None:
    coach = (await make_user(session, role="coach")).id
    (socio,) = await make_members(session, 1)
    viejo = await _wod(session, coach, "2026-10-01", "Viejo")
    medio = await _wod(session, coach, "2026-10-10", "Medio")
    nuevo = await _wod(session, coach, "2026-10-21", "Nuevo")
    for wod in (medio, nuevo, viejo):
        await make_result(session, coach, wod, socio.id, seconds=300)
    salida = await service.list_member_results(session, socio.id, PageParams())
    assert [f.wod_title for f in salida.items] == ["Nuevo", "Medio", "Viejo"]
    assert salida.items[0].wod_date == date(2026, 10, 21) and salida.total == 3


async def test_solo_vigentes_y_pagina(session: AsyncSession) -> None:
    coach = (await make_user(session, role="coach")).id
    (socio,) = await make_members(session, 1)
    wod = await _wod(session, coach, "2026-10-21", "Fran")
    primero = await make_result(session, coach, wod, socio.id, seconds=300)
    await make_result(session, coach, wod, socio.id, seconds=250, supersedes_id=primero.id)
    otro = await _wod(session, coach, "2026-10-20", "Cindy")
    await make_result(session, coach, otro, socio.id, seconds=100)
    todo = await service.list_member_results(session, socio.id, PageParams())
    assert todo.total == 2 and {f.seconds for f in todo.items} == {250, 100}
    pagina = await service.list_member_results(session, socio.id, PageParams(limit=1, offset=1))
    assert (pagina.total, len(pagina.items), pagina.limit, pagina.offset) == (2, 1, 1, 1)


async def test_filtro_benchmark(session: AsyncSession) -> None:
    coach = (await make_user(session, role="coach")).id
    (socio,) = await make_members(session, 1)
    from tests.factories.wods import make_benchmark

    bench = await make_benchmark(session, coach, name=f"Fran {uuid4().hex[:5]}", score_type="time")
    con = await _wod(session, coach, "2026-10-21", "Con", benchmark_id=str(bench.id))
    sin = await _wod(session, coach, "2026-10-20", "Sin")
    for wod in (con, sin):
        await make_result(session, coach, wod, socio.id, seconds=300)
    solo = await service.list_member_results(session, socio.id, PageParams(), benchmark=True)
    assert [f.wod_title for f in solo.items] == ["Con"] and solo.items[0].is_benchmark
    assert solo.items[0].benchmark_id == bench.id
    todos = await service.list_member_results(session, socio.id, PageParams(), benchmark=False)
    assert todos.total == 2


async def test_baja_visible(session: AsyncSession, reloj: FrozenClock) -> None:
    coach = (await make_user(session, role="coach")).id
    (socio,) = await make_members(session, 1)
    wod = await _wod(session, coach, "2026-10-21", "Fran")
    await make_result(session, coach, wod, socio.id, seconds=300)
    await session.execute(
        update(Member).where(Member.id == socio.id).values(deleted_at=reloj.now_utc())
    )
    await session.flush()
    assert (await service.list_member_results(session, socio.id, PageParams())).total == 1


async def test_404_inexistente(session: AsyncSession) -> None:
    with pytest.raises(MemberNotFound):
        await service.list_member_results(session, uuid4(), PageParams())


async def test_pending_como_por_validar(session: AsyncSession) -> None:
    coach = (await make_user(session, role="coach")).id
    (socio,) = await make_members(session, 1)
    wod = await _wod(session, coach, "2026-10-21", "Fran")
    with actor_scope(coach):
        session.add(
            WodResult(
                wod_id=wod,
                member_id=socio.id,
                wod_date=date(2026, 10, 21),
                level="rx",
                seconds=100,
                status="pending",
                recorded_by=coach,
                source="desk",
            )
        )
        await session.flush()
    salida = await service.list_member_results(session, socio.id, PageParams())
    assert [f.status for f in salida.items] == ["pending"]


async def test_ruta_contrato_y_roles(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = (await make_user(session, role="coach")).id
    (socio,) = await make_members(session, 1)
    wod = await _wod(session, coach, "2026-10-21", "Fran")
    await make_result(session, coach, wod, socio.id, seconds=300)
    admin = await usuario_real("admin")
    miembro = await usuario_real("member")
    r = await app_http.get(f"/api/v1/members/{socio.id}/results", headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    fila = r.json()["items"][0]
    assert set(fila) == {
        "id", "wod_id", "wod_date", "wod_title", "score_type", "benchmark_id", "is_benchmark",
        "level", "seconds", "rounds", "reps", "load_g", "capped", "status", "source",
        "session_id", "created_at",
    }  # fmt: skip
    r = await app_http.get(f"/api/v1/members/{socio.id}/results", headers=cabeceras(miembro))
    assert r.status_code == 403
    r = await app_http.get(f"/api/v1/members/{uuid4()}/results", headers=cabeceras(admin))
    assert r.status_code == 404 and r.json()["error"]["code"] == "member_not_found"
