"""`leaderboard` del service y de la ruta (S8-B4, US-171, S8-D13, Q22, L-6). Base real."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.pagination import PageParams
from app.modules.members import service as members_service
from app.modules.members.models import Member
from app.modules.results import reads, service
from app.modules.results.exceptions import LeaderboardTooLarge
from app.modules.results.models import WodResult
from app.modules.wods.exceptions import WodNotFound
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_members
from tests.factories.results import make_result
from tests.factories.users import make_user
from tests.factories.wods import make_movement, make_wod

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

CAMPOS = {
    "position",
    "result_id",
    "member_id",
    "first_name",
    "last_initial",
    "level",
    "seconds",
    "rounds",
    "reps",
    "load_g",
    "capped",
}


async def _wod(session: AsyncSession, **cambios: Any) -> tuple[UUID, UUID]:
    coach = await make_user(session, role="coach")
    mov = await make_movement(session, coach.id, name=f"Mov {uuid4().hex[:6]}", unit="kg")
    datos: dict[str, Any] = {"date": "2026-10-21", "score_type": "time", "time_cap_s": 600}
    datos.update(cambios)
    wod = await make_wod(session, coach.id, [mov.id], **datos)
    return coach.id, wod.id


async def _socios(session: AsyncSession, sexos: list[str | None]) -> list[Member]:
    socios = await make_members(session, len(sexos))
    for socio, sexo in zip(socios, sexos, strict=True):
        await session.execute(update(Member).where(Member.id == socio.id).values(sex=sexo))
    await session.flush()
    return socios


async def test_q22_nulo_y_x_solo_en_todos(session: AsyncSession) -> None:
    coach, wod = await _wod(session)
    ella, el, nulo, equis = await _socios(session, ["f", "m", None, "x"])
    for n, socio in enumerate((ella, el, nulo, equis)):
        await make_result(session, coach, wod, socio.id, seconds=200 + n)
    todos = await service.leaderboard(session, wod, PageParams())
    assert todos.total == 4
    mujeres = await service.leaderboard(session, wod, PageParams(), sex="f")
    hombres = await service.leaderboard(session, wod, PageParams(), sex="m")
    assert [f.member_id for f in mujeres.items] == [ella.id]
    assert [f.member_id for f in hombres.items] == [el.id]
    # Las posiciones se calculan sobre el conjunto filtrado.
    assert [f.position for f in hombres.items] == [1]


async def test_filtro_level(session: AsyncSession) -> None:
    coach, wod = await _wod(session)
    a, b, c = await _socios(session, ["f", "f", "m"])
    await make_result(session, coach, wod, a.id, level="rx", seconds=300)
    await make_result(session, coach, wod, b.id, level="scaled", seconds=250)
    await make_result(session, coach, wod, c.id, level="rx_plus", seconds=280)
    escalado = await service.leaderboard(session, wod, PageParams(), level="scaled")
    assert [f.member_id for f in escalado.items] == [b.id] and escalado.items[0].position == 1
    todos = await service.leaderboard(session, wod, PageParams())
    assert [f.member_id for f in todos.items] == [c.id, a.id, b.id]
    assert [f.position for f in todos.items] == [1, 2, 3]


async def test_solo_vigentes_y_validados(session: AsyncSession) -> None:
    coach, wod = await _wod(session)
    a, b = await _socios(session, ["f", "m"])
    primero = await make_result(session, coach, wod, a.id, seconds=300)
    await make_result(session, coach, wod, a.id, seconds=250, supersedes_id=primero.id)
    # Un resultado `pending` (lo enviará el socio desde EP-25) nace sin validación y no cuenta.
    with actor_scope(coach):
        session.add(
            WodResult(
                wod_id=wod,
                member_id=b.id,
                wod_date=primero.wod_date,
                level="rx",
                seconds=100,
                status="pending",
                recorded_by=coach,
                source="desk",
            )
        )
        await session.flush()
    salida = await service.leaderboard(session, wod, PageParams())
    assert [(f.member_id, f.seconds) for f in salida.items] == [(a.id, 250)]


async def test_mas_de_1000_da_422_leaderboard_too_large(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    coach, wod = await _wod(session)
    socios = await _socios(session, [None, None, None])
    for n, socio in enumerate(socios):
        await make_result(session, coach, wod, socio.id, seconds=100 + n)
    monkeypatch.setattr(reads, "LEADERBOARD_MAX_ROWS", 2)
    with pytest.raises(LeaderboardTooLarge) as caso:
        await service.leaderboard(session, wod, PageParams())
    assert caso.value.status == 422 and caso.value.code == "leaderboard_too_large"
    monkeypatch.setattr(reads, "LEADERBOARD_MAX_ROWS", 3)
    assert (await service.leaderboard(session, wod, PageParams())).total == 3


async def test_tope_por_defecto_es_mil() -> None:
    assert reads.LEADERBOARD_MAX_ROWS == 1_000


async def test_names_for_una_llamada(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    coach, wod = await _wod(session)
    for n, socio in enumerate(await _socios(session, ["f", "m", None])):
        await make_result(session, coach, wod, socio.id, seconds=100 + n)
    llamadas: list[int] = []
    original = members_service.names_for

    async def espia(sesion: AsyncSession, ids: Any) -> Any:
        lista = list(ids)
        llamadas.append(len(lista))
        return await original(sesion, lista)

    monkeypatch.setattr(members_service, "names_for", espia)
    await service.leaderboard(session, wod, PageParams())
    assert llamadas == [3]


async def test_posiciones_de_competencia_y_pagina_sobre_el_conjunto(
    session: AsyncSession,
) -> None:
    coach, wod = await _wod(session)
    socios = await _socios(session, [None, None, None, None])
    for socio, seg in zip(socios, (200, 210, 210, 230), strict=True):
        await make_result(session, coach, wod, socio.id, seconds=seg)
    segunda = await service.leaderboard(session, wod, PageParams(limit=2, offset=2))
    assert (segunda.total, segunda.limit, segunda.offset) == (4, 2, 2)
    assert [f.position for f in segunda.items] == [2, 4]


async def test_wod_sin_resultados_y_wod_inexistente(session: AsyncSession) -> None:
    _coach, wod = await _wod(session)
    vacio = await service.leaderboard(session, wod, PageParams())
    assert vacio.items == [] and vacio.total == 0
    with pytest.raises(WodNotFound):
        await service.leaderboard(session, uuid4(), PageParams())


async def test_wod_sin_puntaje_da_lista_vacia(session: AsyncSession) -> None:
    _coach, wod = await _wod(session, score_type="none", time_cap_s=None)
    assert (await service.leaderboard(session, wod, PageParams())).items == []


async def test_sin_cifrados(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach, wod = await _wod(session)
    (socio,) = await _socios(session, ["f"])
    await make_result(session, coach, wod, socio.id, seconds=222)
    admin = await usuario_real("admin")
    r = await app_http.get(f"/api/v1/wods/{wod}/leaderboard", headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.json()
    assert set(cuerpo) == {"items", "total", "limit", "offset"}
    fila = cuerpo["items"][0]
    assert set(fila) == CAMPOS
    assert fila["last_initial"] == socio.last_name[0].upper() and fila["seconds"] == 222
    for prohibido in ("document", "phone", "email", "birth_date", "emergency_contact", "last_name"):
        assert prohibido not in r.text


async def test_enum_invalido_422_con_field(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    _coach, wod = await _wod(session)
    admin = await usuario_real("admin")
    for consulta, campo in (("level=ultra", "level"), ("sex=x", "sex"), ("sex=z", "sex")):
        r = await app_http.get(
            f"/api/v1/wods/{wod}/leaderboard?{consulta}", headers=cabeceras(admin)
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["field"] == campo


async def test_member_recibe_403_y_wod_inexistente_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    admin = await usuario_real("admin")
    r = await app_http.get(f"/api/v1/wods/{uuid4()}/leaderboard", headers=cabeceras(socio))
    assert r.status_code == 403
    r = await app_http.get(f"/api/v1/wods/{uuid4()}/leaderboard", headers=cabeceras(admin))
    assert r.status_code == 404 and r.json()["error"]["code"] == "wod_not_found"
