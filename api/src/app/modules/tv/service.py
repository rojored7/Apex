"""Service de la TV (S8-C2): valida el token y compone el tablero del día."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.modules.results import service as results_service
from app.modules.settings import service as settings_service
from app.modules.settings.schemas import TvConfig
from app.modules.tv import rules
from app.modules.tv.schemas import TvBoard
from app.modules.wods import service as wods_service

TV_MAX_ROWS = 50


async def authenticate(session: AsyncSession, token: str | None) -> TvConfig | None:
    """`TvConfig` si `token` es el vigente; `None` en cualquier otro caso (L-1)."""
    return await settings_service.verify_tv_token(session, token)


async def today(session: AsyncSession, config: TvConfig) -> TvBoard:
    """El WOD de hoy (Bogotá) y, si la sección lo permite, su ranking público (tope 50)."""
    day = current_clock().today_bogota()
    wod = await wods_service.today_card(session, day)
    filas = []
    if wod is not None and config.show_leaderboard:
        filas = await results_service.public_leaderboard(session, wod.id, TV_MAX_ROWS)
    return rules.to_public_board(day, config, wod, filas)


__all__ = ["TV_MAX_ROWS", "authenticate", "today"]
