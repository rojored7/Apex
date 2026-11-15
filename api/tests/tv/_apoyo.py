"""Apoyo de las pruebas de `tv` (S8-C2): token vigente, WOD de hoy y resultados con socios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.members.models import Member
from app.modules.settings import service as settings_service
from app.modules.settings.schemas import TvConfig, TvEditable
from tests.conftest import T0
from tests.factories.members import make_members
from tests.factories.results import make_result
from tests.factories.users import make_user
from tests.factories.wods import make_movement, make_wod

API = "/api/v1"
URL = f"{API}/tv/today"
ORIGEN = "https://apex.ejemplo.co"
HOY = "2026-10-21"  # `reloj` (T0) = 21 de octubre de 2026, 10:00 de Bogotá
CONSENTIDO = T0 - timedelta(days=1)


async def emitir_token(session: AsyncSession, admin: UUID, **edicion: Any) -> str:
    """Regenera el token de la TV (y fija `refresh_seconds`/`show_leaderboard` si se piden)."""
    with actor_scope(admin):
        salida = await settings_service.regenerate_tv_token(session, admin, origin=ORIGEN)
        if edicion:
            valores = {"refresh_seconds": 30, "show_leaderboard": True, **edicion}
            await settings_service.update_tv(session, TvEditable(**valores), salida.version, admin)
        await session.commit()
    return salida.token


def config(**cambios: Any) -> TvConfig:
    valores: dict[str, Any] = {"refresh_seconds": 30, "show_leaderboard": True, **cambios}
    return TvConfig(**valores)


@dataclass
class Tablero:
    coach: UUID
    wod_id: UUID
    socios: list[Member]


async def wod_de_hoy(session: AsyncSession, **cambios: Any) -> tuple[UUID, UUID]:
    coach = await make_user(session, role="coach")
    uno = await make_movement(session, coach.id, name=f"Mov {uuid4().hex[:6]}", unit="kg")
    datos: dict[str, Any] = {"date": HOY, "title": "Fran", "score_type": "time", "time_cap_s": 600}
    datos.update(cambios)
    wod = await make_wod(session, coach.id, [uno.id], **datos)
    return coach.id, wod.id


async def tablero(
    session: AsyncSession, n: int, *, sexos: list[str | None] | None = None
) -> Tablero:
    """WOD de hoy con `n` socios autorizados y un resultado `rx` de `200 + i` segundos cada uno."""
    coach, wod_id = await wod_de_hoy(session)
    socios = await make_members(session, n, data_consent_at=CONSENTIDO)
    for i, socio in enumerate(socios):
        if sexos is not None:
            await session.execute(update(Member).where(Member.id == socio.id).values(sex=sexos[i]))
        await make_result(session, coach, wod_id, socio.id, seconds=200 + i)
    await session.commit()
    return Tablero(coach, wod_id, socios)


async def dar_de_baja(session: AsyncSession, socio: Member) -> None:
    await session.execute(update(Member).where(Member.id == socio.id).values(deleted_at=T0))
    await session.commit()


async def quitar_autorizacion(session: AsyncSession, socio: Member) -> None:
    await session.execute(update(Member).where(Member.id == socio.id).values(data_consent_at=None))
    await session.commit()
