"""`auth.service.logout(session, token)` por la cookie (S2-B2; US-044; H-1 / S2-D35).

Revoca solo la fila de ese refresh (sin `replaced_by_id`, así un refresh posterior no es
reuso); sin token, con un token desconocido o ya revocado no hace nada.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security import hash_opaque_token
from app.modules.auth import service
from app.modules.auth.models import RefreshToken
from tests.auth._sesion import IP_A, politica
from tests.conftest import CLAVE_PRUEBA, T0, CrearUsuario


async def _login(session: AsyncSession, email: str) -> str:
    resultado = await service.login(
        session, email, CLAVE_PRUEBA, ip=IP_A, user_agent="pytest", policy=politica()
    )
    await session.commit()
    return resultado.refresh_token


async def _fila(session: AsyncSession, token: str) -> RefreshToken:
    fila = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_opaque_token(token))
        .execution_options(populate_existing=True)
    )
    assert fila is not None
    return fila


async def _vivas(session: AsyncSession, user_id: UUID) -> int:
    return int(
        await session.scalar(
            text(
                "SELECT count(*) FROM auth.refresh_tokens WHERE user_id = :u AND revoked_at IS NULL"
            ),
            {"u": user_id},
        )
        or 0
    )


async def test_logout_revoca_solo_la_sesion_de_esa_cookie(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    esta = await _login(session, coach.email)
    otra = await _login(session, coach.email)
    reloj.advance(minutes=3)
    await service.logout(session, esta)
    await session.commit()
    cerrada = await _fila(session, esta)
    assert cerrada.revoked_at == T0 + timedelta(minutes=3)
    assert cerrada.replaced_by_id is None
    assert (await _fila(session, otra)).revoked_at is None
    assert await _vivas(session, coach.id) == 1


async def test_sin_token_o_con_uno_desconocido_no_hace_nada(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    await _login(session, coach.email)
    await service.logout(session, None)
    await service.logout(session, "no-existe-este-token")
    await service.logout(session, "ñandú")  # no ASCII: inválido, sin error
    await session.commit()
    assert await _vivas(session, coach.id) == 1


async def test_un_logout_repetido_no_mueve_la_fecha_de_revocacion(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    token = await _login(session, coach.email)
    await service.logout(session, token)
    await session.commit()
    reloj.advance(minutes=10)
    await service.logout(session, token)
    await session.commit()
    assert (await _fila(session, token)).revoked_at == T0


async def test_logout_no_toca_tokens_valid_after(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """Logout cierra una sesión; no es `revoke_all` (H-3 solo para cierres masivos)."""
    coach = await usuario_real("coach")
    token = await _login(session, coach.email)
    await service.logout(session, token)
    await session.commit()
    corte = await session.scalar(
        text("SELECT tokens_valid_after FROM auth.users WHERE id = :id"), {"id": coach.id}
    )
    assert corte is None
