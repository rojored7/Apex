"""Reglas puras del login (S2-B2; S2-D1, S2-D40/M-7, S2-D10/H-4). Sin base."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.context import SYSTEM_USER_ID
from app.modules.auth.models import User
from app.modules.auth.rules import (
    account_may_authenticate,
    is_active_admin,
    should_auto_lock,
    user_status,
)

T0 = datetime(2026, 10, 21, 15, 0, 0, tzinfo=UTC)


def _user(**cambios: object) -> User:
    valores: dict[str, object] = {
        "id": uuid4(),
        "email": "ana@test.apex",
        "password_hash": "$argon2id$x",
        "role": "coach",
        "member_id": None,
        "is_active": True,
        "locked_at": None,
        "deleted_at": None,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    return User(**valores)


# Una fila por estado de S2-D1 más el usuario técnico (N-15).
ESTADOS: dict[str, tuple[dict[str, object], str, bool]] = {
    "activo": ({}, "active", True),
    "inactivo": ({"is_active": False}, "inactive", False),
    "bloqueado": ({"locked_at": T0}, "locked", False),
    "pendiente": ({"password_hash": None}, "pending_activation", False),
    "borrado": ({"deleted_at": T0}, "deleted", False),
    "tecnico": (
        {
            "id": SYSTEM_USER_ID,
            "email": "system@apex.local",
            "role": "admin",
            "password_hash": None,
            "is_active": False,
        },
        "inactive",
        False,
    ),
}


@pytest.mark.parametrize("caso", list(ESTADOS))
def test_user_status_y_account_may_authenticate_por_estado(caso: str) -> None:
    cambios, estado, puede = ESTADOS[caso]
    usuario = _user(**cambios)
    assert user_status(usuario) == estado
    assert account_may_authenticate(usuario) is puede


def test_el_tecnico_nunca_autentica_aunque_parezca_activo() -> None:
    """N-15: `SYSTEM_USER_ID` queda fuera por id, no solo por `is_active = false`."""
    tecnico = _user(id=SYSTEM_USER_ID, role="admin", is_active=True)
    assert account_may_authenticate(tecnico) is False


@pytest.mark.parametrize(
    ("cambios", "esperado"),
    [
        ({"deleted_at": T0, "locked_at": T0, "is_active": False}, "deleted"),
        ({"locked_at": T0, "is_active": False, "password_hash": None}, "locked"),
        ({"is_active": False, "password_hash": None}, "inactive"),
        ({"password_hash": None}, "pending_activation"),
    ],
    ids=["borrado-manda", "bloqueado-sobre-inactivo", "inactivo-sobre-pendiente", "pendiente"],
)
def test_orden_de_precedencia_del_estado(cambios: dict[str, object], esperado: str) -> None:
    """S2-D1: `deleted > locked > inactive > pending_activation > active`."""
    assert user_status(_user(**cambios)) == esperado


def test_is_active_admin() -> None:
    assert is_active_admin(_user(role="admin")) is True
    assert is_active_admin(_user(role="coach")) is False
    assert is_active_admin(_user(role="admin", locked_at=T0)) is False
    assert is_active_admin(_user(role="admin", password_hash=None)) is False
    assert is_active_admin(_user(role="admin", is_active=False)) is False
    assert is_active_admin(_user(id=SYSTEM_USER_ID, role="admin")) is False


@pytest.mark.parametrize(
    ("fallos", "ultimo_admin", "bloquea"),
    [
        (0, False, False),
        (19, False, False),
        (20, False, True),
        (21, False, True),
        (20, True, False),
        (500, True, False),
    ],
)
def test_should_auto_lock_umbral_y_excepcion_del_ultimo_admin(
    fallos: int, ultimo_admin: bool, bloquea: bool
) -> None:
    """S2-D10 y H-4: bloqueo a los 20 fallos consecutivos; el último admin activo nunca."""
    assert should_auto_lock(fallos, 20, is_last_admin=ultimo_admin) is bloquea
