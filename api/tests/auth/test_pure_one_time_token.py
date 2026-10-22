"""`rules.is_one_time_token_usable` y `rules.link_purpose_for`, puras (S2-B4; US-048, US-052;
S2-D40, blueprint 7.2).

`is_one_time_token_usable(token, user, now)`: sin usar, `expires_at > now` (exactamente
`expires_at == now` ya no sirve) y una cuenta que puede autenticarse según
`account_may_authenticate` (S2-D40), salvo la exigencia de hash cuando el propósito es
`activate`: un pendiente de activación solo es usable con `activate`. Bloqueado, borrado,
inactivo o el usuario técnico nunca son usables.

`link_purpose_for(user)`: `activate` si la cuenta no tiene hash; si no, `reset`.
Objetos `User` y `OneTimeToken` en memoria, sin base.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from app.core.context import SYSTEM_USER_ID
from app.modules.auth.models import OneTimeToken, User
from app.modules.auth.rules import is_one_time_token_usable, link_purpose_for

AHORA = datetime(2026, 10, 21, 15, 0, 0, tzinfo=UTC)
HASH = "$argon2id$v=19$m=8,t=1,p=1$ficticio"


def _usuario(**cambios: Any) -> User:
    valores: dict[str, Any] = {
        "id": uuid4(),
        "email": "u@test.apex",
        "password_hash": HASH,
        "role": "coach",
        "member_id": None,
        "is_active": True,
        "locked_at": None,
        "deleted_at": None,
        "must_change_password": False,
        "failed_login_count": 0,
        "tokens_valid_after": None,
    }
    valores.update(cambios)
    return User(**valores)


def _token(purpose: str = "reset", **cambios: Any) -> OneTimeToken:
    valores: dict[str, Any] = {
        "id": uuid4(),
        "user_id": uuid4(),
        "token_hash": "0" * 64,
        "purpose": purpose,
        "expires_at": AHORA + timedelta(hours=1),
        "used_at": None,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    return OneTimeToken(**valores)


# Límite exacto de `expires_at` -------------------------------------------------------------


@pytest.mark.parametrize("purpose", ["activate", "reset"])
def test_expires_at_igual_a_ahora_ya_no_es_usable(purpose: str) -> None:
    usuario = _usuario(password_hash=None) if purpose == "activate" else _usuario()
    token = _token(purpose, expires_at=AHORA)
    assert is_one_time_token_usable(token, usuario, AHORA) is False


@pytest.mark.parametrize("purpose", ["activate", "reset"])
def test_expires_at_un_segundo_despues_de_ahora_es_usable(purpose: str) -> None:
    usuario = _usuario(password_hash=None) if purpose == "activate" else _usuario()
    token = _token(purpose, expires_at=AHORA + timedelta(seconds=1))
    assert is_one_time_token_usable(token, usuario, AHORA) is True


def test_un_microsegundo_antes_de_vencer_sigue_usable_y_uno_despues_no() -> None:
    usuario = _usuario()
    token = _token("reset", expires_at=AHORA)
    assert is_one_time_token_usable(token, usuario, AHORA - timedelta(microseconds=1)) is True
    assert is_one_time_token_usable(token, usuario, AHORA + timedelta(microseconds=1)) is False


# Uso previo ------------------------------------------------------------------------------


@pytest.mark.parametrize("purpose", ["activate", "reset"])
def test_un_token_usado_no_es_usable_aunque_no_haya_vencido(purpose: str) -> None:
    usuario = _usuario(password_hash=None) if purpose == "activate" else _usuario()
    token = _token(purpose, used_at=AHORA - timedelta(minutes=1))
    assert is_one_time_token_usable(token, usuario, AHORA) is False


# Pendiente de activación: solo con `activate` (S2-D40) --------------------------------------


def test_un_pendiente_sin_hash_es_usable_con_activate() -> None:
    pendiente = _usuario(password_hash=None)
    assert is_one_time_token_usable(_token("activate"), pendiente, AHORA) is True


def test_un_pendiente_sin_hash_no_es_usable_con_reset() -> None:
    pendiente = _usuario(password_hash=None)
    assert is_one_time_token_usable(_token("reset"), pendiente, AHORA) is False


def test_un_activo_con_hash_es_usable_con_reset() -> None:
    assert is_one_time_token_usable(_token("reset"), _usuario(), AHORA) is True


def test_un_activo_con_hash_tambien_puede_usar_un_activate_vigente() -> None:
    """S2-D40 solo quita la exigencia de hash para `activate`; no la convierte en "sin hash".
    Un activate vigente de una cuenta ya activa (p. ej. reenviado antes de activar) sigue
    cumpliendo `account_may_authenticate`."""
    assert is_one_time_token_usable(_token("activate"), _usuario(), AHORA) is True


# Cuentas que no pueden autenticarse ------------------------------------------------------


@pytest.mark.parametrize("purpose", ["activate", "reset"])
@pytest.mark.parametrize(
    "cambios",
    [
        {"locked_at": AHORA - timedelta(days=1)},
        {"deleted_at": AHORA - timedelta(days=1)},
        {"is_active": False},
        {"id": SYSTEM_USER_ID, "is_active": False},
    ],
    ids=["bloqueado", "borrado", "inactivo", "tecnico"],
)
def test_bloqueado_borrado_inactivo_o_tecnico_no_es_usable(
    purpose: str, cambios: dict[str, Any]
) -> None:
    if purpose == "activate":
        cambios = {"password_hash": None, **cambios}
    usuario = _usuario(**cambios)
    assert is_one_time_token_usable(_token(purpose), usuario, AHORA) is False


@pytest.mark.parametrize(
    "cambios",
    [
        {"locked_at": AHORA - timedelta(days=1)},
        {"deleted_at": AHORA - timedelta(days=1)},
        {"is_active": False},
    ],
    ids=["bloqueado", "borrado", "inactivo"],
)
def test_un_pendiente_bloqueado_borrado_o_inactivo_tampoco_activa(cambios: dict[str, Any]) -> None:
    usuario = _usuario(password_hash=None, **cambios)
    assert is_one_time_token_usable(_token("activate"), usuario, AHORA) is False


def test_un_socio_activo_tambien_puede_restablecer() -> None:
    socio = _usuario(role="member", member_id=uuid4())
    assert is_one_time_token_usable(_token("reset"), socio, AHORA) is True


# link_purpose_for ------------------------------------------------------------------------


def test_sin_hash_el_enlace_es_de_activacion() -> None:
    assert link_purpose_for(_usuario(password_hash=None)) == "activate"


def test_con_hash_el_enlace_es_de_restablecimiento() -> None:
    assert link_purpose_for(_usuario()) == "reset"


def test_el_proposito_solo_depende_del_hash() -> None:
    """Bloqueado o borrado no cambian el propósito: la elegibilidad la decide `resend_link`."""
    assert link_purpose_for(_usuario(password_hash=None, locked_at=AHORA)) == "activate"
    assert link_purpose_for(_usuario(deleted_at=AHORA)) == "reset"
