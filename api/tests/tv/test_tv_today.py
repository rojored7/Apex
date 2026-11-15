"""`tv.service.today` y `results.service.public_leaderboard` (S8-C2, S8-D18, S8-D34, M-4)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.members.models import Member
from app.modules.tv import service
from tests.factories.users import make_user
from tests.tv._apoyo import (
    config,
    dar_de_baja,
    emitir_token,
    quitar_autorizacion,
    tablero,
    wod_de_hoy,
)

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def test_sin_wod_lista_vacia(session: AsyncSession) -> None:
    salida = await service.today(session, config())
    assert salida.wod is None and salida.leaderboard == []
    assert salida.date == date(2026, 10, 21) and salida.refresh_seconds == 30


async def test_show_leaderboard_false(session: AsyncSession) -> None:
    await tablero(session, 2)
    salida = await service.today(session, config(show_leaderboard=False))
    assert salida.wod is not None and salida.wod.title == "Fran"
    assert salida.leaderboard == []


async def test_wod_sin_resultados_trae_wod_y_lista_vacia(session: AsyncSession) -> None:
    await wod_de_hoy(session)
    salida = await service.today(session, config())
    assert salida.wod is not None and salida.leaderboard == []
    assert salida.wod.movements[0].reps == "21-15-9"


async def test_tope_50(session: AsyncSession) -> None:
    await tablero(session, 52)
    salida = await service.today(session, config())
    assert len(salida.leaderboard) == 50
    assert [f.position for f in salida.leaderboard] == list(range(1, 51))


async def test_todos_incluye_sexo_nulo_y_x(session: AsyncSession) -> None:
    await tablero(session, 4, sexos=["f", "m", None, "x"])
    salida = await service.today(session, config())
    assert len(salida.leaderboard) == 4


async def test_excluye_bajas(session: AsyncSession) -> None:
    datos = await tablero(session, 3)
    await dar_de_baja(session, datos.socios[1])
    salida = await service.today(session, config())
    assert len(salida.leaderboard) == 2


async def test_excluye_sin_autorizacion_vigente(session: AsyncSession) -> None:
    datos = await tablero(session, 3)
    await quitar_autorizacion(session, datos.socios[0])
    salida = await service.today(session, config())
    assert len(salida.leaderboard) == 2


async def test_posiciones_sin_huecos_tras_excluir(session: AsyncSession) -> None:
    """Hallazgo 11: el segundo real está dado de baja y la TV numera 1, 2, no 1, 3."""
    datos = await tablero(session, 3)
    for socio in datos.socios:
        await session.execute(
            update(Member)
            .where(Member.id == socio.id)
            .values(last_name=f"Apellido{socio.id.hex[:4]}")
        )
    await dar_de_baja(session, datos.socios[1])
    salida = await service.today(session, config())
    assert [f.position for f in salida.leaderboard] == [1, 2]
    assert [f.score.seconds for f in salida.leaderboard] == [200, 202]


async def test_refresh_seconds_de_la_seccion(session: AsyncSession) -> None:
    admin = await make_user(session, role="admin")
    token = await emitir_token(session, admin.id, refresh_seconds=45, show_leaderboard=True)
    cfg = await service.authenticate(session, token)
    assert cfg is not None and cfg.refresh_seconds == 45
    assert (await service.today(session, cfg)).refresh_seconds == 45


async def test_authenticate_solo_acepta_el_vigente(session: AsyncSession) -> None:
    admin = await make_user(session, role="admin")
    token = await emitir_token(session, admin.id)
    assert await service.authenticate(session, token) is not None
    assert await service.authenticate(session, "inventado") is None
    assert await service.authenticate(session, None) is None
    assert await service.authenticate(session, "") is None
