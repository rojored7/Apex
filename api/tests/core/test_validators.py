"""`EmailAddress` de `core/validators.py` (blueprint S2, decisión 5) y, desde S4A-B4,
`check_instant_range` (S4A-D46, S4A-D66): pruebas puras."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, ValidationError

from app.core.validators import (
    EMAIL_MAX_LENGTH,
    INSTANT_FLOOR,
    EmailAddress,
    check_email_shape,
    check_instant_range,
    instant_ceiling,
)
from app.modules.payments.rules import PAID_AT_FLOOR


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


# S4A-B4 (S4A-D46, S4A-D66): rango de instantes de un filtro ---------------------------------
#
# Valores a mano con `AHORA = 2026-10-21T15:00:00Z`: piso 2020-01-01T00:00Z, techo
# 2026-10-22T15:00:00Z (`now + 1 día`). El error es `ValueError(<campo>)`: su único argumento es
# el nombre del campo y nunca el valor.

AHORA = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
TECHO = datetime(2026, 10, 22, 15, 0, tzinfo=UTC)
UN_MICRO = timedelta(microseconds=1)
MAS_CINCO = timezone(timedelta(hours=5))


def _rango(start: datetime | None, end: datetime | None) -> None:
    check_instant_range(start, end, now=AHORA, field_start="from", field_end="to")


def _campo_del_error(start: datetime | None, end: datetime | None) -> str:
    with pytest.raises(ValueError) as capturado:
        _rango(start, end)
    assert len(capturado.value.args) == 1
    return str(capturado.value.args[0])


def test_piso_y_techo_de_instantes() -> None:
    assert datetime(2020, 1, 1, tzinfo=UTC) == INSTANT_FLOOR
    assert instant_ceiling(AHORA) == TECHO


def test_paid_at_floor_de_pagos_es_el_mismo_piso() -> None:
    """S4A-D66: `payments.rules` no cambia; su piso coincide con el de `core/validators`."""
    assert PAID_AT_FLOOR == INSTANT_FLOOR


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (None, None),
        (INSTANT_FLOOR, None),
        (None, TECHO),
        (INSTANT_FLOOR, TECHO),
        (AHORA - timedelta(days=30), AHORA),
        (TECHO - UN_MICRO, TECHO),
        (datetime(2026, 10, 21, 5, 0, tzinfo=timezone(timedelta(hours=-5))), None),
    ],
    ids=["sin-rango", "piso", "techo", "todo", "mes", "un-micro", "bogota"],
)
def test_rangos_validos(start: datetime | None, end: datetime | None) -> None:
    assert _rango(start, end) is None


@pytest.mark.parametrize(
    ("start", "end", "campo"),
    [
        (INSTANT_FLOOR - UN_MICRO, None, "from"),
        (None, INSTANT_FLOOR - UN_MICRO, "to"),
        (TECHO + UN_MICRO, None, "from"),
        (None, TECHO + UN_MICRO, "to"),
        (datetime(1, 1, 1, tzinfo=MAS_CINCO), None, "from"),
        (None, datetime(9999, 12, 31, tzinfo=UTC), "to"),
        (datetime(1, 1, 1, tzinfo=MAS_CINCO), datetime(9999, 12, 31, 23, 59, tzinfo=UTC), "from"),
        (AHORA, AHORA - UN_MICRO, "to"),
        (AHORA, AHORA, "to"),
        (datetime(2026, 10, 1), None, "from"),
        (None, datetime(2026, 10, 1), "to"),
    ],
    ids=[
        "from-bajo-piso",
        "to-bajo-piso",
        "from-sobre-techo",
        "to-sobre-techo",
        "from-anio-1",
        "to-anio-9999",
        "ambos-extremos",
        "invertido",
        "iguales",
        "from-sin-zona",
        "to-sin-zona",
    ],
)
def test_rangos_invalidos_dan_el_campo(
    start: datetime | None, end: datetime | None, campo: str
) -> None:
    assert _campo_del_error(start, end) == campo


def test_los_nombres_de_campo_los_elige_quien_llama() -> None:
    with pytest.raises(ValueError) as capturado:
        check_instant_range(AHORA, AHORA, now=AHORA, field_start="desde", field_end="hasta")
    assert capturado.value.args == ("hasta",)


def test_el_error_no_repite_el_valor() -> None:
    with pytest.raises(ValueError) as capturado:
        _rango(datetime(1999, 12, 31, 23, 59, tzinfo=UTC), None)
    assert "1999" not in str(capturado.value)
