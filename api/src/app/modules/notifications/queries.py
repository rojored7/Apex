"""Lecturas de avisos (S5-B7, US-128, US-130; S5-D92, S5-D219, N-20). Privado: solo `service.py`
lo importa.

- `today_list` / `today_count`: "por avisar hoy" (S5-D219, S5-D225; sin socios dados de baja): los
  `pending` de hoy y de los 15 días anteriores (un WhatsApp no enviado ayer sigue por avisar) y
  los `failed` de hoy y anteriores.
- `list_`: el historial con filtros y `q` por nombre (`members.service.search_ids`).
- `get`: un aviso (`NotificationNotFound`).
- `list_for_member`: la pestaña del socio, incluidos los dados de baja; `MemberNotFound` si no
  existe.
Los nombres salen de `members.service.names_for` por lote; nunca se descifra nada.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, PageParams, any_uuids, paginate, to_page
from app.modules.members import service as members_service
from app.modules.notifications.exceptions import NotificationNotFound
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationFilters, NotificationOut

PENDING_WINDOW_DAYS: Final = 15


def _today_condition(today: date) -> ColumnElement[bool]:
    return or_(
        and_(
            Notification.status == "pending",
            Notification.target_date <= today,
            Notification.target_date >= today - timedelta(days=PENDING_WINDOW_DAYS),
        ),
        and_(Notification.status == "failed", Notification.target_date <= today),
    )


def _ordered(consulta: Select[Any]) -> Select[Any]:
    return consulta.order_by(Notification.target_date.desc(), Notification.id)


async def _outputs(session: AsyncSession, filas: Sequence[Notification]) -> list[NotificationOut]:
    nombres = await members_service.names_for(session, (f.member_id for f in filas))
    salida: list[NotificationOut] = []
    for fila in filas:
        socio = nombres.get(fila.member_id)
        nombre = f"{socio.first_name} {socio.last_name}" if socio else ""
        campos = {c: getattr(fila, c) for c in NotificationOut.model_fields if c != "member_name"}
        salida.append(NotificationOut(member_name=nombre, **campos))
    return salida


async def _page(
    session: AsyncSession, consulta: Select[Any], page: PageParams
) -> Page[NotificationOut]:
    filas, total = await paginate(session, _ordered(consulta), page)
    return to_page(await _outputs(session, filas), total, page)


async def _by_name(session: AsyncSession, q: str | None) -> set[UUID] | None:
    if q is None or not q.strip():
        return None
    return await members_service.search_ids(session, q, include_deleted=True)


async def today_list(
    session: AsyncSession, today: date, page: PageParams, q: str | None = None
) -> Page[NotificationOut]:
    consulta = select(Notification).where(_today_condition(today))
    vivos = await members_service.active_ids(session)  # S5-D225: sin socios dados de baja
    consulta = consulta.where(Notification.member_id == any_uuids(vivos))
    socios = await _by_name(session, q)
    if socios is not None:
        if not socios:
            return to_page([], 0, page)
        consulta = consulta.where(Notification.member_id == any_uuids(socios))
    return await _page(session, consulta, page)


async def today_count(session: AsyncSession, today: date) -> int:
    pagina = await today_list(session, today, PageParams(limit=1, offset=0), None)
    return pagina.total


async def list_(
    session: AsyncSession, filters: NotificationFilters, page: PageParams
) -> Page[NotificationOut]:
    consulta = select(Notification)
    if filters.status is not None:
        consulta = consulta.where(Notification.status == filters.status)
    if filters.channel is not None:
        consulta = consulta.where(Notification.channel == filters.channel)
    if filters.rule_id is not None:
        consulta = consulta.where(Notification.rule_id == filters.rule_id)
    if filters.from_date is not None:
        consulta = consulta.where(Notification.target_date >= filters.from_date)
    if filters.to_date is not None:
        consulta = consulta.where(Notification.target_date <= filters.to_date)
    socios = await _by_name(session, filters.q)
    if socios is not None:
        if not socios:
            return to_page([], 0, page)
        consulta = consulta.where(Notification.member_id == any_uuids(socios))
    return await _page(session, consulta, page)


async def get(session: AsyncSession, notification_id: UUID) -> NotificationOut:
    fila = await session.get(Notification, notification_id)
    if fila is None:
        raise NotificationNotFound()
    return (await _outputs(session, [fila]))[0]


async def list_for_member(
    session: AsyncSession, member_id: UUID, page: PageParams
) -> Page[NotificationOut]:
    await members_service.ensure_exists(session, member_id, include_deleted=True)
    consulta = select(Notification).where(Notification.member_id == member_id)
    return await _page(session, consulta, page)
