"""Enlaces de un solo uso: activación, recuperación y reenvío (S2-B4: US-048, US-052; H-2,
H-3, L-13, S2-D36, S2-D37, S2-D40). Privado del módulo (revisión Python H1); se usa a través de
`auth.service`.

- `reset`: token con `FOR UPDATE` (orden usuario → token), política con `field="new_password"`,
  hash nuevo, cierre de los demás enlaces abiertos y, si es `reset`, `revoke_all` y
  `SessionsRevoked`; `PasswordChanged(via=<propósito>, via_link_issued_by=<created_by>)`.
- `forgot` (H-2): no lee ni escribe la base; cuenta el intento en `FORGOT_ACCOUNT_BUCKET` y
  espera el piso de `sessions.wait_floor` exista o no la cuenta.
- `forgot_deliver` (S5-B9, US-131; D38, D91): lo que `forgot` no hace, DESPUÉS de responder y en
  una sesión propia: cuenta elegible, token `reset` y correo, con semáforo de 4 y cola de 32.
- `resend_link` (L-13) e `issue_link` (el mismo enlace sin L-13, solo para
  `cli issue-reset-link`).
"""

from __future__ import annotations

import asyncio
import logging
import time
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final, Literal
from uuid import UUID

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events, ratelimit
from app.core.clock import current_clock
from app.core.config import Settings
from app.core.context import actor_scope
from app.core.mail import mail_configured, send_mail
from app.core.security import (
    TokenInvalid,
    hash_opaque_token,
    hash_password,
)
from app.modules.auth import mail_texts, rules, tokens
from app.modules.auth.events import (
    PasswordChanged,
    SessionsRevoked,
)
from app.modules.auth.exceptions import (
    InvalidToken,
    UserNotEligible,
)
from app.modules.auth.models import OneTimeToken, User
from app.modules.auth.rules import (
    AuthPolicy,
    is_active_admin,
    normalize_login_email,
)
from app.modules.auth.schemas import (
    IssuedLinkOut,
    UserStatus,
)
from app.modules.auth.sessions import wait_floor

logger = logging.getLogger("app.auth")


# S2-D36 (H-2): tope por cuenta de `forgot`, además de `rate_limit("forgot")` por IP. Cuenta todo
# intento sobre el correo normalizado, exista o no la cuenta.
FORGOT_ACCOUNT_BUCKET: Final = "forgot-account"


FORGOT_ACCOUNT_LIMIT: Final = 5


FORGOT_ACCOUNT_WINDOW_S: Final = 3600


# S5-D238: tope del envío síncrono de `create_user` y `resend_link` (dentro de la transacción de
# la petición); menor que el del proxy y que `DB_IDLE_IN_TX_TIMEOUT_MS`.
AUTH_MAIL_TIMEOUT_S: Final = 15


# Estados que pueden recibir un enlace: los demás (bloqueado, borrado, inactivo) no lo podrían
# usar (`rules.is_one_time_token_usable`).
_LINK_ELIGIBLE: Final[frozenset[UserStatus]] = frozenset({"active", "pending_activation"})


# Restablecer y recuperar ---------------------------------------------------------------------


