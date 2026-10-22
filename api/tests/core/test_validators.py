"""`EmailAddress` de `core/validators.py` (blueprint S2, decisión 5): pruebas puras."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app.core.validators import EMAIL_MAX_LENGTH, EmailAddress, check_email_shape


class _Correo(BaseModel):
    email: EmailAddress


def _valida(valor: str) -> str:
    return _Correo(email=valor).email


def test_recorta_espacios_y_pasa_a_minusculas() -> None:
    assert _valida("  Hola@CrossFit.CO ") == "hola@crossfit.co"


@pytest.mark.parametrize(
    "correo", ["socia@apex.co", "a.b+c@sub.dominio.com.co", "x@y.z"], ids=["simple", "sub", "corto"]
)
def test_correos_validos(correo: str) -> None:
    assert _valida(correo) == correo


@pytest.mark.parametrize(
    "correo",
    [
        "no-es-correo",
        "@apex.co",
        "socia@",
        "socia@apex",
        "con espacio@apex.co",
        "dos@@apex.co",
        "a@b@apex.co",
        "",
        "   ",
    ],
    ids=[
        "sin-arroba",
        "sin-local",
        "sin-dominio",
        "sin-punto",
        "espacio",
        "doble",
        "dos",
        "vacio",
        "blanco",
    ],
)
def test_correos_invalidos(correo: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _valida(correo)
    errores = excinfo.value.errors()
    assert errores[0]["loc"] == ("email",)


def test_255_caracteres_se_rechazan_y_254_valen() -> None:
    dominio = "@apex.co"
    justo = "a" * (EMAIL_MAX_LENGTH - len(dominio)) + dominio
    assert _valida(justo) == justo
    with pytest.raises(ValidationError):
        _valida("a" + justo)


def test_el_mensaje_no_repite_el_valor() -> None:
    valor = "correo-raro-8812"
    with pytest.raises(ValueError, match="forma válida") as excinfo:
        check_email_shape(valor)
    assert valor not in str(excinfo.value)
    with pytest.raises(ValidationError) as error_modelo:
        _valida(valor)
    assert all(valor not in e["msg"] for e in error_modelo.value.errors())


def test_la_funcion_pura_devuelve_el_valor() -> None:
    assert check_email_shape("a@b.co") == "a@b.co"
