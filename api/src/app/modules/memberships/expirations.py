"""Recálculo diario del estado guardado de las membresías (S4A-B2, US-094; S4A-D1, S4A-D2,
S4A-D57). Privado (D7): los demás módulos, el worker y el CLI lo ven por `memberships.service`.

La columna `status` es un espejo persistido del estado efectivo (S4A-D1): las lecturas siguen
derivadas (`compute_status` y `status_expr`); este recálculo alinea la columna para las filas que
el tiempo movió y es la única fuente de `MembershipExpiring` y `MembershipExpired`.

`recompute_statuses(session_factory, *, today, page_size=RECOMPUTE_PAGE)`:
1. `expiring_days` de `settings_service.memberships_policy`, una vez por corrida;
2. fase 1, lectura sin candados en una sesión propia que se cierra antes de la fase 2
   (`_candidate_member_ids`): los `member_id` distintos con alguna membresía guardada en
   `active`, `expiring` o `frozen` cuyo `status_expr(today, expiring_days)` difiere de lo
   guardado, `member_id > after`, orden por `member_id`, `LIMIT page_size` (paginación por llave);
3. fase 2, una transacción por socio (`_recompute_member` → `_apply_to_member`): `lock_member`,
   `sell.lock_membership` por cada candidata (relee con `populate_existing`), salto si ya no es
   candidata o ya coincide, `queries._load_freezes_for`, `compute_status`, asignación, **un solo
   `flush`** y `events.emit` según `rules.transition_event`. Orden socio → fila → cadena (D3);
4. ocupación (`BUSY_SQLSTATES` o `DatabaseBusy` de `lock_member`): hasta `MAX_BUSY_RETRIES`
   reintentos con `await asyncio.sleep(RETRY_DELAYS_S[i])` **fuera** de la transacción; si sigue
   ocupado cuenta en `busy_omitidos` y sigue con el siguiente socio. Cualquier otra excepción de
   un socio cuenta en `errores` (se registra solo el tipo) y el ciclo sigue.

Nada en este archivo se llama `on_*` y no hay `with_for_update` (la única puerta es
`sell.lock_membership`); lo vigilan `test_handlers_no_new_locks.py`, `test_guarded_calls.py` y
`test_expirations_lock_order.py`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, replace
from datetime import date
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import DatabaseBusy, translate_busy
from app.core.events import DomainEvent, emit
from app.core.locks import lock_member
from app.modules.memberships.events import MembershipExpired, MembershipExpiring
from app.modules.memberships.models import Membership
from app.modules.memberships.queries import _load_freezes_for, status_expr
from app.modules.memberships.rules import (
    MembershipStatus,
    compute_status,
    snapshot,
    transition_event,
)
from app.modules.memberships.sell import lock_membership
from app.modules.settings import service as settings_service

logger = logging.getLogger("app.memberships")

RECOMPUTE_PAGE: Final = 200
"""Ids de socio por página de la fase 1."""
MAX_BUSY_RETRIES: Final = 2
"""Reintentos de un socio ocupado antes de omitirlo (`busy_omitidos`)."""
RETRY_DELAYS_S: Final[tuple[float, ...]] = (0.5, 1.0)
"""Espera antes de cada reintento, fuera de la transacción (S4A-D57)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RecomputeSummary:
    """Conteos de una corrida (S4A-D2); claves subconjunto de `core.jobs.DETAIL_KEYS` (E2).

    - `revisados`: socios candidatos de la fase 1 que se procesaron (incluidos los omitidos por
      ocupación y los que fallaron);
    - `cambiadas`: membresías cuya columna `status` cambió (`por_vencer + vencidas + otras`);
    - `por_vencer`: cambios que emitieron `MembershipExpiring`;
    - `vencidas`: cambios que emitieron `MembershipExpired`;
    - `otras`: cambios sin evento (`active` ↔ `frozen`, `frozen` → `active`, ...);
    - `busy_omitidos`: socios omitidos tras agotar los reintentos por ocupación;
    - `errores`: socios cuya transacción falló por cualquier otra causa.
    """

    revisados: int = 0
    cambiadas: int = 0
    por_vencer: int = 0
    vencidas: int = 0
    otras: int = 0
    busy_omitidos: int = 0
    errores: int = 0


async def recompute_statuses(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    today: date,
    page_size: int = RECOMPUTE_PAGE,
) -> RecomputeSummary:
    """Alinea la columna `status` con el estado efectivo de `today` (docstring del módulo)."""
    if page_size < 1:
        raise ValueError("page_size debe ser positivo")
    expiring_days = await _expiring_days(session_factory)
    resumen = RecomputeSummary()
    after: UUID | None = None
    while True:
        async with session_factory() as lectura:
            ids = await _candidate_member_ids(lectura, today, expiring_days, after, limit=page_size)
        for member_id in ids:
            parcial = await _member_summary(session_factory, member_id, today, expiring_days)
            resumen = _sumar(resumen, parcial)
        if len(ids) < page_size:
            break
        after = ids[-1]
    logger.info("membership statuses recomputed", extra=asdict(resumen))
    return resumen


def _sumar(a: RecomputeSummary, b: RecomputeSummary) -> RecomputeSummary:
    """Suma campo a campo (sin mutar `a` ni `b`)."""
    return replace(a, **{k: v + getattr(b, k) for k, v in asdict(a).items()})


