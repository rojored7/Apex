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


# N-2 y Python H2 (revisión del Sprint 2): texto seguro en toda entrada ---------------------

from app.core.validators import (  # noqa: E402
    SafeMultilineText,
    SafeText,
    check_multiline_text,
    check_visible_text,
)


class _Nombre(BaseModel):
    nombre: SafeText


class _Texto(BaseModel):
    texto: SafeMultilineText


@pytest.mark.parametrize(
    "valor",
    ["a\x00b", "\x00", "a\x1fb", "\x7f", "a\u200bb", "\u200b", "a\u202eb", "\ufeffx", "\u2066a"],
    ids=["nul", "solo-nul", "us", "del", "zwsp", "solo-zwsp", "rlo", "bom", "lri"],
)
def test_safe_text_rechaza_control_y_formato(valor: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _Nombre(nombre=valor)
    assert excinfo.value.errors()[0]["loc"] == ("nombre",)
    assert all(valor not in e["msg"] for e in excinfo.value.errors())


@pytest.mark.parametrize(
    "valor", ["", "   ", "\u3000", "\u00a0"], ids=["vacio", "blanco", "ideo", "nbsp"]
)
def test_safe_text_exige_algo_visible(valor: str) -> None:
    with pytest.raises(ValidationError):
        _Nombre(nombre=valor)


def test_safe_text_normaliza_a_nfc_y_recorta() -> None:
    compuesto = _Nombre(nombre="  Jose\u0301 ").nombre
    assert compuesto == "José"
    assert len(compuesto) == 4


def test_safe_text_acepta_nombres_reales() -> None:
    for nombre in ("María José", "O'Neil", "Nguyễn", "Zoë-Ann", "Peña"):
        assert _Nombre(nombre=nombre).nombre == nombre


def test_check_visible_text_es_pura_y_no_repite_el_valor() -> None:
    with pytest.raises(ValueError) as excinfo:
        check_visible_text("secreto\x00")
    assert "secreto" not in str(excinfo.value)
    assert check_visible_text("e\u0301") == "é"


def test_safe_multiline_text_admite_saltos_y_tabuladores() -> None:
    texto = "Política\n\n\tArtículo 1.\r\nFin"
    assert _Texto(texto=texto).texto == texto


@pytest.mark.parametrize(
    "valor",
    ["a\x00b", "a\x07b", "a\u202eb", "a\u2066b", "\n\n"],
    ids=["nul", "bel", "rlo", "lri", "solo-saltos"],
)
def test_safe_multiline_text_rechaza_nul_controles_y_bidi(valor: str) -> None:
    with pytest.raises(ValidationError):
        _Texto(texto=valor)
    with pytest.raises(ValueError):
        check_multiline_text(valor)


@pytest.mark.parametrize("correo", ["a\x00@x.co", "a@x\x00.co", "a\u200b@x.co", "\u202ea@x.co"])
def test_email_address_rechaza_nul_y_formato(correo: str) -> None:
    with pytest.raises(ValidationError):
        _valida(correo)