async def _locked_one_time_token(
    session: AsyncSession, token: str
) -> tuple[OneTimeToken, User] | None:
    """El token y su usuario con `FOR UPDATE`, siempre en el orden usuario → token (el mismo de
    `resend_link`, `issue_link` y `change_password`; sin él, una emisión concurrente podría dar
    un interbloqueo). Dos `reset` con el mismo token se serializan en el usuario y el segundo
    lee `used_at` fresco."""
    try:
        token_hash = hash_opaque_token(token)
    except TokenInvalid:
        return None
    dueno = await session.scalar(
        select(OneTimeToken.user_id).where(OneTimeToken.token_hash == token_hash)
    )
    if dueno is None:
        return None
    usuario = await session.scalar(
        select(User)
        .where(User.id == dueno)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    fila = await session.scalar(
        select(OneTimeToken)
        .where(OneTimeToken.token_hash == token_hash)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if usuario is None or fila is None:
        return None
    return fila, usuario


async def reset(session: AsyncSession, token: str, new_password: str) -> None:
    """US-048 (blueprint S2-B4, decisión 7; H-3, S2-D37, S2-D40, L-13): token con `FOR
    UPDATE` (`InvalidToken`), política con `field="new_password"`, hash nuevo y token usado
    bajo `actor_scope(token.user_id)`; con `reset`, `revoke_all` y `SessionsRevoked`;
    `PasswordChanged(via=<propósito>, via_link_issued_by=<created_by del token>)`. No inicia
    sesión."""
    encontrado = await _locked_one_time_token(session, token)
    now = current_clock().now_utc()
    if encontrado is None or not rules.is_one_time_token_usable(*encontrado, now):
        logger.info("enlace de un solo uso rechazado")
        raise InvalidToken()
    fila, usuario = encontrado
    rules.validate_password_policy(new_password, field="new_password")
    nuevo_hash = await anyio.to_thread.run_sync(hash_password, new_password)
    via: Literal["activate", "reset"] = "activate" if fila.purpose == "activate" else "reset"
    with actor_scope(usuario.id):
        fila.used_at = now
        usuario.password_hash = nuevo_hash
        usuario.must_change_password = False
        usuario.failed_login_count = 0
        await session.flush()
        # Revisión S2-B4 (MEDIUM-1): ningún otro enlace abierto sobrevive a la contraseña nueva.
        await tokens.close_open_one_time_tokens(session, usuario.id, now=now)
        if via == "reset":
            revocadas = await tokens.revoke_all(session, usuario.id, now=now)
            if revocadas:
                await events.emit(
                    SessionsRevoked(
                        user_id=usuario.id,
                        by=usuario.id,
                        revoked=revocadas,
                        reason="password_reset",
                    ),
                    session,
                )
        await events.emit(
            PasswordChanged(
                user_id=usuario.id, by=usuario.id, via=via, via_link_issued_by=fila.created_by
            ),
            session,
        )
        await session.flush()
    logger.info("contraseña fijada por enlace", extra={"user_id": str(usuario.id), "via": via})


async def forgot(email: str, *, policy: AuthPolicy) -> None:
    """US-048 (S2-D36, H-2; S5-D38): solo valida y cuenta. Normaliza, cuenta el intento en
    `FORGOT_ACCOUNT_BUCKET` y espera el piso `policy.min_duration_ms` con el sleeper de
    `configure_sleeper` (S2-D39), exista o no la cuenta; devuelve siempre igual.

    No consulta la base ni envía nada: la búsqueda de la cuenta y el correo del enlace corren en
    segundo plano con `forgot_deliver` (S5-B9), así que el tiempo de respuesta no depende de si el
    correo existe. LOW L3: la firma no lleva `session` ni `ip` (eran parámetros muertos)."""
    inicio = time.monotonic()
    await ratelimit.enforce(
        FORGOT_ACCOUNT_BUCKET,
        normalize_login_email(email),
        limit=FORGOT_ACCOUNT_LIMIT,
        window_s=FORGOT_ACCOUNT_WINDOW_S,
    )
    logger.info("forgot recibido; la entrega sigue en segundo plano (forgot_deliver)")
    await wait_floor(inicio, policy)


# Entrega de `forgot` en segundo plano (S5-B9; D91, S5-D237) -------------------------------------

FORGOT_DELIVER_CONCURRENCY: Final = 4


FORGOT_DELIVER_QUEUE: Final = 32


@dataclass
class _Cola:
    """Semáforo y contador de espera atados a un bucle de eventos."""

    semaforo: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(FORGOT_DELIVER_CONCURRENCY)
    )
    esperando: int = 0


_COLAS: Final[weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _Cola]] = (
    weakref.WeakKeyDictionary()
)


def _cola_del_bucle() -> _Cola:
    """La cola del bucle vigente, creada de forma perezosa (uno por proceso del api)."""
    bucle = asyncio.get_running_loop()
    cola = _COLAS.get(bucle)
    if cola is None:
        cola = _COLAS[bucle] = _Cola()
    return cola


async def _issue_reset_mail(
    email: str, session_factory: Callable[[], Any], settings: Settings
) -> tuple[str, str, str] | None:
    """(destino, enlace, remitente) o `None`. Sesión propia, cerrada al volver (el correo sale
    fuera de la transacción). Sin canal (S5-D235) o con una cuenta no elegible (S5-D236:
    inexistente, inactiva, bloqueada o `pending_activation`) no consulta ni emite nada de más."""
    async with session_factory() as sesion, sesion.begin():
        remitente = await mail_texts.email_sender_name(sesion, settings)
        if remitente is None:
            return None
        usuario = await sesion.scalar(
            select(User)
            .where(User.email == normalize_login_email(email), User.deleted_at.is_(None))
            .with_for_update()
        )
        if usuario is None or rules.user_status(usuario) != "active":
            return None
        with actor_scope(usuario.id):
            claro, _ = await tokens.issue_one_time_token(
                sesion, usuario.id, "reset", now=current_clock().now_utc()
            )
        logger.info("enlace de recuperación emitido", extra={"user_id": str(usuario.id)})
        return usuario.email, rules.activation_url(settings.FRONT_BASE_URL, claro), remitente


async def _deliver_one(email: str, session_factory: Callable[[], Any], settings: Settings) -> None:
    emitido = await _issue_reset_mail(email, session_factory, settings)
    if emitido is None:
        return
    destino, url, remitente = emitido
    mensaje = mail_texts.account_message("reset", to=destino, url=url, sender=remitente)
    await send_mail(settings, mensaje)