async def _expiring_days(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """`expiring_days` de la política, leído una vez por corrida en una sesión corta."""
    async with session_factory() as sesion:
        return (await settings_service.memberships_policy(sesion)).expiring_days


async def _member_summary(
    session_factory: async_sessionmaker[AsyncSession],
    member_id: UUID,
    today: date,
    expiring_days: int,
) -> RecomputeSummary:
    """El aporte de un socio al resumen: sus cambios, o la ocupación, o el error (solo el tipo:
    el mensaje puede traer datos del socio y su id no va al log).

    El log va FUERA del `except`: si un handler falla, `logging.handleError` imprime la traza con
    la excepción en curso encadenada (y su mensaje); sin excepción activa no hay nada que filtrar.
    """
    try:
        cambiadas, por_vencer, vencidas, otras = await _recompute_member(
            session_factory, member_id, today, expiring_days
        )
    except DatabaseBusy:
        tipo, parcial = "DatabaseBusy", RecomputeSummary(revisados=1, busy_omitidos=1)
    except Exception as error:
        tipo, parcial = type(error).__name__, RecomputeSummary(revisados=1, errores=1)
    else:
        return RecomputeSummary(
            revisados=1, cambiadas=cambiadas, por_vencer=por_vencer, vencidas=vencidas, otras=otras
        )
    logger.warning("membership recompute failed", extra={"error_type": tipo})
    return parcial


CANDIDATE_STATUSES: Final = (
    MembershipStatus.active.value,
    MembershipStatus.expiring.value,
    MembershipStatus.frozen.value,
)
"""Estados guardados que el recálculo mira; `pending_payment`, `cancelled` y `expired` no."""


async def _candidate_member_ids(
    session: AsyncSession,
    today: date,
    expiring_days: int,
    after: UUID | None,
    *,
    limit: int = RECOMPUTE_PAGE,
) -> list[UUID]:
    """Fase 1: una página de ids de socio candidatos (sin candados)."""
    consulta = (
        select(Membership.member_id)
        .where(
            Membership.status.in_(CANDIDATE_STATUSES),
            status_expr(today, expiring_days) != Membership.status,
        )
        .group_by(Membership.member_id)
        .order_by(Membership.member_id)
        .limit(limit)
    )
    if after is not None:
        consulta = consulta.where(Membership.member_id > after)
    return list(await session.scalars(consulta))


async def _recompute_member(
    session_factory: async_sessionmaker[AsyncSession],
    member_id: UUID,
    today: date,
    expiring_days: int,
) -> tuple[int, int, int, int]:
    """Fase 2 de un socio con sus reintentos: `(cambiadas, por_vencer, vencidas, otras)`.

    Abre `async with session_factory() as s, s.begin():` y llama `_apply_to_member`; las esperas
    entre reintentos van fuera del `begin()`. Agotados los reintentos propaga la ocupación
    (`recompute_statuses` la cuenta en `busy_omitidos`)."""
    intento = 0
    while True:
        try:
            async with session_factory() as sesion, sesion.begin():
                return await _apply_to_member(sesion, member_id, today, expiring_days)
        except DatabaseBusy:
            if intento >= MAX_BUSY_RETRIES:
                raise
        except DBAPIError as error:
            if translate_busy(error) is None:
                raise
            if intento >= MAX_BUSY_RETRIES:
                raise DatabaseBusy() from error
        await asyncio.sleep(RETRY_DELAYS_S[intento])
        intento += 1


async def _apply_to_member(
    session: AsyncSession, member_id: UUID, today: date, expiring_days: int
) -> tuple[int, int, int, int]:
    """Cuerpo de la transacción de un socio: `lock_member`, `lock_membership` por fila, un solo
    `flush` y los eventos. Devuelve `(cambiadas, por_vencer, vencidas, otras)`."""
    await lock_member(session, member_id)
    filas: list[Membership] = []
    for membership_id in await _candidate_rows_of(session, member_id):
        fila = await lock_membership(session, membership_id)
        if fila is not None and fila.status in CANDIDATE_STATUSES:
            filas.append(fila)
    ventanas = await _load_freezes_for(session, [fila.id for fila in filas])
    eventos: list[DomainEvent] = []
    otras = 0
    for fila in filas:
        previo = MembershipStatus(fila.status)
        nuevo = compute_status(snapshot(fila), today, expiring_days, ventanas.get(fila.id, []))
        if nuevo is previo:
            continue
        fila.status = nuevo.value
        evento = _transition(fila, previo, nuevo, today)
        if evento is None:
            otras += 1
        else:
            eventos.append(evento)
    if not eventos and not otras:
        return 0, 0, 0, 0
    await session.flush()
    for emitido in eventos:
        await emit(emitido, session)
    por_vencer = sum(isinstance(e, MembershipExpiring) for e in eventos)
    vencidas = len(eventos) - por_vencer
    return por_vencer + vencidas + otras, por_vencer, vencidas, otras


async def _candidate_rows_of(session: AsyncSession, member_id: UUID) -> list[UUID]:
    """Ids de las membresías del socio con estado guardado candidato (se releen con candado)."""
    consulta = (
        select(Membership.id)
        .where(Membership.member_id == member_id, Membership.status.in_(CANDIDATE_STATUSES))
        .order_by(Membership.id)
    )
    return list(await session.scalars(consulta))


def _transition(
    fila: Membership, previo: MembershipStatus, nuevo: MembershipStatus, today: date
) -> MembershipExpiring | MembershipExpired | None:
    """El evento de `rules.transition_event` para la fila (solo ids y fechas)."""
    tipo = transition_event(previo, nuevo)
    if tipo is None:
        return None
    clase = MembershipExpiring if tipo == "expiring" else MembershipExpired
    return clase(
        membership_id=fila.id, member_id=fila.member_id, end_date=fila.end_date, on_date=today
    )
