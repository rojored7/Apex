"""`auth.rules.validate_password_policy` (S2-B3; US-046; N-10, L-5 del Sprint 1, S2-D30).

La política de `core.security` (12 a 128 caracteres, fuera de `common_passwords.txt`) traducida
a `AuthError` 422 `weak_password` con el `field` que pide quien llama: `password` por defecto,
`new_password` en el cambio y en el restablecimiento. Con `current_hash`, la nueva debe ser
distinta de la actual. El mensaje nunca repite la contraseña.
"""

from __future__ import annotations

import pytest

from app.core.security import COMMON_PASSWORDS, PASSWORD_MAX_LENGTH, hash_password
from app.modules.auth.exceptions import AuthError
from app.modules.auth.rules import validate_password_policy
from tests.conftest import CLAVE_PRUEBA

ONCE = "Once-letra1"  # 11 caracteres
DOCE = "casa-azul-19"  # 12 caracteres, no común
# Una común de la lista con 12 o más caracteres: falla por `too_common`, no por `too_short`.
COMUN = sorted(c for c in COMMON_PASSWORDS if len(c) >= 12)[0]


def _rechazo(password: str, **kw: object) -> AuthError:
    with pytest.raises(AuthError) as excinfo:
        validate_password_policy(password, **kw)  # type: ignore[arg-type]
    return excinfo.value


@pytest.mark.parametrize("campo", ["password", "new_password"])
def test_once_caracteres_da_weak_password_con_el_campo_pedido(campo: str) -> None:
    error = _rechazo(ONCE, field=campo)
    assert error.code == "weak_password"
    assert error.status == 422
    assert error.field == campo
    assert ONCE not in error.message


def test_el_campo_por_defecto_es_password() -> None:
    assert _rechazo(ONCE).field == "password"


def test_doce_caracteres_no_comunes_pasan() -> None:
    assert len(DOCE) == 12
    assert validate_password_policy(DOCE) is None
    assert validate_password_policy(DOCE, field="new_password") is None


def test_128_caracteres_pasan_y_129_dan_weak_password() -> None:
    """L-5: el tope es 128 (`PASSWORD_MAX_LENGTH`); 129 se rechaza con el mismo código."""
    assert PASSWORD_MAX_LENGTH == 128
    larga = ("Ab1-" * 33)[:128]
    assert len(larga) == 128
    assert validate_password_policy(larga) is None
    error = _rechazo(larga + "x", field="new_password")
    assert error.code == "weak_password" and error.field == "new_password"
    assert larga not in error.message


@pytest.mark.parametrize("variante", [COMUN, COMUN.upper(), COMUN.capitalize()])
def test_una_comun_de_la_lista_da_weak_password_sin_importar_mayusculas(variante: str) -> None:
    error = _rechazo(variante, field="new_password")
    assert error.code == "weak_password" and error.field == "new_password"
    assert variante not in error.message


def test_la_lista_comun_es_la_de_core(argon2_rapido: None) -> None:
    """`cambiar-esto` (el literal del ejemplo de `.env.seed`, L-9) sigue en la lista."""
    assert "cambiar-esto" in COMMON_PASSWORDS
    assert _rechazo("Cambiar-Esto").code == "weak_password"


def test_igual_a_la_actual_da_weak_password_en_new_password(argon2_rapido: None) -> None:
    actual = hash_password(CLAVE_PRUEBA)
    error = _rechazo(CLAVE_PRUEBA, current_hash=actual, field="new_password")
    assert error.code == "weak_password"
    assert error.field == "new_password"
    assert CLAVE_PRUEBA not in error.message


def test_distinta_de_la_actual_pasa(argon2_rapido: None) -> None:
    actual = hash_password(CLAVE_PRUEBA)
    assert validate_password_policy(DOCE, current_hash=actual, field="new_password") is None


def test_la_longitud_se_revisa_antes_que_la_igualdad(argon2_rapido: None) -> None:
    """Una corta no llega a argon2: el rechazo es por la política, con el mismo campo."""
    actual = hash_password(CLAVE_PRUEBA)
    error = _rechazo(ONCE, current_hash=actual, field="new_password")
    assert error.code == "weak_password" and error.field == "new_password"
