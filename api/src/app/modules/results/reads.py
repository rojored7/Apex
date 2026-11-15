"""Lecturas de `results` (S8-B4, US-171 a US-173). Privado del módulo.

- `leaderboard` (S8-D13, Q22, L-6): los resultados vigentes y validados del WOD (con `level` en
  SQL), los nombres en UNA llamada a `members.service.names_for` (nunca un campo cifrado), el
  filtro de sexo (`f|m` excluye `NULL` y `x`; sin filtro entran todos), el orden y las posiciones
  de `leaderboard.py` sobre el conjunto filtrado y, al final, la página. Con más de
  `LEADERBOARD_MAX_ROWS` filas vigentes responde 422 `leaderboard_too_large`: un ranking nunca
  se trunca.
- `wod_results` (US-172): todos los resultados del WOD (por defecto solo vigentes), con el nombre
  del socio y de quien registró (`auth.service.user_names_for`, una llamada).
- `member_results` (US-173): los resultados vigentes del socio, del WOD más reciente al más
  antiguo (`wod_date` copiado, sin JOIN), con el título del WOD (`wods.service.titles_for`).
Todas leen sin candados ni escrituras.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, PageParams, paginate, to_page
from app.modules.auth import service as auth_service
from app.modules.members import service as members_service
from app.modules.members.schemas import MemberName
from app.modules.results.exceptions import LeaderboardTooLarge
from app.modules.results.leaderboard import Mark, rank_rows
from app.modules.results.models import WodResult
from app.modules.results.schemas import LeaderboardRow, MemberResultRow, PublicRow, WodResultRow
from app.modules.wods import service as wods_service
from app.modules.wods.exceptions import WodNotFound

LEADERBOARD_MAX_ROWS = 1_000


async def _score_type(session: AsyncSession, wod_id: UUID) -> str:
    titulos = await wods_service.titles_for(session, [wod_id])
    if wod_id not in titulos:
        raise WodNotFound()
    return titulos[wod_id].score_type


def _to_row(position: int, mark: Mark, last_initial: str, fila: WodResult) -> LeaderboardRow:
    return LeaderboardRow(
        position=position,
        result_id=fila.id,
        member_id=fila.member_id,
        first_name=mark.first_name,
        last_initial=last_initial,
        level=fila.level,
        seconds=fila.seconds,
        rounds=fila.rounds,
        reps=fila.reps,
        load_g=fila.load_g,
        capped=fila.capped,
    )


def _marks(
    filas: list[WodResult], nombres: dict[UUID, MemberName], sex: str | None
) -> tuple[dict[UUID, WodResult], list[Mark]]:
    """Las marcas con nombre del conjunto filtrado por sexo (Q22: `f|m` excluye `NULL` y `x`)."""
    por_resultado: dict[UUID, WodResult] = {}
    marcas: list[Mark] = []
    for fila in filas:
        nombre = nombres.get(fila.member_id)
        if nombre is None or (sex is not None and nombre.sex != sex):
            continue
        por_resultado[fila.id] = fila
        marcas.append(
            Mark(
                fila.id,
                fila.member_id,
                nombre.first_name,
                nombre.last_name,
                fila.level,
                fila.seconds,
                fila.rounds,
                fila.reps,
                fila.load_g,
                fila.capped,
            )
        )
    return por_resultado, marcas


async def leaderboard(
    session: AsyncSession,
    wod_id: UUID,
    page: PageParams,
    *,
    level: str | None = None,
    sex: str | None = None,
) -> Page[LeaderboardRow]:
    score_type = await _score_type(session, wod_id)
    if score_type == "none":
        return to_page([], 0, page)
    consulta = select(WodResult).where(
        WodResult.wod_id == wod_id,
        WodResult.is_current.is_(True),
        WodResult.status == "validated",
    )
    if level is not None:
        consulta = consulta.where(WodResult.level == level)
    filas = list(
        await session.scalars(consulta.order_by(WodResult.id).limit(LEADERBOARD_MAX_ROWS + 1))
    )
    if len(filas) > LEADERBOARD_MAX_ROWS:
        raise LeaderboardTooLarge()
    nombres = await members_service.names_for(session, [f.member_id for f in filas])
    por_resultado, marcas = _marks(filas, nombres, sex)
    ordenadas = rank_rows(score_type, marcas)
    pagina = ordenadas[page.offset : page.offset + page.limit]
    items = [
        _to_row(r.position, r.mark, r.mark.last_name[:1].upper(), por_resultado[r.mark.result_id])
        for r in pagina
    ]
    return to_page(items, len(ordenadas), page)


async def public_leaderboard(session: AsyncSession, wod_id: UUID, limit: int) -> list[PublicRow]:
    """Ranking «Todos» de la TV (S8-C2, S8-D34, M-4). Excluye primero las bajas y a quien no tiene
    autorización de datos vigente (`board_names`) y calcula las posiciones después. Sin `member_id`
    ni sexo en la salida; un WOD sin marca (`none`) no tiene ranking."""
    score_type = await _score_type(session, wod_id)
    if score_type == "none":
        return []
    consulta = select(WodResult).where(
        WodResult.wod_id == wod_id,
        WodResult.is_current.is_(True),
        WodResult.status == "validated",
    )
    filas = list(
        await session.scalars(consulta.order_by(WodResult.id).limit(LEADERBOARD_MAX_ROWS + 1))
    )
    if len(filas) > LEADERBOARD_MAX_ROWS:
        raise LeaderboardTooLarge()
    nombres = await members_service.board_names(session, [f.member_id for f in filas])
    por_resultado, marcas = _marks(filas, nombres, None)
    ordenadas = rank_rows(score_type, marcas)[: max(limit, 0)]
    return [
        PublicRow(
            position=r.position,
            first_name=r.mark.first_name,
            last_name=r.mark.last_name,
            level=por_resultado[r.mark.result_id].level,
            seconds=r.mark.seconds,
            rounds=r.mark.rounds,
            reps=r.mark.reps,
            load_g=r.mark.load_g,
            capped=r.mark.capped,
        )
        for r in ordenadas
    ]


async def wod_results(
    session: AsyncSession, wod_id: UUID, page: PageParams, *, include_superseded: bool = False
) -> Page[WodResultRow]:
    await _score_type(session, wod_id)
    consulta = select(WodResult).where(WodResult.wod_id == wod_id)
    if not include_superseded:
        consulta = consulta.where(WodResult.is_current.is_(True))
    filas, total = await paginate(
        session, consulta.order_by(WodResult.created_at.desc(), WodResult.id), page
    )
    nombres = await members_service.names_for(session, [f.member_id for f in filas])
    quienes = await auth_service.user_names_for(session, list({f.recorded_by for f in filas}))
    items = [
        WodResultRow(
            id=f.id,
            member_id=f.member_id,
            first_name=nombres[f.member_id].first_name if f.member_id in nombres else "",
            last_name=nombres[f.member_id].last_name if f.member_id in nombres else "",
            level=f.level,
            seconds=f.seconds,
            rounds=f.rounds,
            reps=f.reps,
            load_g=f.load_g,
            capped=f.capped,
            status=f.status,
            source=f.source,
            is_current=f.is_current,
            supersedes_id=f.supersedes_id,
            session_id=f.session_id,
            recorded_by=f.recorded_by,
            recorded_by_name=quienes.get(f.recorded_by),
            created_at=f.created_at,
        )
        for f in filas
    ]
    return to_page(items, total, page)


async def member_results(
    session: AsyncSession, member_id: UUID, page: PageParams, *, benchmark: bool | None = None
) -> Page[MemberResultRow]:
    await members_service.ensure_exists(session, member_id, include_deleted=True)
    consulta = select(WodResult).where(
        WodResult.member_id == member_id, WodResult.is_current.is_(True)
    )
    if benchmark:
        consulta = consulta.where(WodResult.benchmark_id.is_not(None))
    filas, total = await paginate(
        session,
        consulta.order_by(WodResult.wod_date.desc(), WodResult.created_at.desc(), WodResult.id),
        page,
    )
    titulos = await wods_service.titles_for(session, list({f.wod_id for f in filas}))
    items = [
        MemberResultRow(
            id=f.id,
            wod_id=f.wod_id,
            wod_date=f.wod_date,
            wod_title=titulos[f.wod_id].title if f.wod_id in titulos else "",
            score_type=titulos[f.wod_id].score_type if f.wod_id in titulos else "",
            benchmark_id=f.benchmark_id,
            is_benchmark=f.benchmark_id is not None,
            level=f.level,
            seconds=f.seconds,
            rounds=f.rounds,
            reps=f.reps,
            load_g=f.load_g,
            capped=f.capped,
            status=f.status,
            source=f.source,
            session_id=f.session_id,
            created_at=f.created_at,
        )
        for f in filas
    ]
    return to_page(items, total, page)
