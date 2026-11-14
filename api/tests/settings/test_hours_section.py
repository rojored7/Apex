"""Sección `hours` (US-154, S7-D8, N-18): rangos `HH:MM` de Bogotá, de 0 a 2 por día."""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.settings.exceptions import SettingsValidationError
from app.modules.settings.schemas import (
    ENABLED_SECTIONS,
    SECTION_REGISTRY,
    HoursSettings,
    SectionKey,
)
from app.modules.settings.service import defaults_for, validate_section
from tests.settings._apoyo import DIAS, HOURS_DEFAULTS, HOURS_OK


def _error(valor: dict[str, Any]) -> SettingsValidationError:
    with pytest.raises(SettingsValidationError) as excinfo:
        validate_section(SectionKey.hours, valor)
    assert excinfo.value.status == 422
    return excinfo.value


def test_hours_esta_habilitada_y_registrada() -> None:
    assert SectionKey.hours in ENABLED_SECTIONS
    assert SECTION_REGISTRY[SectionKey.hours] is HoursSettings


def test_rango_valido() -> None:
    modelo = validate_section(SectionKey.hours, HOURS_OK)
    assert modelo.model_dump(mode="json") == HOURS_OK


def test_por_omision_los_siete_vacios() -> None:
    assert defaults_for(SectionKey.hours) == HOURS_DEFAULTS
    assert validate_section(SectionKey.hours, {}).model_dump(mode="json") == HOURS_DEFAULTS
    assert set(HOURS_DEFAULTS) == set(DIAS)


def test_lista_vacia_es_cerrado() -> None:
    modelo = validate_section(SectionKey.hours, {**HOURS_OK, "monday": []})
    assert modelo.model_dump(mode="json")["monday"] == []


@pytest.mark.parametrize(
    "rango",
    [
        {"open": "21:00", "close": "05:00"},
        {"open": "10:00", "close": "10:00"},
    ],
    ids=["abre_despues_de_cerrar", "igual"],
)
def test_open_no_menor_que_close_da_422_hours_monday(rango: dict[str, str]) -> None:
    error = _error({**HOURS_OK, "monday": [rango]})
    assert error.field == "value.monday"
    assert "21:00" not in error.message


# Dígitos no ASCII que `\d` aceptaba: árabe-índicos (U+0665), de ancho completo (U+FF10) y
# devanagari (U+0966); y un salto de línea final. Se construyen con chr() (sin invisibles).
_ARABE_5 = chr(0x0665)
_ANCHO_0 = chr(0xFF10)
_DEVA_0 = chr(0x0966)


@pytest.mark.parametrize(
    "hora",
    [
        "5:00",
        "24:00",
        "12:60",
        "0500",
        "ab:cd",
        "",
        f"0{_ARABE_5}:00",
        f"{_ANCHO_0}5:00",
        f"05:{_DEVA_0}0",
    ],
    ids=[
        "una_cifra",
        "24",
        "60_min",
        "sin_dos_puntos",
        "letras",
        "vacio",
        "arabe",
        "ancho_completo",
        "devanagari",
    ],
)
def test_formato_hhmm_invalido_da_422(hora: str) -> None:
    error = _error({**HOURS_OK, "tuesday": [{"open": hora, "close": "23:00"}]})
    assert error.field is not None and "tuesday" in error.field


def test_rangos_solapados_dan_422() -> None:
    solapados = [{"open": "06:00", "close": "10:00"}, {"open": "09:00", "close": "12:00"}]
    error = _error({**HOURS_OK, "wednesday": solapados})
    assert error.field is not None and error.field.endswith("wednesday")


def test_rangos_desordenados_dan_422() -> None:
    desordenados = [{"open": "16:00", "close": "20:00"}, {"open": "06:00", "close": "10:00"}]
    error = _error({**HOURS_OK, "thursday": desordenados})
    assert error.field is not None and error.field.endswith("thursday")


def test_rangos_contiguos_son_validos() -> None:
    contiguos = [{"open": "06:00", "close": "10:00"}, {"open": "10:00", "close": "12:00"}]
    validate_section(SectionKey.hours, {**HOURS_OK, "friday": contiguos})


def test_mas_de_dos_rangos_da_422() -> None:
    tres = [
        {"open": "05:00", "close": "07:00"},
        {"open": "08:00", "close": "10:00"},
        {"open": "11:00", "close": "13:00"},
    ]
    error = _error({**HOURS_OK, "sunday": tres})
    assert error.field is not None and error.field.endswith("sunday")


def test_clave_ajena_o_dia_con_forma_vieja_da_422() -> None:
    assert _error({**HOURS_OK, "festivos": []}).field is not None
    assert _error({**HOURS_OK, "monday": {"closed": True}}).field is not None
