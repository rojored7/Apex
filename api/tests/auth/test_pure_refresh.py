"""Reglas puras del refresh (S2-B2; N-13, M-2 gracia de reuso, L-4 tope absoluto, M-7).

Valores calculados a mano con `T0 = 2026-10-21T15:00:00Z`, gracia de 10 s, TTL de 7 días y
tope absoluto de 30 días por familia (`family_started_at`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.cli import export_settings
from app.core.context import SYSTEM_USER_ID
from app.modules.auth.cookies import policy_from
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.rules import AuthPolicy, is_refresh_usable, is_reuse

T0 = datetime(2026, 10, 21, 15, 0, 0, tzinfo=UTC)
GRACIA = timedelta(seconds=10)
TOPE = timedelta(days=30)


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


def _token(**cambios: object) -> RefreshToken:
    valores: dict[str, object] = {
        "id": uuid4(),
        "user_id": uuid4(),
        "token_hash": "0" * 64,
        "expires_at": T0 + timedelta(days=7),
        "revoked_at": None,
        "replaced_by_id": None,
        "family_started_at": T0,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    return RefreshToken(**valores)


def test_un_refresh_vigente_de_una_cuenta_activa_es_usable() -> None:
    assert is_refresh_usable(_token(), _user(), T0 + timedelta(hours=1), absolute_ttl=TOPE)


@pytest.mark.parametrize(
    ("cambios", "ahora"),
    [
        ({"expires_at": T0 + timedelta(hours=1)}, T0 + timedelta(hours=1)),  # vence justo ahora
        ({"expires_at": T0}, T0 + timedelta(seconds=1)),
        ({"revoked_at": T0}, T0 + timedelta(seconds=1)),
        ({"family_started_at": T0 - TOPE}, T0),  # cumple 30 días justo ahora
        ({"family_started_at": T0 - TOPE - timedelta(days=1)}, T0),
    ],
    ids=["vence-ahora", "vencido", "revocado", "familia-30-dias", "familia-31-dias"],
)
def test_no_es_usable_vencido_revocado_o_familia_de_30_dias(
    cambios: dict[str, object], ahora: datetime
) -> None:
    assert is_refresh_usable(_token(**cambios), _user(), ahora, absolute_ttl=TOPE) is False


def test_la_familia_un_segundo_antes_del_tope_sigue_usable() -> None:
    token = _token(family_started_at=T0 - TOPE + timedelta(seconds=1))
    assert is_refresh_usable(token, _user(), T0, absolute_ttl=TOPE) is True


@pytest.mark.parametrize(
    "cambios",
    [
        {"locked_at": T0},
        {"is_active": False},
        {"password_hash": None},
        {"deleted_at": T0},
        {"id": SYSTEM_USER_ID, "role": "admin"},
    ],
    ids=["bloqueado", "inactivo", "pendiente", "borrado", "tecnico"],
)
def test_no_es_usable_si_la_cuenta_ya_no_puede_autenticarse(cambios: dict[str, object]) -> None:
    """M-7: el mismo predicado que el login (`account_may_authenticate`)."""
    assert is_refresh_usable(_token(), _user(**cambios), T0, absolute_ttl=TOPE) is False


@pytest.mark.parametrize(
    ("segundos", "es_reuso"),
    [(0, False), (5, False), (9.999, False), (10, True), (11, True), (3600, True)],
)
def test_is_reuse_con_gracia_de_10_segundos(segundos: float, es_reuso: bool) -> None:
    """M-2: un rotado usado antes de 10 s es concurrencia benigna; desde 10 s, reuso real."""
    rotado = _token(revoked_at=T0, replaced_by_id=uuid4())
    assert is_reuse(rotado, T0 + timedelta(seconds=segundos), GRACIA) is es_reuso


def test_un_refresh_cerrado_por_logout_no_es_reuso() -> None:
    """Sin `replaced_by_id` (logout) nunca es reuso: no revoca la familia (blueprint 7.1)."""
    cerrado = _token(revoked_at=T0, replaced_by_id=None)
    assert is_reuse(cerrado, T0 + timedelta(hours=1), GRACIA) is False
    assert is_reuse(_token(), T0 + timedelta(hours=1), GRACIA) is False


def test_policy_from_settings_por_defecto() -> None:
    politica = policy_from(export_settings())
    assert politica == AuthPolicy(
        access_ttl_s=900,
        refresh_ttl=timedelta(days=7),
        refresh_absolute_ttl=timedelta(days=30),
        reuse_grace=timedelta(seconds=10),
        account_limit=10,
        account_window_s=900,
        account_global_limit=100,
        account_global_window_s=3600,
        lock_after=20,
        min_duration_ms=export_settings().LOGIN_MIN_DURATION_MS,
    )


def test_policy_from_sigue_a_settings() -> None:
    ajustada = export_settings().model_copy(
        update={
            "REFRESH_TOKEN_TTL_DAYS": 3,
            "REFRESH_ABSOLUTE_TTL_DAYS": 14,
            "REFRESH_REUSE_GRACE_S": 4,
            "LOGIN_ACCOUNT_LIMIT": 7,
            "LOGIN_LOCK_AFTER": 9,
            "ACCESS_TOKEN_TTL_S": 600,
            "LOGIN_MIN_DURATION_MS": 250,
        }
    )
    politica = policy_from(ajustada)
    assert politica.refresh_ttl == timedelta(days=3)
    assert politica.refresh_absolute_ttl == timedelta(days=14)
    assert politica.reuse_grace == timedelta(seconds=4)
    assert politica.account_limit == 7 and politica.lock_after == 9
    assert politica.access_ttl_s == 600 and politica.min_duration_ms == 250
