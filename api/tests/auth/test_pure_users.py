"""Funciones puras de auth (US-041 T8)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.core.context import SYSTEM_USER_ID
from app.modules.auth.exceptions import AuthError
from app.modules.auth.models import User
from app.modules.auth.service import (
    is_active_admin,
    normalize_login_email,
    user_status,
    validate_password_policy,
    validate_user_role,
)


def test_validate_user_role() -> None:
    with pytest.raises(AuthError) as sin_socio:
        validate_user_role("member", None)
    assert sin_socio.value.code == "member_id_required"
    validate_user_role("coach", None)
    validate_user_role("admin", None)
    with pytest.raises(AuthError) as con_socio:
        validate_user_role("coach", uuid4())
    assert con_socio.value.code == "member_id_not_allowed"
    validate_user_role("member", uuid4())


def test_normalize_login_email() -> None:
    assert normalize_login_email(" Dueno@Apex.co ") == "dueno@apex.co"


def test_validate_password_policy_traduce_a_auth_error() -> None:
    with pytest.raises(AuthError) as corta:
        validate_password_policy("once-letras")
    assert corta.value.code == "weak_password" and corta.value.field == "password"
    with pytest.raises(AuthError) as comun:
        validate_password_policy("Contraseña123")
    assert comun.value.code == "weak_password"
    validate_password_policy("casa-azul-19")


def _user(**cambios: object) -> User:
    valores: dict[str, object] = {
        "email": "a@apex.local",
        "password_hash": "$argon2id$x",
        "role": "admin",
        "member_id": None,
        "is_active": True,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    return User(**valores)


def test_is_active_admin_y_status() -> None:
    tecnico = _user(
        id=SYSTEM_USER_ID, email="system@apex.local", password_hash=None, is_active=False
    )
    assert is_active_admin(tecnico) is False and user_status(tecnico) == "inactive"
    bloqueado = _user(locked_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert is_active_admin(bloqueado) is False and user_status(bloqueado) == "locked"
    baja = _user(deleted_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert is_active_admin(baja) is False and user_status(baja) == "deleted"
    assert is_active_admin(_user(role="coach")) is False
    assert is_active_admin(_user(password_hash=None)) is False
    activo = _user()
    assert is_active_admin(activo) is True and user_status(activo) == "active"
    assert isinstance(activo.id, UUID)
