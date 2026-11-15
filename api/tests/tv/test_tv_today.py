"""`tv.service.today` y `results.service.public_leaderboard` (S8-C2, S8-D18, S8-D34, M-4)."""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.members.models import Member
from app.modules.results import reads
from app.modules.results import service as results_service
from app.modules.results.models import WodResult
from app.modules.results.schemas import VoidIn
from app.modules.tv import service
from tests.factories.members import make_members
from tests.factories.results import make_result
from tests.factories.users import make_user
from tests.tv._apoyo import (
    CONSENTIDO,
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
    assert salida.show_leaderboard is False


async def test_show_leaderboard_true_viaja_en_el_tablero(session: AsyncSession) -> None:
    await tablero(session, 2)
    salida = await service.today(session, config(show_leaderboard=True))
    assert salida.show_leaderboard is True and len(salida.leaderboard) == 2


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


async def _vigente(session: AsyncSession, wod_id: UUID, socio: Member) -> UUID:
    consulta = select(WodResult.id).where(
        WodResult.wod_id == wod_id, WodResult.member_id == socio.id, WodResult.is_current
    )
    return (await session.scalars(consulta)).one()


async def test_excluye_pendientes_anulados_y_superados(session: AsyncSession) -> None:
    """Solo el resultado vigente y validado de cada socio llega a la TV (S8-D34)."""
    datos = await tablero(session, 4)
    coach, wod_id = datos.coach, datos.wod_id
    a, b = datos.socios[0], datos.socios[1]
    (e,) = await make_members(session, 1, data_consent_at=CONSENTIDO)
    # `a` corrige su marca (200 -> 150): la anterior queda superada y no cuenta.
    await make_result(
        session, coach, wod_id, a.id, seconds=150, supersedes_id=await _vigente(session, wod_id, a)
    )
    # `b` queda anulado.
    vigente_b = await _vigente(session, wod_id, b)
    with actor_scope(coach):
        await results_service.void_result(session, vigente_b, VoidIn(reason="error"), by=coach)
        # `e` solo tiene un resultado pendiente (nace sin validar) y sería el primero si contara.
        session.add(
            WodResult(
                wod_id=wod_id,
                member_id=e.id,
                wod_date=date(2026, 10, 21),
                level="rx",
                seconds=100,
                status="pending",
                recorded_by=coach,
                source="desk",
            )
        )
        await session.commit()
    salida = await service.today(session, config())
    assert [f.score.seconds for f in salida.leaderboard] == [150, 202, 203]
    assert [f.position for f in salida.leaderboard] == [1, 2, 3]


async def test_ranking_demasiado_grande_deja_el_tablero_sin_ranking(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """L-1: si el WOD supera el tope del ranking, la TV muestra el WOD con la lista vacía."""
    await tablero(session, 3)
    monkeypatch.setattr(reads, "LEADERBOARD_MAX_ROWS", 2)
    with caplog.at_level(logging.WARNING):
        salida = await service.today(session, config())
    assert salida.wod is not None and salida.wod.title == "Fran"
    assert salida.leaderboard == []
    assert any("ranking" in r.getMessage().lower() for r in caplog.records)
