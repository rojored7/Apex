"""Envío de avisos pendientes (S5-B8, US-125; S5-D28, S5-D35, S5-D227, S5-D228, M-6). Privado: solo
`service.py` lo importa.

`send_pending(session_factory, today, *, load_contact, channel, max_attempts)` recorre los avisos
`email` elegibles y los manda por `channel`:

- elegibles: `pending` de la ventana de 15 días (`today - 15 ... today`, S5-D227) y `failed` de hoy
  y anteriores, ambos con `attempts < max_attempts`; nunca `whatsapp_link`, `sent` ni `skipped`
  (S5-D228: el rol del worker puede actualizar cualquier fila y nada más lo impide);
- una transacción por aviso con `FOR UPDATE SKIP LOCKED`: (a) `load_contact` y `attempts += 1`,
  COMMIT; (b) FUERA de toda transacción, `channel.send`; (c) segunda transacción: `sent`
  (`sent_at`, `sent_by = SYSTEM_USER_ID`, `last_error` limpio) o `failed` + `last_error` (código
  cerrado). Todo por ORM, así `__audited__` deja las filas `update` (M-6). Un corte entre (b) y
  (c) deja el aviso con el intento contado: la corrida siguiente lo repite una vez como máximo
  (entrega "al menos una vez", tope `NOTIFY_MAX_ATTEMPTS`);
- sin canal configurado o con `channels.email.enabled` falso (sin fila = apagado) cada aviso queda
  `skipped` con `skip_reason = "canal_no_configurado"`, sin descifrar nada (S5-D222);
- socio sin autorización de datos o sin correo al momento del envío: `skipped` con
  `sin_consentimiento` o `sin_correo` (reintentar no sirve; S5-D227), sin llamar al canal;
- un canal que lanza cuenta como `failed`/`unknown` y el lote sigue; una fila ilegible o un bug por
  aviso lo dejan `failed`/`unknown` con el intento contado (S5-D230); solo un fallo del custodio
  (`code == "crypto_unavailable"`) sube y hace fallar el job (M-4);
- el cierre tras un envío exitoso corre bajo `shield` y se reintenta una vez (S5-D229); una corrida
  toma como máximo `NOTIFY_MAX_PER_RUN` avisos y no empieza ninguno pasado
  `NOTIFY_SOFT_DEADLINE_S` (S5-D232);
- `NotificationFailed` solo al agotar los intentos. Ningún log lleva correo, nombre ni cuerpo:
  solo `notification_id` y, como mucho, el tipo del error.

`load_contact` se inyecta desde `service.py`, único llamador de `contact_for_notification`
(S5-D32). La arista `notifications -> settings` (S5-D212) es la lectura de `channels`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import events
from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.members.exceptions import MemberNotContactable
from app.modules.members.service import Contact
from app.modules.notifications.channels.base import (
    ChannelPayload,
    ChannelResult,
    NotificationChannel,
)
from app.modules.notifications.events import (
    NotificationFailed,
    NotificationSent,
    NotificationSkipped,
)
from app.modules.notifications.models import ERROR_CODES, Notification
from app.modules.notifications.queries import PENDING_WINDOW_DAYS
from app.modules.notifications.schemas import SendResult
from app.modules.settings import service as settings_service
from app.modules.settings.schemas import ChannelsSettings, SectionKey

logger = logging.getLogger("app.notifications")

LoadContact = Callable[[AsyncSession, UUID], Awaitable[Contact]]
SessionFactory = async_sessionmaker[AsyncSession]

NOTIFY_MAX_ATTEMPTS: Final = 3
"""Intentos por aviso `email` (S5-D35): al tercero fallido queda `failed` para siempre."""
SKIP_NOT_CONFIGURED: Final = "canal_no_configurado"
SKIP_NO_CONSENT: Final = "sin_consentimiento"
SKIP_NO_EMAIL: Final = "sin_correo"
UNKNOWN_ERROR: Final = "unknown"

SENT: Final = "enviado"
FAILED: Final = "fallido"
SKIPPED: Final = "omitido"
UNTOUCHED: Final = "intacto"
"""Qué le pasó a un aviso en esta pasada; `UNTOUCHED` = otra transacción lo tenía o ya no era
elegible (no cuenta)."""


SYSTEMIC_CODE: Final = "crypto_unavailable"
CLOSE_ATTEMPTS: Final = 2
"""Intentos del cierre tras un envío exitoso: el primero y UN reintento (S5-D229)."""
NOTIFY_MAX_PER_RUN: Final = 500
"""Avisos que toma una corrida (S5-D232); lo demás sigue mañana."""
NOTIFY_SOFT_DEADLINE_S: Final = 480
"""Plazo blando con reloj monotónico: pasado, no se toma ninguna fila más (el job tiene 600 s)."""
_LINE_BREAKS: Final = ("\r", "\n", chr(0x2028), chr(0x2029), chr(0x85))


def _has_line_break(texto: str) -> bool:
    return any(salto in texto for salto in _LINE_BREAKS)


@dataclass(frozen=True, slots=True)
class _Prepared:
    """Lo que sale de la fase (a): solo lo necesario para enviar y cerrar."""

    notification_id: UUID
    member_id: UUID
    payload: ChannelPayload


@asynccontextmanager
async def _tx(sf: SessionFactory) -> AsyncIterator[AsyncSession]:
    """Sesión corta con transacción y el actor del sistema (D33)."""
    with actor_scope(SYSTEM_USER_ID):
        async with sf() as session, session.begin():
            yield session


def _eligible(today: date, max_attempts: int) -> ColumnElement[bool]:
    return and_(
        Notification.channel == "email",
        Notification.attempts < max_attempts,
        or_(
            and_(
                Notification.status == "pending",
                Notification.target_date <= today,
                Notification.target_date >= today - timedelta(days=PENDING_WINDOW_DAYS),
            ),
            and_(Notification.status == "failed", Notification.target_date <= today),
        ),
    )


async def _eligible_ids(sf: SessionFactory, today: date, max_attempts: int) -> list[UUID]:
    async with sf() as session:
        filas = await session.scalars(
            select(Notification.id)
            .where(_eligible(today, max_attempts))
            .order_by(Notification.target_date, Notification.created_at, Notification.id)
        )
        return list(filas)


async def _count_eligible(sf: SessionFactory, today: date, max_attempts: int) -> int:
    async with sf() as session:
        total = await session.scalar(
            select(func.count()).select_from(Notification).where(_eligible(today, max_attempts))
        )
    return int(total or 0)


async def _channels_config(sf: SessionFactory) -> ChannelsSettings:
    async with sf() as session:
        valor = await settings_service.get(session, SectionKey.channels)
    if not isinstance(valor, ChannelsSettings):
        raise TypeError("channels")
    return valor


async def _lock_eligible(
    session: AsyncSession, notification_id: UUID, today: date, max_attempts: int
) -> Notification | None:
    """La fila, si sigue elegible y nadie más la tiene (`SKIP LOCKED`); `None` si no."""
    return await session.scalar(
        select(Notification)
        .where(Notification.id == notification_id, _eligible(today, max_attempts))
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )


async def _close_as_skipped(session: AsyncSession, aviso: Notification, reason: str) -> None:
    aviso.status = "skipped"
    aviso.skip_reason = reason
    await session.flush()
    await events.emit(
        NotificationSkipped(
            notification_id=aviso.id,
            member_id=aviso.member_id,
            channel="email",
        ),
        session,
    )


async def _skip(
    sf: SessionFactory, notification_id: UUID, reason: str, today: date, max_attempts: int
) -> str:
    """Omite el aviso sin descifrar nada (canal apagado o sin credenciales)."""
    async with _tx(sf) as session:
        aviso = await _lock_eligible(session, notification_id, today, max_attempts)
        if aviso is None:
            return UNTOUCHED
        await _close_as_skipped(session, aviso, reason)
    return SKIPPED


async def _fail_for_good(session: AsyncSession, aviso: Notification, max_attempts: int) -> None:
    """Cierra un aviso que nunca se podrá enviar: `failed` con todos los intentos gastados."""
    aviso.attempts = max_attempts
    aviso.status = "failed"
    aviso.last_error = UNKNOWN_ERROR
    await session.flush()
    await events.emit(
        NotificationFailed(notification_id=aviso.id, member_id=aviso.member_id, channel="email"),
        session,
    )


async def _prepare(
    sf: SessionFactory,
    notification_id: UUID,
    today: date,
    max_attempts: int,
    load_contact: LoadContact,
    config: ChannelsSettings,
) -> _Prepared | str:
    """Fase (a): candado, contacto y `attempts += 1`, todo confirmado antes de enviar."""
    async with _tx(sf) as session:
        aviso = await _lock_eligible(session, notification_id, today, max_attempts)
        if aviso is None:
            return UNTOUCHED
        if _has_line_break(aviso.rendered_subject):
            # `core.mail` rechaza siempre este asunto: no se gastan reintentos (LOW 6 de B8).
            logger.warning(
                "notifications: asunto con salto de línea, no se envía",
                extra={"notification_id": str(aviso.id)},
            )
            await _fail_for_good(session, aviso, max_attempts)
            return FAILED
        try:
            contacto = await load_contact(session, aviso.member_id)
        except MemberNotContactable:
            await _close_as_skipped(session, aviso, SKIP_NO_CONSENT)
            return SKIPPED
        if not contacto.email:
            await _close_as_skipped(session, aviso, SKIP_NO_EMAIL)
            return SKIPPED
        aviso.attempts += 1
        await session.flush()
        return _Prepared(
            notification_id=aviso.id,
            member_id=aviso.member_id,
            payload=ChannelPayload(
                to=contacto.email,
                subject=aviso.rendered_subject,
                body=aviso.rendered_body,
                reply_to=config.email.reply_to,
                from_name=config.email.sender_name,
            ),
        )


async def _deliver(channel: NotificationChannel, prepared: _Prepared) -> ChannelResult:
    """Fase (b): fuera de toda transacción. Un canal con un bug cuenta como `unknown`."""
    try:
        return await channel.send(prepared.payload)
    except Exception as error:
        logger.warning(
            "notifications: el canal lanzó al enviar",
            extra={
                "notification_id": str(prepared.notification_id),
                "error_type": type(error).__name__,
            },
        )
        return ChannelResult(ok=False, error_code=UNKNOWN_ERROR)


async def _finish(
    sf: SessionFactory, prepared: _Prepared, result: ChannelResult, max_attempts: int
) -> str:
    """Fase (c): `sent` o `failed` en una transacción nueva (por ORM, deja `update`)."""
    async with _tx(sf) as session:
        aviso = await session.scalar(
            select(Notification)
            .where(Notification.id == prepared.notification_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if aviso is None:  # no se borran avisos; solo por un entorno roto
            return UNTOUCHED
        if result.ok:
            aviso.status = "sent"
            aviso.sent_at = current_clock().now_utc()
            aviso.sent_by = SYSTEM_USER_ID
            aviso.last_error = None
            await session.flush()
            await events.emit(
                NotificationSent(
                    notification_id=aviso.id, member_id=aviso.member_id, channel="email"
                ),
                session,
            )
            return SENT
        codigo = result.error_code if result.error_code in ERROR_CODES else UNKNOWN_ERROR
        aviso.status = "failed"
        aviso.last_error = codigo
        await session.flush()
        if aviso.attempts >= max_attempts:
            await events.emit(
                NotificationFailed(
                    notification_id=aviso.id, member_id=aviso.member_id, channel="email"
                ),
                session,
            )
        return FAILED


def _is_systemic(error: BaseException) -> bool:
    """Un fallo del custodio (sellado, inalcanzable, sin permiso, sin keyring), no de UNA fila.
    Se reconoce por su `code` fijo para no importar `core.crypto` aquí (S5-D230)."""
    return getattr(error, "code", None) == SYSTEMIC_CODE


async def _send_and_close(
    sf: SessionFactory, channel: NotificationChannel, prepared: _Prepared, max_attempts: int
) -> str:
    """Fases (b) y (c) como una unidad que sobrevive a la cancelación del job (S5-D229): el correo
    ya salió, así que el cierre se reintenta UNA vez con sesión nueva; si también falla, el aviso
    queda con el intento contado (se repetirá: entrega "al menos una vez") y cuenta `fallido`."""
    resultado = await _deliver(channel, prepared)
    for _intento in range(CLOSE_ATTEMPTS):
        try:
            return await _finish(sf, prepared, resultado, max_attempts)
        except Exception as error:
            if _is_systemic(error):
                raise
            logger.error(
                "notifications: no se pudo cerrar un aviso tras enviarlo",
                extra={
                    "notification_id": str(prepared.notification_id),
                    "error_type": type(error).__name__,
                },
            )
    return FAILED


async def _process_one(
    sf: SessionFactory,
    notification_id: UUID,
    today: date,
    max_attempts: int,
    load_contact: LoadContact,
    channel: NotificationChannel,
    config: ChannelsSettings,
) -> str:
    preparado = await _prepare(sf, notification_id, today, max_attempts, load_contact, config)
    if isinstance(preparado, str):
        return preparado
    # El envío (`to_thread`) no se cancela: bajo `shield` el cierre ocurre aunque el job caiga.
    unidad = asyncio.ensure_future(_send_and_close(sf, channel, preparado, max_attempts))
    return await asyncio.shield(unidad)


async def _mark_failed(
    sf: SessionFactory, notification_id: UUID, today: date, max_attempts: int
) -> str:
    """Un aviso cuya preparación falló (fila ilegible, bug de un suscriptor): `failed`/`unknown`
    con el intento contado, para que acumule hasta el tope y no bloquee la cola (S5-D230)."""
    try:
        async with _tx(sf) as session:
            aviso = await _lock_eligible(session, notification_id, today, max_attempts)
            if aviso is None:
                return FAILED
            aviso.attempts += 1
            aviso.status = "failed"
            aviso.last_error = UNKNOWN_ERROR
            await session.flush()
            if aviso.attempts >= max_attempts:
                await events.emit(
                    NotificationFailed(
                        notification_id=aviso.id, member_id=aviso.member_id, channel="email"
                    ),
                    session,
                )
    except SQLAlchemyError as error:
        logger.error(
            "notifications: no se pudo marcar el aviso como fallido",
            extra={"notification_id": str(notification_id), "error_type": type(error).__name__},
        )
    return FAILED


async def _handle(
    sf: SessionFactory,
    notification_id: UUID,
    today: date,
    max_attempts: int,
    load_contact: LoadContact,
    channel: NotificationChannel,
    config: ChannelsSettings,
) -> str:
    """Un aviso de la pasada: apagado por el admin → `skipped`; si no, las tres fases. Un fallo
    no sistémico lo deja `failed`/`unknown` (S5-D230); lo sistémico (custodio) relanza (M-4)."""
    if not config.email.enabled:
        return await _skip(sf, notification_id, SKIP_NOT_CONFIGURED, today, max_attempts)
    try:
        return await _process_one(
            sf, notification_id, today, max_attempts, load_contact, channel, config
        )
    except Exception as error:
        if _is_systemic(error):
            raise
        logger.error(
            "notifications: un aviso falló al prepararse",
            extra={"notification_id": str(notification_id), "error_type": type(error).__name__},
        )
        return await _mark_failed(sf, notification_id, today, max_attempts)


async def send_pending(
    session_factory: SessionFactory,
    today: date,
    *,
    load_contact: LoadContact,
    channel: NotificationChannel,
    max_attempts: int = NOTIFY_MAX_ATTEMPTS,
    max_per_run: int = NOTIFY_MAX_PER_RUN,
    soft_deadline_s: float = NOTIFY_SOFT_DEADLINE_S,
    monotonic: Callable[[], float] = time.monotonic,
) -> SendResult:
    ids = await _eligible_ids(session_factory, today, max_attempts)
    if not ids:
        return SendResult(enviados=0, fallidos=0, omitidos=0, pendientes=0)
    config = await _channels_config(session_factory)
    sin_credenciales = config.email.enabled and not channel.configured
    conteos = {SENT: 0, FAILED: 0, SKIPPED: 0, UNTOUCHED: 0}
    inicio = monotonic()
    # S5-D231: habilitado sin credenciales no es una omisión definitiva; esperan y se avisa.
    for notification_id in [] if sin_credenciales else ids[:max_per_run]:
        if monotonic() - inicio >= soft_deadline_s:
            break  # S5-D232: lo que falta sigue mañana; los intentos solo se gastan al enviar
        resultado = await _handle(
            session_factory,
            notification_id,
            today,
            max_attempts,
            load_contact,
            channel,
            config,
        )
        conteos[resultado] += 1
    return SendResult(
        enviados=conteos[SENT],
        fallidos=conteos[FAILED],
        omitidos=conteos[SKIPPED],
        pendientes=await _count_eligible(session_factory, today, max_attempts),
        sin_credenciales=sin_credenciales,
    )
