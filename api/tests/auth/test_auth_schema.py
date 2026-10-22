"""Restricciones de `auth.users` y usuario técnico tras `upgrade head` (US-041 T10)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.auth.models import User


def _user(**cambios: object) -> User:
    valores: dict[str, object] = {
        "email": "ana@apex.local",
        "password_hash": "$argon2id$x",
        "role": "coach",
        "member_id": None,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    return User(**valores)


async def _falla(session: AsyncSession, usuario: User) -> str:
    with pytest.raises((IntegrityError, DBAPIError)) as excinfo:
        async with session.begin_nested():
            session.add(usuario)
            await session.flush()
    return str(excinfo.value)


async def test_check_de_member_id_y_de_correo_normalizado(session: AsyncSession) -> None:
    with actor_scope(SYSTEM_USER_ID):
        assert "member_id_for_member" in await _falla(session, _user(role="member"))
        assert "email_normalized" in await _falla(session, _user(email="Ana@Apex.local"))
        assert "role" in await _falla(session, _user(role="root"))
        session.add(_user(role="member", member_id=uuid4()))
        await session.flush()


async def test_el_correo_se_puede_repetir_solo_si_el_anterior_esta_dado_de_baja(
    session: AsyncSession,
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        primero = _user()
        session.add(primero)
        await session.flush()
        assert "uq_users_email_alive" in await _falla(session, _user())
        primero.deleted_at = datetime(2026, 10, 21, tzinfo=UTC)
        await session.flush()
        session.add(_user())
        await session.flush()


async def test_el_usuario_tecnico_existe_inactivo_y_sin_contrasena(session: AsyncSession) -> None:
    tecnico = await session.get(User, SYSTEM_USER_ID)
    assert tecnico is not None
    assert tecnico.email == "system@apex.local" and tecnico.role == "admin"
    assert tecnico.is_active is False and tecnico.password_hash is None
    assert tecnico.created_by == SYSTEM_USER_ID
    tablas = (
        await session.scalars(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'auth' ORDER BY 1"
            )
        )
    ).all()
    assert list(tablas) == ["one_time_tokens", "refresh_tokens", "users"]
