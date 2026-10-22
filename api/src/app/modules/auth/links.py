"""Enlaces de un solo uso: activación, recuperación y reenvío (S2-B4: US-048, US-052; H-2,
H-3, L-13, S2-D36, S2-D37, S2-D40). Privado del módulo (revisión Python H1); se usa a través de
`auth.service`.

- `reset`: token con `FOR UPDATE` (orden usuario → token), política con `field="new_password"`,
  hash nuevo, cierre de los demás enlaces abiertos y, si es `reset`, `revoke_all` y
  `SessionsRevoked`; `PasswordChanged(via=<propósito>, via_link_issued_by=<created_by>)`.
- `forgot` (H-2): no lee ni escribe la base; cuenta el intento en `FORGOT_ACCOUNT_BUCKET` y
  espera el piso de `sessions.wait_floor` exista o no la cuenta.
- `resend_link` (L-13) e `issue_link` (el mismo enlace sin L-13, solo para
  `cli issue-reset-link`).
"""

from __future__ import annotations

import logging
import time
from typing import Final, Literal
from uuid import UUID

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events, ratelimit
from app.core.clock import current_clock
from app.core.context import actor_scope
from app.core.security import (
    TokenInvalid,
    hash_opaque_token,
    hash_password,
)
from app.modules.auth import rules, tokens
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
    """US-048 en v0.1 (S2-D36, H-2): no escribe nada. Normaliza, cuenta el intento en
    `FORGOT_ACCOUNT_BUCKET`, espera el piso `policy.min_duration_ms` con el sleeper de
    `configure_sleeper` (S2-D39) exista o no la cuenta y deja un log sin el correo.

    Ni siquiera consulta la base: sin emisor (US-131) no hay nada que hacer con la cuenta, y no
    leerla quita de raíz cualquier diferencia de tiempo entre un correo existente y uno que no.
    LOW L3 de la revisión Python: la firma ya no lleva `session` ni `ip` (eran parámetros
    muertos); el emisor real los agregará cuando exista."""
    inicio = time.monotonic()
    await ratelimit.enforce(
        FORGOT_ACCOUNT_BUCKET,
        normalize_login_email(email),
        limit=FORGOT_ACCOUNT_LIMIT,
        window_s=FORGOT_ACCOUNT_WINDOW_S,
    )
    logger.info("forgot recibido; v0.1 no envía enlaces (US-131)")
    await wait_floor(inicio, policy)


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
    session: AsyncSession, user_id: UUID, *, by: UUID, front_base_url: str
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
    return await _issue_link_for(session, usuario, by=by, front_base_url=front_base_url)
