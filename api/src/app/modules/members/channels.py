"""Preferencias de canal de aviso del socio (S5-B5, US-123; S5-D31, S5-D210, N-20, N-33).

Archivo privado de `members` (S4A-D72): solo lo importa `members`; los demás módulos llegan por
la fachada `members/service.py`, que re-exporta estas tres funciones.

- `channels_for(session, member_ids) -> dict[UUID, frozenset[str]]`: canales efectivos por lote,
  UNA consulta a `members.member_channel_preferences`; un socio sin filas recibe los valores por
  defecto de `rules.effective_channels`. Un id que no existe no aparece en el resultado y uno
  dado de baja SÍ aparece: el llamador (`notifications`, B7 `generate`) trata la ausencia como
  "no contactable".
- `get_channels(session, member_id) -> ChannelsOut`: también sobre un dado de baja (N-20).
- `set_channels(session, member_id, items, by) -> ChannelsOut`: `lock_member` primero, 409
  `member_deleted` si el socio tiene `deleted_at`, 422 `consent_required` si activa el correo sin
  `data_consent_at` (S5-D211), upsert por `(member_id, channel)` y, si algo
  cambió, el evento `MemberUpdated(changed_fields=("channels",))` sin valores (S5-D210). La
  auditoría la escribe el oyente de `__audited__` con el socio como sujeto.
- `get_channels` y `set_channels` corren solo bajo el rol del api (el worker no escribe
  `audit_log`; allí solo se usa `channels_for`).
- No hace `commit()`: lo hace quien llama (el router por la dependencia de sesión).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.locks import lock_member
from app.modules.members.changes import MemberUpdated
from app.modules.members.exceptions import ConsentRequired, MemberDeleted, MemberNotFound
from app.modules.members.models import Member, MemberChannelPreference
from app.modules.members.rules import effective_channels
from app.modules.members.schemas import ChannelItem, ChannelsOut

CHANNELS_FIELD: Final = "channels"


def _efectivos(filas: Iterable[MemberChannelPreference], has_consent: bool) -> frozenset[str]:
    activos = frozenset(f.channel for f in filas if f.active)
    inactivos = frozenset(f.channel for f in filas if not f.active)
    return effective_channels(activos, inactivos, has_consent)


def _salida(
    member_id: UUID, filas: Sequence[MemberChannelPreference], has_consent: bool
) -> ChannelsOut:
    return ChannelsOut(
        member_id=member_id,
        channels=[
            ChannelItem(channel=f.channel, active=f.active)
            for f in sorted(filas, key=lambda fila: fila.channel)
        ],
        effective=sorted(_efectivos(filas, has_consent)),
        has_consent=has_consent,
    )


async def _filas_de(session: AsyncSession, member_id: UUID) -> list[MemberChannelPreference]:
    consulta = (
        select(MemberChannelPreference)
        .where(MemberChannelPreference.member_id == member_id)
        .execution_options(populate_existing=True)
    )
    return list((await session.scalars(consulta)).all())


async def channels_for(
    session: AsyncSession, member_ids: Iterable[UUID]
) -> dict[UUID, frozenset[str]]:
    """Canales efectivos de varios socios; una consulta a las preferencias para todo el lote."""
    ids = list(dict.fromkeys(member_ids))
    if not ids:
        return {}
    consentimiento = {
        fila.id: fila.data_consent_at is not None
        for fila in (
            await session.execute(
                select(Member.id, Member.data_consent_at).where(Member.id.in_(ids))
            )
        ).all()
    }
    por_socio: dict[UUID, list[MemberChannelPreference]] = defaultdict(list)
    consulta = (
        select(MemberChannelPreference)
        .where(MemberChannelPreference.member_id.in_(ids))
        .execution_options(populate_existing=True)
    )
    for fila in (await session.scalars(consulta)).all():
        por_socio[fila.member_id].append(fila)
    return {
        socio: _efectivos(por_socio.get(socio, []), tiene)
        for socio, tiene in consentimiento.items()
    }


async def get_channels(session: AsyncSession, member_id: UUID) -> ChannelsOut:
    """Preferencias, canales efectivos y consentimiento; `MemberNotFound` si no existe."""
    consentimiento = (
        await session.execute(select(Member.data_consent_at).where(Member.id == member_id))
    ).all()
    if not consentimiento:
        raise MemberNotFound()
    return _salida(member_id, await _filas_de(session, member_id), consentimiento[0][0] is not None)


async def set_channels(
    session: AsyncSession, member_id: UUID, items: Sequence[ChannelItem], by: UUID
) -> ChannelsOut:
    """Upsert por `(member_id, channel)`; `MemberDeleted` (409) si el socio está dado de baja."""
    await lock_member(session, member_id)
    socio = await session.scalar(
        select(Member).where(Member.id == member_id).execution_options(populate_existing=True)
    )
    if socio is None:
        raise MemberNotFound()
    if socio.deleted_at is not None:
        raise MemberDeleted()
    if socio.data_consent_at is None and any(i.channel == "email" and i.active for i in items):
        raise ConsentRequired()  # S5-D211: el opt-in del correo no se guarda sin base legal
    filas = await _filas_de(session, member_id)
    por_canal = {f.channel: f for f in filas}
    cambio = False
    for item in items:
        existente = por_canal.get(item.channel)
        if existente is None:
            nueva = MemberChannelPreference(
                member_id=member_id, channel=item.channel, active=item.active, created_by=by
            )
            session.add(nueva)
            por_canal[item.channel] = nueva
            cambio = True
        elif existente.active != item.active:
            existente.active = item.active
            cambio = True
    if cambio:
        await session.flush()
        await events.emit(
            MemberUpdated(member_id=member_id, changed_fields=(CHANNELS_FIELD,)), session
        )
    return _salida(member_id, list(por_canal.values()), socio.data_consent_at is not None)