async def forgot_deliver(
    email: str, *, session_factory: Callable[[], Any], settings: Settings
) -> None:
    """US-131 (D38, D91, S5-D234..D237, M-7d/e): búsqueda, token y correo DESPUÉS de la
    respuesta de `POST /auth/forgot`, en una sesión propia. Sin SMTP no toca la base. A lo más 4
    a la vez y 32 en espera: lo que no cabe se descarta con una línea fija. Nunca propaga: un
    fallo deja solo el tipo de la excepción en el log (ni correo ni enlace)."""
    if not mail_configured(settings):
        return
    cola = _cola_del_bucle()
    if cola.semaforo.locked() and cola.esperando >= FORGOT_DELIVER_QUEUE:
        logger.warning("forgot_deliver: cola llena, descartado")
        return
    cola.esperando += 1
    try:
        await cola.semaforo.acquire()
    finally:
        cola.esperando -= 1
    try:
        await _deliver_one(email, session_factory, settings)
    except Exception as error:
        logger.warning("forgot_deliver: falló", extra={"error_type": type(error).__name__})
    finally:
        cola.semaforo.release()


# Emitir y reenviar ---------------------------------------------------------------------------


def _ensure_link_eligible(usuario: User) -> None:
    if rules.user_status(usuario) not in _LINK_ELIGIBLE:
        raise UserNotEligible()


async def _issue_link_for(
    session: AsyncSession, usuario: User, *, by: UUID, front_base_url: str
) -> IssuedLinkOut:
    """Emite el enlace de `link_purpose_for` atribuido a `by` (`created_by` y auditoría)."""
    proposito = rules.link_purpose_for(usuario)
    with actor_scope(by):
        claro, fila = await tokens.issue_one_time_token(
            session, usuario.id, proposito, now=current_clock().now_utc()
        )
    logger.info(
        "enlace emitido",
        extra={"user_id": str(usuario.id), "purpose": proposito, "by": str(by)},
    )
    return IssuedLinkOut(
        url=rules.activation_url(front_base_url, claro),
        purpose=proposito,
        expires_at=fila.expires_at,
    )


async def issue_link(
    session: AsyncSession, user_id: UUID, *, by: UUID, front_base_url: str
) -> IssuedLinkOut:
    """El enlace de `link_purpose_for(user)` sin la regla L-13 (solo `cli issue-reset-link`):
    `get_alive_or_404(include_deleted=True)`; bloqueado o borrado dan `UserNotEligible`."""
    usuario = await tokens.get_alive_or_404(session, user_id, include_deleted=True, for_update=True)
    _ensure_link_eligible(usuario)
    return await _issue_link_for(session, usuario, by=by, front_base_url=front_base_url)


async def resend_link(
    session: AsyncSession,
    user_id: UUID,
    *,
    by: UUID,
    front_base_url: str,
    settings: Settings | None = None,
) -> IssuedLinkOut:
    """US-052 (blueprint S2-B4; L-13): `UserNotFound` para el técnico o un id inexistente;
    `UserNotEligible` si está bloqueado o borrado, si es la cuenta de `by` o si es otro admin
    activo con contraseña; si no, `issue_one_time_token` del propósito de `link_purpose_for`
    y `IssuedLinkOut` con `url = <front_base_url sin barra final>/restablecer/<token>`."""
    usuario = await tokens.get_alive_or_404(session, user_id, include_deleted=True, for_update=True)
    _ensure_link_eligible(usuario)
    if usuario.id == by or is_active_admin(usuario):
        # L-13: un admin no recupera su cuenta ni la de otro admin activo por aquí.
        logger.info("reenvío rechazado por L-13", extra={"user_id": str(usuario.id)})
        raise UserNotEligible()
    # S5-D239: la configuración se lee ANTES del token y sin `except`: un error de base se propaga.
    remitente = await mail_texts.email_sender_name(session, settings) if settings else None
    emitido = await _issue_link_for(session, usuario, by=by, front_base_url=front_base_url)
    enviado = await _send_link_mail(settings, remitente, to=usuario.email, issued=emitido)
    return emitido.model_copy(update={"email_sent": enviado})


async def _send_link_mail(
    settings: Settings | None, remitente: str | None, *, to: str, issued: IssuedLinkOut
) -> bool:
    """S5-B9 (D37): el correo del enlace reenviado; falso sin `settings`, SMTP o canal
    (`remitente` nulo) o si el envío falla o pasa de `AUTH_MAIL_TIMEOUT_S` (S5-D238). Solo el
    envío va en el `except` (S5-D239) y registra solo el tipo (M-7d)."""
    if settings is None or remitente is None:
        return False
    mensaje = mail_texts.account_message(issued.purpose, to=to, url=issued.url, sender=remitente)
    try:
        async with asyncio.timeout(AUTH_MAIL_TIMEOUT_S):
            return (await send_mail(settings, mensaje)).ok
    except Exception as error:
        logger.warning("correo del enlace no enviado", extra={"error_type": type(error).__name__})
        return False
