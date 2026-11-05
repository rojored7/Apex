"""Generación diaria de avisos (S5-B7, US-124; S5-D26, S5-D71, S5-D218, M-6). Privado: solo
`service.py` lo importa.

`generate_today(session, today)`: reglas activas; fechas objetivo `today - 15 ... today` (N-35);
candidatos por `memberships.service.notification_candidates`; canales por
`members.service.channels_for` en lotes de `BATCH_SIZE` socios; una inserción ORM por aviso nuevo
dentro de `begin_nested()` (un `IntegrityError` es "ya existente"); `NotificationQueued` solo para
filas realmente insertadas. Una transacción por lote: confirma al terminar cada uno. El actor lo
fija quien llama. No descifra nada: el nombre sale de `members.service.names_for`.

Orden de descarte de cada par (candidata, regla): fuera de la ventana; `membership_expiring` de una
membresía ya terminada; socio dado de baja (ni se cuenta); sin consentimiento
(`sin_consentimiento`, sin fila, D54); `membership_expired` de quien ya renovó (`ya_renovaron`);
aviso ya existente. Después, el aviso nace `skipped` (no cuenta en `generados`, no emite
`NotificationQueued`) con `skip_reason = "canal_no_configurado"` si `settings.channels` no
habilita el canal de la regla (sin fila = apagado, S5-D265a) o `"canal_desactivado_socio"` si el
socio, con consentimiento, apagó ese canal (S5-D266). Una plantilla que no se puede renderizar
deja el aviso `skipped` con `skip_reason = "plantilla_invalida"` (S5-D218) y se cuenta en
`omitidos_por_plantilla`. `settings.channels` se lee una vez por corrida.

Cada lote toma `pg_advisory_xact_lock(hashtext(GENERATE_LOCK_KEY))` antes de leer (S5-D223): dos
corridas se serializan y la segunda ve lo que confirmó la primera. `sin_consentimiento` y
`ya_renovaron` cuentan socios distintos por corrida.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.db import violated_constraint
from app.core.pagination import chunked
from app.modules.members import service as members_service
from app.modules.members.schemas import MemberChannelState
from app.modules.memberships import service as memberships_service
from app.modules.memberships.schemas import NotificationCandidate
from app.modules.notifications import rules
from app.modules.notifications.events import NotificationQueued
from app.modules.notifications.exceptions import TemplateError
from app.modules.notifications.models import (
    NOTIFICATION_KEY,
    Notification,
    NotificationRule,
    NotificationTemplate,
)
from app.modules.notifications.schemas import GenerateResult
from app.modules.settings import service as settings_service
from app.modules.settings.schemas import ChannelsSettings, SectionKey

logger = logging.getLogger("app.notifications")

BATCH_SIZE: Final = 200
WINDOW_DAYS: Final = 15
INVALID_TEMPLATE: Final = "plantilla_invalida"
SKIP_CHANNEL_NOT_CONFIGURED: Final = "canal_no_configurado"
SKIP_MEMBER_CHANNEL_OFF: Final = "canal_desactivado_socio"
GENERATE_LOCK_SQL: Final = "SELECT pg_advisory_xact_lock(hashtext(:k))"
GENERATE_LOCK_KEY: Final = "apex:generate:notifications"
INVALID_SUBJECT: Final = "Plantilla inválida"
MONTHS: Final = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_Key = tuple[UUID, UUID, date]
_Pair = tuple[NotificationCandidate, NotificationRule, date]


@dataclass(frozen=True)
class _Reglas:
    """Lo que no cambia entre lotes: reglas activas, plantillas y canales habilitados por el
    admin (clave = `NotificationRule.channel`)."""

    activas: Sequence[NotificationRule]
    plantillas: Mapping[UUID, NotificationTemplate]
    habilitados: Mapping[str, bool]


class _Counts:
    def __init__(self) -> None:
        self.generados = 0
        self.ya_renovaron: set[UUID] = set()
        self.sin_consentimiento: set[UUID] = set()
        self.omitidos_por_plantilla = 0


def vence_text(end_date: date) -> str:
    """`{vence}`: día sin ceros, mes abreviado en minúsculas y año (`5 nov 2026`)."""
    return f"{end_date.day} {MONTHS[end_date.month - 1]} {end_date.year}"


async def _enabled_channels(session: AsyncSession) -> dict[str, bool]:
    """`settings.channels` → `email` y `whatsapp_link` habilitados (S5-D265a; sin fila, apagado)."""
    valor = await settings_service.get(session, SectionKey.channels)
    if not isinstance(valor, ChannelsSettings):
        raise TypeError("channels")
    return {"email": valor.email.enabled, "whatsapp_link": valor.whatsapp.enabled}


async def generate_today(session: AsyncSession, today: date) -> GenerateResult:
    activas = list(
        await session.scalars(
            select(NotificationRule)
            .where(NotificationRule.is_active.is_(True))
            .order_by(NotificationRule.offset_days, NotificationRule.id)
        )
    )
    if not activas:
        return GenerateResult(0, 0, 0, True)
    reglas = _Reglas(activas, await _templates(session, activas), await _enabled_channels(session))
    inicio = today - timedelta(days=WINDOW_DAYS)
    fines = {
        inicio + timedelta(days=d) - timedelta(days=r.offset_days)
        for r in activas
        for d in range(WINDOW_DAYS + 1)
    }
    por_socio: dict[UUID, list[NotificationCandidate]] = defaultdict(list)
    for candidata in await memberships_service.notification_candidates(session, fines):
        por_socio[candidata.member_id].append(candidata)
    vivos = await members_service.active_ids(session)
    socios = sorted(m for m in por_socio if m in vivos)
    cuentas = _Counts()
    for lote in chunked(socios, BATCH_SIZE):
        await _process_batch(session, today, lote, por_socio, reglas, cuentas)
        await session.commit()
    logger.info("notifications: generación", extra={"generated": cuentas.generados})
    return GenerateResult(
        cuentas.generados,
        len(cuentas.ya_renovaron),
        len(cuentas.sin_consentimiento),
        False,
        cuentas.omitidos_por_plantilla,
    )


async def _templates(
    session: AsyncSession, activas: Sequence[NotificationRule]
) -> dict[UUID, NotificationTemplate]:
    ids = {r.template_id for r in activas}
    consulta = select(NotificationTemplate).where(NotificationTemplate.id.in_(ids))
    return {p.id: p for p in await session.scalars(consulta)}


def _pairs(
    today: date,
    candidatas: Sequence[NotificationCandidate],
    activas: Sequence[NotificationRule],
) -> list[_Pair]:
    """Pares (candidata, regla) cuyo objetivo cae en la ventana y que tienen sentido. De las reglas
    de vencida de una misma membresía solo cuenta la más reciente: avisar "venció hace 1 día" a
    quien lleva 7 sería un texto viejo (la recuperación de N-35 es para el aviso que toca)."""
    inicio = today - timedelta(days=WINDOW_DAYS)
    salida: list[_Pair] = []
    ultimas: dict[UUID, date] = {}
    for c in candidatas:
        for r in activas:
            objetivo = rules.target_dates(r, c.end_date)
            if not inicio <= objetivo <= today:
                continue
            if r.trigger == "membership_expiring" and c.end_date < today:
                continue
            if r.trigger == "membership_expired":
                ultimas[c.membership_id] = max(ultimas.get(c.membership_id, objetivo), objetivo)
            salida.append((c, r, objetivo))
    return [
        (c, r, o)
        for c, r, o in salida
        if r.trigger != "membership_expired" or o == ultimas[c.membership_id]
    ]


async def _process_batch(
    session: AsyncSession,
    today: date,
    lote: Sequence[UUID],
    por_socio: dict[UUID, list[NotificationCandidate]],
    reglas: _Reglas,
    cuentas: _Counts,
) -> None:
    await session.execute(text(GENERATE_LOCK_SQL), {"k": GENERATE_LOCK_KEY})
    canales = await members_service.channels_for(session, list(lote))
    pares = [par for socio in lote for par in _pairs(today, por_socio[socio], reglas.activas)]
    if not pares:
        return
    renovados = await memberships_service.has_current_or_future(
        session, {c.member_id for c, r, _ in pares if r.trigger == "membership_expired"}, today
    )
    nombres = await members_service.names_for(session, lote)
    existentes = await _existing(session, [c.membership_id for c, _, _ in pares])
    for candidata, regla, objetivo in pares:
        estado = canales.get(candidata.member_id)
        if estado is None or not estado.has_consent:
            cuentas.sin_consentimiento.add(candidata.member_id)
        elif regla.trigger == "membership_expired" and candidata.member_id in renovados:
            cuentas.ya_renovaron.add(candidata.member_id)
        elif (regla.id, candidata.membership_id, objetivo) not in existentes:
            motivo = _skip_reason(regla, estado, reglas.habilitados)
            socio = nombres.get(candidata.member_id)
            nombre = socio.first_name if socio else ""
            plantilla = reglas.plantillas[regla.template_id]
            await _insert(session, regla, plantilla, candidata, objetivo, nombre, motivo, cuentas)


def _skip_reason(
    regla: NotificationRule, estado: MemberChannelState, habilitados: Mapping[str, bool]
) -> str | None:
    """Por qué el aviso de esta regla nace `skipped` por el canal; `None` si puede enviarse."""
    if not habilitados.get(regla.channel, False):
        return SKIP_CHANNEL_NOT_CONFIGURED
    if regla.channel not in estado.channels:
        return SKIP_MEMBER_CHANNEL_OFF
    return None


async def _existing(session: AsyncSession, membership_ids: Sequence[UUID]) -> set[_Key]:
    claves: set[_Key] = set()
    for trozo in chunked(list(dict.fromkeys(membership_ids))):
        consulta = select(
            Notification.rule_id, Notification.membership_id, Notification.target_date
        ).where(Notification.membership_id.in_(trozo))
        claves.update((f[0], f[1], f[2]) for f in (await session.execute(consulta)).all())
    return claves


def _render(
    plantilla: NotificationTemplate, candidata: NotificationCandidate, objetivo: date, nombre: str
) -> tuple[str, str] | None:
    contexto: dict[str, str | int] = {
        "nombre": nombre,
        "plan": candidata.plan_name,
        "vence": vence_text(candidata.end_date),
        "dias": rules.days_value(candidata.end_date, objetivo),
    }
    try:
        asunto = rules.render_subject(plantilla.subject, contexto)
        return asunto, rules.render(plantilla.body, contexto)
    except TemplateError:
        return None


async def _insert(
    session: AsyncSession,
    regla: NotificationRule,
    plantilla: NotificationTemplate,
    candidata: NotificationCandidate,
    objetivo: date,
    nombre: str,
    motivo: str | None,
    cuentas: _Counts,
) -> None:
    textos = _render(plantilla, candidata, objetivo, nombre)
    pendiente = textos is not None and motivo is None
    aviso = Notification(
        rule_id=regla.id,
        member_id=candidata.member_id,
        membership_id=candidata.membership_id,
        target_date=objetivo,
        channel=regla.channel,
        status="pending" if pendiente else "skipped",
        rendered_subject=textos[0] if textos else INVALID_SUBJECT,
        rendered_body=textos[1] if textos else "",
        attempts=0,
        skip_reason=None if pendiente else (motivo or INVALID_TEMPLATE),
    )
    try:
        async with session.begin_nested():
            session.add(aviso)
            await session.flush()
    except IntegrityError as error:
        if violated_constraint(error) != NOTIFICATION_KEY:
            raise
        return  # otra corrida lo creó entre la lectura y la inserción: ya existente (D223)
    if not pendiente:
        if motivo is None:
            cuentas.omitidos_por_plantilla += 1
        return  # `skipped` por canal o por plantilla: ni `generados` ni `NotificationQueued`
    cuentas.generados += 1
    await events.emit(
        NotificationQueued(
            notification_id=aviso.id,
            member_id=aviso.member_id,
            rule_id=regla.id,
            channel=regla.channel,  # type: ignore[arg-type]
            target_date=objetivo,
        ),
        session,
    )
