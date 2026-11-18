"""Envío de avisos pendientes (S5-B8, US-125; S5-D28, S5-D35, S5-D227, S5-D228, M-6). Privado: solo
`service.py` lo importa.

`send_pending(session_factory, today, *, load_contact, channel, max_attempts)` recorre los avisos
`email` elegibles y los manda por `channel`:

- elegibles: `pending` de la ventana de 15 días (`today - 15 ... today`, S5-D227) y `failed` de hoy
  y anteriores, ambos con `attempts < max_attempts`; nunca `whatsapp_link`, `sent` ni `skipped`;
- una transacción por aviso con `FOR UPDATE SKIP LOCKED`: (a) `load_contact` y `attempts += 1`,
  COMMIT; (b) FUERA de toda transacción, `channel.send`; (c) segunda transacción: `sent`
  (`sent_at`, `sent_by = SYSTEM_USER_ID`, `last_error` limpio) o `failed` + `last_error` (código
  cerrado). Todo por ORM, así `__audited__` deja las filas `update` (M-6). Un corte entre (b) y
  (c) deja el aviso con el intento contado: la corrida siguiente lo repite una vez como máximo
  (entrega "al menos una vez", tope `NOTIFY_MAX_ATTEMPTS`);
- exclusión entre pasadas paralelas (S9-D44, S9-D45): el candado de fila solo vale durante (a).
  (1) Mientras un aviso está en vuelo su proceso sostiene
  `pg_try_advisory_xact_lock(NOTIFY_LOCK_NS, <clave del id>)` en una transacción aparte sin filas
  bloqueadas, con `idle_in_transaction_session_timeout` local en 0. Candado, preparación, envío y
  cierre son una sola tarea blindada; la pasada cancelada espera a sus unidades (`drain_units`,
  tope `NOTIFY_DRAIN_TIMEOUT_S`, solo las suyas) antes de salir (S9-D46). Toda escritura sobre el
  aviso ocurre dentro de esa unidad, bajo el candado. Un fallo de APERTURA de la conexión
  (`is_open_failure`: `ConnectionError`, `socket.gaierror`, SQLSTATE `08`/`53300`/`57P0x` o pool
  agotado) al tomar el candado o al abrir la sesión de (a) (`_open_connection`) deja el aviso
  intacto, sin gastar intento, y suma a `SendResult.sin_conexion`; tras
  `NOTIFY_MAX_CONNECTION_ERRORS` (3) seguidos la pasada se corta y el job sale no-ok. Un `OSError`
  cualquiera o un fallo posterior a la apertura NO es de conexión: gasta intento (S9-D47). Otra
  pasada que no obtiene el candado deja el aviso intacto; `skip` lo prueba antes de bloquear la
  fila y responde 409 `notification_in_flight`. (2) cada pasada lista `(id, attempts)` y toma la
  fila solo si `attempts` sigue igual (control optimista). `pendientes` cuenta un aviso en vuelo;
- el opt-in se mira ANTES de descifrar (`channels_for` no descifra): sin autorización o con el
  correo apagado se omite sin filas `decrypt` (S9-D46);
- sin canal configurado o con `channels.email.enabled` falso cada aviso queda `skipped` con
  `skip_reason = "canal_no_configurado"`, sin descifrar nada (S5-D222);
- sin autorización de datos o sin correo al enviar: `skipped` con `sin_consentimiento` o
  `sin_correo` (S5-D227); sin el correo entre sus canales efectivos (S5-D31):
  `canal_desactivado_socio`; `channel.send` tiene el tope `NOTIFY_SEND_TIMEOUT_S`;
- un canal que lanza cuenta como `failed`/`unknown` y el lote sigue; una fila ilegible o un bug por
  aviso lo dejan `failed`/`unknown` con el intento contado (S5-D230); solo un fallo del custodio
  (`code == "crypto_unavailable"`) sube y hace fallar el job (M-4);
- el cierre tras un envío exitoso corre bajo `shield` y se reintenta una vez (S5-D229); una corrida
  toma como máximo `NOTIFY_MAX_PER_RUN` avisos y no empieza ninguno pasado
  `NOTIFY_SOFT_DEADLINE_S` (S5-D232); los cinco márgenes suman 570 < 600 s del job (S9-D47);
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
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date
from typing import Final
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.db import is_connection_error
from app.modules.members import service as members_service
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
from app.modules.notifications.schemas import SendResult
from app.modules.notifications.sending_queries import (
    SessionFactory,
    count_eligible,
    eligible_ids,
    lock_eligible,
)
from app.modules.settings import service as settings_service
from app.modules.settings.schemas import ChannelsSettings, SectionKey

logger = logging.getLogger("app.notifications")

LoadContact = Callable[[AsyncSession, UUID], Awaitable[Contact]]

NOTIFY_MAX_ATTEMPTS: Final = 3
"""Intentos por aviso `email` (S5-D35): al tercero fallido queda `failed` para siempre."""
SKIP_NOT_CONFIGURED: Final = "canal_no_configurado"
SKIP_NO_CONSENT: Final = "sin_consentimiento"
SKIP_NO_EMAIL: Final = "sin_correo"
SKIP_MEMBER_CHANNEL_OFF: Final = "canal_desactivado_socio"
UNKNOWN_ERROR: Final = "unknown"

SENT: Final = "enviado"
FAILED: Final = "fallido"
SKIPPED: Final = "omitido"
UNTOUCHED: Final = "intacto"
"""Resultado de un aviso; `UNTOUCHED` = otra transacción lo tenía o ya no era elegible."""
NO_CONNECTION: Final = "sin_conexion"
"""Intacto y sin gastar intento: no se pudo ABRIR la conexión; suma a `sin_conexion` (S9-D47)."""
NOTIFY_MAX_CONNECTION_ERRORS: Final = 3
"""Errores de apertura SEGUIDOS tras los que la pasada se corta (S9-D47)."""

SYSTEMIC_CODE: Final = "crypto_unavailable"
CLOSE_ATTEMPTS: Final = 2
"""Intentos del cierre tras un envío exitoso: el primero y UN reintento (S5-D229)."""
NOTIFY_MAX_PER_RUN: Final = 500
"""Avisos que toma una corrida (S5-D232); lo demás sigue mañana."""
NOTIFY_SOFT_DEADLINE_S: Final = 330
"""Plazo blando (reloj monotónico): pasado, no se toma ninguna fila más. Con los márgenes de
abajo debe caber en el `timeout_s` del job (600 s; S9-D46: 480 a 420; S9-D47: 330)."""
NOTIFY_PRE_MARGIN_S: Final = 60
"""Lo que corre ANTES del plazo blando: generar, `try_load` y el listado (S9-D47)."""
NOTIFY_PREPARE_MARGIN_S: Final = 40
"""Candado y preparación del ÚLTIMO aviso, que puede empezar justo antes del plazo (S9-D47)."""
NOTIFY_LOCK_NS: Final = 4_270_010
"""Primera clave del candado de aviso en vuelo (`pg_try_advisory_xact_lock(int, int)`)."""
IN_FLIGHT_LOCK_SQL: Final = "SELECT pg_try_advisory_xact_lock(:ns, :k)"
NOTIFY_SEND_TIMEOUT_S: Final = 90
"""Tope total de `channel.send` por aviso (S9-D45); menor que el plazo del job (600 s)."""
NOTIFY_CLOSE_MARGIN_S: Final = 50
"""Tras el último envío: el cierre (2 x `DB_LOCK_TIMEOUT_MS`) y el conteo final (30 s)."""
NOTIFY_DRAIN_TIMEOUT_S: Final = 30
"""Cuánto espera una pasada cancelada a que sus unidades en vuelo cierren (S9-D46)."""
_LINE_BREAKS: Final = ("\r", "\n", chr(0x2028), chr(0x2029), chr(0x85))


def _has_line_break(texto: str) -> bool:
    return any(salto in texto for salto in _LINE_BREAKS)


@dataclass(frozen=True, slots=True)
class _Prepared:
    """Lo que sale de la fase (a): solo lo necesario para enviar y cerrar."""

    notification_id: UUID
    member_id: UUID
    payload: ChannelPayload


def _lock_key(notification_id: UUID) -> int:
    """32 bits del id como `int4` con signo; una colisión solo deja un aviso para la corrida
    siguiente (queda intacto)."""
    bajo = notification_id.int & 0xFFFFFFFF
    return bajo - (1 << 32) if bajo >= (1 << 31) else bajo


async def try_in_flight_lock(session: AsyncSession, notification_id: UUID) -> bool:
    """Intenta `pg_try_advisory_xact_lock(NOTIFY_LOCK_NS, <clave>)` en la transacción de `session`
    (no espera). `True` si lo obtuvo; se suelta con el COMMIT o el ROLLBACK de esa transacción."""
    obtenido = await session.scalar(
        text(IN_FLIGHT_LOCK_SQL), {"ns": NOTIFY_LOCK_NS, "k": _lock_key(notification_id)}
    )
    return bool(obtenido)


def is_open_failure(error: BaseException) -> bool:
    """Fallo de APERTURA: error de conexión real (`core.db.is_connection_error`) o pool agotado
    (`sqlalchemy.exc.TimeoutError`, no es un `DBAPIError`; S9-D47). Nada se escribió ni se envió."""
    return isinstance(error, PoolTimeoutError) or is_connection_error(error)


class _ConnectionNotOpened(Exception):
    """No se pudo abrir la conexión de una transacción de `_tx`; la causa va en `__cause__`."""


async def _open_connection(session: AsyncSession) -> None:
    """Toma la conexión del pool ya (la sesión es perezosa): separa la APERTURA del resto."""
    await session.connection()


@asynccontextmanager
async def _in_flight(sf: SessionFactory, notification_id: UUID) -> AsyncIterator[str | None]:
    """Candado de «aviso en vuelo» (S9-D44): cede `None` si esta pasada lo obtuvo; si no, el
    resultado que la unidad debe devolver sin tocar el aviso (`UNTOUCHED` si otra pasada lo tiene
    o la sentencia falló; `NO_CONNECTION` si no se pudo abrir la conexión). Vive en una
    transacción propia, sin filas bloqueadas, abierta hasta que el aviso se cierra; muere con la
    conexión."""
    async with sf() as session:
        cerrado: str | None = None
        try:
            # El candado vive lo que dure el envío: el rol del worker corta las transacciones
            # inactivas a los 60 s y soltaría el candado a mitad de un SMTP lento.
            await session.execute(
                select(func.set_config("idle_in_transaction_session_timeout", "0", True))
            )
            if not await try_in_flight_lock(session, notification_id):
                cerrado = UNTOUCHED
        except Exception as error:
            if is_open_failure(error):
                cerrado = NO_CONNECTION
            elif isinstance(error, SQLAlchemyError):
                cerrado = UNTOUCHED
            else:
                raise
            # pool agotado, CONNECTION LIMIT, puerto cerrado, corte: no se envió nada (S9-D46)
            logger.warning(
                "notifications: no se pudo tomar el candado de aviso en vuelo",
                extra={"notification_id": str(notification_id), "error_type": type(error).__name__},
            )
        try:
            yield cerrado
        finally:
            try:
                await session.rollback()
            except (SQLAlchemyError, OSError) as error:  # p. ej. el timeout de inactividad
                logger.warning(
                    "notifications: no se pudo soltar el candado de aviso en vuelo",
                    extra={
                        "notification_id": str(notification_id),
                        "error_type": type(error).__name__,
                    },
                )


@asynccontextmanager
async def _tx(sf: SessionFactory) -> AsyncIterator[AsyncSession]:
    """Sesión corta con el actor del sistema (D33); solo un fallo de apertura sale como
    `_ConnectionNotOpened`, otro error de la fase (a) gasta intento (S9-D47)."""
    with actor_scope(SYSTEM_USER_ID):
        async with sf() as session, session.begin():
            try:
                await _open_connection(session)
            except Exception as error:
                if is_open_failure(error):
                    raise _ConnectionNotOpened from error
                raise
            yield session


async def _channels_config(sf: SessionFactory) -> ChannelsSettings:
    async with sf() as session:
        valor = await settings_service.get(session, SectionKey.channels)
    if not isinstance(valor, ChannelsSettings):
        raise TypeError("channels")
    return valor


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
    sf: SessionFactory,
    notification_id: UUID,
    expected_attempts: int,
    reason: str,
    today: date,
    max_attempts: int,
) -> str:
    """Omite el aviso sin descifrar nada (canal apagado o sin credenciales)."""
    async with _tx(sf) as session:
        aviso = await lock_eligible(
            session, notification_id, expected_attempts, today, max_attempts
        )
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


async def _deliverable_contact(
    session: AsyncSession, aviso: Notification, load_contact: LoadContact
) -> str | None:
    """El correo si el aviso aún se puede enviar; si no (sin autorización, correo apagado por el
    socio, S5-D31, o sin correo guardado) lo cierra `skipped` y devuelve `None`. Primero la
    consulta que NO descifra (`channels_for`) y solo si el correo sigue activo se descifra
    (S9-D46: un socio apagado no deja filas `decrypt`)."""
    estado = (await members_service.channels_for(session, [aviso.member_id])).get(aviso.member_id)
    if estado is None or not estado.has_consent:
        await _close_as_skipped(session, aviso, SKIP_NO_CONSENT)
        return None
    if "email" not in estado.channels:
        await _close_as_skipped(session, aviso, SKIP_MEMBER_CHANNEL_OFF)
        return None
    try:
        contacto = await load_contact(session, aviso.member_id)
    except MemberNotContactable:
        await _close_as_skipped(session, aviso, SKIP_NO_CONSENT)
        return None
    if not contacto.email:
        await _close_as_skipped(session, aviso, SKIP_NO_EMAIL)
        return None
    return contacto.email


async def _prepare(
    sf: SessionFactory,
    notification_id: UUID,
    expected_attempts: int,
    today: date,
    max_attempts: int,
    load_contact: LoadContact,
    config: ChannelsSettings,
) -> _Prepared | str:
    """Fase (a): candado, contacto y `attempts += 1`, todo confirmado antes de enviar."""
    async with _tx(sf) as session:
        aviso = await lock_eligible(
            session, notification_id, expected_attempts, today, max_attempts
        )
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
        correo = await _deliverable_contact(session, aviso, load_contact)
        if correo is None:
            return SKIPPED
        aviso.attempts += 1
        await session.flush()
        return _Prepared(
            notification_id=aviso.id,
            member_id=aviso.member_id,
            payload=ChannelPayload(
                to=correo,
                subject=aviso.rendered_subject,
                body=aviso.rendered_body,
                reply_to=config.email.reply_to,
                from_name=config.email.sender_name,
            ),
        )


async def _deliver(channel: NotificationChannel, prepared: _Prepared) -> ChannelResult:
    """Fase (b): fuera de toda transacción. Un canal con un bug cuenta como `unknown`."""
    try:
        return await asyncio.wait_for(channel.send(prepared.payload), NOTIFY_SEND_TIMEOUT_S)
    except TimeoutError:
        logger.warning(
            "notifications: el canal no respondió a tiempo",
            extra={"notification_id": str(prepared.notification_id)},
        )
        return ChannelResult(ok=False, error_code="timeout")
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
        if aviso is None or aviso.status in ("sent", "skipped"):
            # No se borran avisos; y uno ya cerrado por otro camino no se pisa (S9-D45).
            if result.ok:
                logger.warning(
                    "notifications: el correo salió pero el aviso ya estaba cerrado",
                    extra={"notification_id": str(prepared.notification_id)},
                )
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
    expected_attempts: int,
    today: date,
    max_attempts: int,
    load_contact: LoadContact,
    channel: NotificationChannel,
    config: ChannelsSettings,
) -> str:
    # Candado, escritura previa, envío y cierre son UNA unidad bajo `shield` (S9-D45): si el job
    # se cancela, el candado se suelta solo cuando el cierre terminó, no antes.
    unidad = asyncio.ensure_future(
        _locked_unit(
            sf,
            notification_id,
            expected_attempts,
            today,
            max_attempts,
            load_contact,
            channel,
            config,
        )
    )
    _UNITS.add(unidad)
    propias = _PASS_UNITS.get()
    if propias is not None:
        propias.add(unidad)
    unidad.add_done_callback(_unit_done)
    return await asyncio.shield(unidad)


_UNITS: set[asyncio.Future[str]] = set()
"""Referencias fuertes a las unidades en vuelo (el bucle solo guarda referencias débiles)."""
_PASS_UNITS: ContextVar[set[asyncio.Future[str]] | None] = ContextVar("pass_units", default=None)
"""Las unidades de ESTA pasada: `send_pending` solo espera a las suyas al cancelarse, no a las de
otra pasada del mismo proceso (S9-D46)."""


async def drain_units(
    units: set[asyncio.Future[str]] | None = None, *, timeout_s: float = NOTIFY_DRAIN_TIMEOUT_S
) -> None:
    """Espera (con tope) a que terminen `units` (por omisión todas las del proceso) sin relanzar
    su resultado: lo que falle ya lo registró `_unit_done`. Sin esto, `asyncio.run` cancela una
    unidad que aún envía y suelta el candado sin cerrar el aviso (S9-D46)."""
    pendientes = {u for u in (_UNITS if units is None else units) if not u.done()}
    if pendientes:
        await asyncio.wait(pendientes, timeout=timeout_s)


def _unit_done(unidad: asyncio.Future[str]) -> None:
    _UNITS.discard(unidad)
    if not unidad.cancelled():
        unidad.exception()  # marca la excepción como leída si nadie esperaba el resultado


async def _prepare_or_skip(
    sf: SessionFactory,
    notification_id: UUID,
    expected_attempts: int,
    today: date,
    max_attempts: int,
    load_contact: LoadContact,
    config: ChannelsSettings,
) -> _Prepared | str:
    """Canal apagado por el admin: `skipped` sin descifrar; si no, la fase (a)."""
    if not config.email.enabled:
        return await _skip(
            sf, notification_id, expected_attempts, SKIP_NOT_CONFIGURED, today, max_attempts
        )
    return await _prepare(
        sf, notification_id, expected_attempts, today, max_attempts, load_contact, config
    )


async def _guarded_prepare(
    sf: SessionFactory,
    notification_id: UUID,
    expected_attempts: int,
    today: date,
    max_attempts: int,
    load_contact: LoadContact,
    config: ChannelsSettings,
) -> _Prepared | str:
    """Lo previo al envío, con el candado de aviso tomado. Un fallo del custodio sube
    (M-4); un fallo de APERTURA de la conexión (`_ConnectionNotOpened`: puerto cerrado, `CONNECTION
    LIMIT`, pool agotado) deja el aviso intacto y sin gastar intento (nada salió, S9-D46, S9-D47);
    cualquier otro, incluso un `OSError` ajeno a la conexión, lo deja `failed`/`unknown` con el
    intento contado (S5-D230)."""
    try:
        return await _prepare_or_skip(
            sf, notification_id, expected_attempts, today, max_attempts, load_contact, config
        )
    except Exception as error:
        if _is_systemic(error):
            raise
        if isinstance(error, _ConnectionNotOpened):
            logger.warning(
                "notifications: sin conexión al preparar un aviso, queda intacto",
                extra={
                    "notification_id": str(notification_id),
                    "error_type": type(error.__cause__).__name__,
                },
            )
            return NO_CONNECTION
        logger.error(
            "notifications: un aviso falló al prepararse",
            extra={"notification_id": str(notification_id), "error_type": type(error).__name__},
        )
        return await _mark_failed(sf, notification_id, expected_attempts, today, max_attempts)


async def _locked_unit(
    sf: SessionFactory,
    notification_id: UUID,
    expected_attempts: int,
    today: date,
    max_attempts: int,
    load_contact: LoadContact,
    channel: NotificationChannel,
    config: ChannelsSettings,
) -> str:
    async with _in_flight(sf, notification_id) as cerrado:
        if cerrado is not None:
            return cerrado  # otra pasada lo tiene en vuelo, o no se pudo tomar (S9-D44, S9-D47)
        preparado = await _guarded_prepare(
            sf, notification_id, expected_attempts, today, max_attempts, load_contact, config
        )
        if isinstance(preparado, str):
            return preparado
        return await _send_and_close(sf, channel, preparado, max_attempts)


async def _mark_failed(
    sf: SessionFactory,
    notification_id: UUID,
    expected_attempts: int,
    today: date,
    max_attempts: int,
) -> str:
    """Un aviso cuya preparación falló (fila ilegible, bug de un suscriptor): `failed`/`unknown`
    con el intento contado, para que acumule hasta el tope y no bloquee la cola (S5-D230)."""
    try:
        async with _tx(sf) as session:
            aviso = await lock_eligible(
                session, notification_id, expected_attempts, today, max_attempts
            )
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
    except (SQLAlchemyError, OSError, _ConnectionNotOpened) as error:
        logger.error(
            "notifications: no se pudo marcar el aviso como fallido",
            extra={"notification_id": str(notification_id), "error_type": type(error).__name__},
        )
    return FAILED


async def _handle(
    sf: SessionFactory,
    notification_id: UUID,
    expected_attempts: int,
    today: date,
    max_attempts: int,
    load_contact: LoadContact,
    channel: NotificationChannel,
    config: ChannelsSettings,
) -> str:
    """Un aviso de la pasada: todo ocurre dentro de su unidad bajo el candado de aviso, también la
    omisión por canal apagado y el `failed` de un fallo de preparación (S9-D46). Solo un fallo
    del custodio (sistémico) sube y hace fallar el job (M-4). Cualquier otro fallo inesperado de UN
    aviso (candado, suscriptor de `_mark_failed`) lo cuenta fallido y la pasada sigue; la
    cancelación (`BaseException`) sube (S9-D47)."""
    try:
        return await _process_one(
            sf,
            notification_id,
            expected_attempts,
            today,
            max_attempts,
            load_contact,
            channel,
            config,
        )
    except Exception as error:
        if _is_systemic(error):
            raise
        logger.error(
            "notifications: un aviso falló de forma inesperada",
            extra={"notification_id": str(notification_id), "error_type": type(error).__name__},
        )
        return FAILED


async def _run_pass(
    sf: SessionFactory,
    pendientes: list[tuple[UUID, int]],
    today: date,
    max_attempts: int,
    load_contact: LoadContact,
    channel: NotificationChannel,
    config: ChannelsSettings,
    soft_deadline_s: float,
    monotonic: Callable[[], float],
) -> dict[str, int]:
    """Recorre `pendientes` y cuenta qué le pasó a cada aviso. Se corta al plazo blando (S5-D232)
    o tras `NOTIFY_MAX_CONNECTION_ERRORS` fallos de apertura seguidos (S9-D47)."""
    conteos = {SENT: 0, FAILED: 0, SKIPPED: 0, UNTOUCHED: 0, NO_CONNECTION: 0}
    seguidos = 0  # errores de apertura sin un aviso que sí abriera entre medias
    inicio = monotonic()
    for notification_id, expected_attempts in pendientes:
        if monotonic() - inicio >= soft_deadline_s:
            break  # S5-D232: lo que falta sigue mañana; los intentos solo se gastan al enviar
        resultado = await _handle(
            sf,
            notification_id,
            expected_attempts,
            today,
            max_attempts,
            load_contact,
            channel,
            config,
        )
        conteos[resultado] += 1
        seguidos = seguidos + 1 if resultado == NO_CONNECTION else 0
        if seguidos >= NOTIFY_MAX_CONNECTION_ERRORS:
            logger.error(
                "notifications: la base no da conexiones, se corta la pasada",
                extra={"sin_conexion": conteos[NO_CONNECTION]},
            )
            break  # lo que falta sigue en la corrida siguiente; nada se gastó
    return conteos


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
    ids = await eligible_ids(session_factory, today, max_attempts)
    if not ids:
        return SendResult(enviados=0, fallidos=0, omitidos=0, pendientes=0)
    config = await _channels_config(session_factory)
    sin_credenciales = config.email.enabled and not channel.configured
    propias: set[asyncio.Future[str]] = set()
    token = _PASS_UNITS.set(propias)
    try:
        # S5-D231: habilitado sin credenciales no es una omisión definitiva; esperan y se avisa.
        tomados = [] if sin_credenciales else ids[:max_per_run]
        conteos = await _run_pass(
            session_factory,
            tomados,
            today,
            max_attempts,
            load_contact,
            channel,
            config,
            soft_deadline_s,
            monotonic,
        )
    finally:
        _PASS_UNITS.reset(token)
        await drain_units(propias)  # cancelada (job, SIGTERM, `asyncio.run`): no soltar a medias
    return SendResult(
        enviados=conteos[SENT],
        fallidos=conteos[FAILED],
        omitidos=conteos[SKIPPED],
        pendientes=await count_eligible(session_factory, today, max_attempts),
        sin_credenciales=sin_credenciales,
        sin_conexion=conteos[NO_CONNECTION],
    )
