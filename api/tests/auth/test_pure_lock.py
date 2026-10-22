"""`auth.rules.lock_precondition` y los errores de S2-B5 (US-050; blueprint S2-B5).

Orden fijo de errores: `CannotLockSelf` (el admin se bloquea a sí mismo), `AlreadyLocked`
(`locked_at` lleno) y `LastAdmin` (el objetivo es el último admin activo). Los cuatro errores
nuevos son 409 con su código estable y un mensaje en español sin datos de la cuenta.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.core.errors import DomainError
from app.modules.auth.exceptions import AlreadyLocked, CannotLockSelf, LastAdmin, NotLocked
from app.modules.auth.models import User
from app.modules.auth.rules import lock_precondition

OBJETIVO = UUID("00000000-0000-0000-0000-0000000000b1")
OTRO = UUID("00000000-0000-0000-0000-0000000000b2")
BLOQUEO = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)


def _usuario(*, locked: bool = False, role: str = "admin") -> User:
    return User(
        id=OBJETIVO,
        email="objetivo@test.apex",
        password_hash="$argon2id$x",  # noqa: S106 - marcador, no una contraseña
        role=role,
        member_id=None,
        is_active=True,
        locked_at=BLOQUEO if locked else None,
        deleted_at=None,
    )


@pytest.mark.parametrize(
    ("por", "bloqueado", "ultimo", "esperado"),
    [
        (OBJETIVO, True, True, CannotLockSelf),
        (OBJETIVO, False, False, CannotLockSelf),
        (OTRO, True, True, AlreadyLocked),
        (OTRO, True, False, AlreadyLocked),
        (OTRO, False, True, LastAdmin),
    ],
)
def test_orden_fijo_de_errores(
    por: UUID, bloqueado: bool, ultimo: bool, esperado: type[DomainError]
) -> None:
    with pytest.raises(esperado):
        lock_precondition(_usuario(locked=bloqueado), por, is_last_admin=ultimo)


@pytest.mark.parametrize("rol", ["admin", "coach", "member"])
def test_sin_impedimentos_no_lanza(rol: str) -> None:
    assert lock_precondition(_usuario(role=rol), OTRO, is_last_admin=False) is None


def test_no_modifica_al_usuario() -> None:
    usuario = _usuario()
    lock_precondition(usuario, OTRO, is_last_admin=False)
    assert usuario.locked_at is None


@pytest.mark.parametrize(
    ("tipo", "codigo"),
    [
        (LastAdmin, "last_admin"),
        (CannotLockSelf, "cannot_lock_self"),
        (AlreadyLocked, "already_locked"),
        (NotLocked, "not_locked"),
    ],
)
def test_los_errores_nuevos_son_409_con_codigo_estable(
    tipo: type[DomainError], codigo: str
) -> None:
    error = tipo()
    assert (error.status, error.code) == (409, codigo)
    assert error.message
    assert "@" not in error.message
    assert error.field is None
