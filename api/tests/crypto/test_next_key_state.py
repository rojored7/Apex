"""`next_key_state`: la máquina de estados de una llave al rotar y al retirar (S4B-B3b; S4B-D39).

Pura: sin base. `active -> decrypt_only` al rotar; `decrypt_only -> retired` solo por retiro;
todo lo demás es `InvalidTransition` (el trigger de `crypto_keys` admite también
`active -> retired`, pero para `encrypt` el servicio nunca debe pedirlo).
"""

from __future__ import annotations

import pytest

from app.core.crypto.service import InvalidTransition, next_key_state


@pytest.mark.parametrize("purpose", ["encrypt", "index"])
def test_al_rotar_la_activa_pasa_a_decrypt_only(purpose: str) -> None:
    assert next_key_state("active", "rotate", purpose) == "decrypt_only"


@pytest.mark.parametrize("purpose", ["encrypt", "index"])
def test_el_retiro_pasa_decrypt_only_a_retired(purpose: str) -> None:
    assert next_key_state("decrypt_only", "retire", purpose) == "retired"


@pytest.mark.parametrize("evento", ["rotate", "retire"])
def test_una_llave_retired_no_va_a_ningun_estado(evento: str) -> None:
    with pytest.raises(InvalidTransition):
        next_key_state("retired", evento, "encrypt")  # type: ignore[arg-type]


def test_decrypt_only_no_vuelve_a_active_al_rotar() -> None:
    with pytest.raises(InvalidTransition):
        next_key_state("decrypt_only", "rotate", "encrypt")


def test_active_no_pasa_a_retired_para_encrypt() -> None:
    """Retirar una llave que aún cifra dejaría ilegibles los datos nuevos."""
    with pytest.raises(InvalidTransition):
        next_key_state("active", "retire", "encrypt")


def test_invalid_transition_es_una_excepcion_propia() -> None:
    assert issubclass(InvalidTransition, Exception)
    assert not issubclass(InvalidTransition, ValueError)
