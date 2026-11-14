"""Sección `classes` (US-154, S7-D8, N-18, N-38): cupo 1 a 100 y ventana 0 a 240, sin sobrecupo."""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.settings.exceptions import SettingsValidationError
from app.modules.settings.schemas import (
    ENABLED_SECTIONS,
    SECTION_REGISTRY,
    ClassesSettings,
    SectionKey,
)
from app.modules.settings.service import defaults_for, validate_section
from tests.settings._apoyo import CLASSES_DEFAULTS, CLASSES_OK


def _campo_invalido(valor: dict[str, Any]) -> str | None:
    with pytest.raises(SettingsValidationError) as excinfo:
        validate_section(SectionKey.classes, valor)
    assert excinfo.value.status == 422
    return excinfo.value.field


def test_classes_esta_habilitada_y_registrada() -> None:
    assert SectionKey.classes in ENABLED_SECTIONS
    assert SECTION_REGISTRY[SectionKey.classes] is ClassesSettings


def test_por_omision_15_y_30() -> None:
    assert defaults_for(SectionKey.classes) == CLASSES_DEFAULTS
    assert validate_section(SectionKey.classes, {}).model_dump() == CLASSES_DEFAULTS


def test_valor_valido() -> None:
    assert validate_section(SectionKey.classes, CLASSES_OK).model_dump() == CLASSES_OK


def test_capacidad_1_a_100() -> None:
    for valor in (1, 100):
        modelo = validate_section(SectionKey.classes, {**CLASSES_OK, "default_capacity": valor})
        assert modelo.model_dump()["default_capacity"] == valor
    for valor in (0, 101, -1):
        campo = _campo_invalido({**CLASSES_OK, "default_capacity": valor})
        assert campo == "value.default_capacity"


def test_ventana_0_a_240() -> None:
    for valor in (0, 240):
        modelo = validate_section(SectionKey.classes, {**CLASSES_OK, "checkin_window_min": valor})
        assert modelo.model_dump()["checkin_window_min"] == valor
    for valor in (-1, 241):
        campo = _campo_invalido({**CLASSES_OK, "checkin_window_min": valor})
        assert campo == "value.checkin_window_min"


@pytest.mark.parametrize("valor", ["15", 15.5, True], ids=["texto", "decimal", "booleano"])
def test_no_enteros_dan_422(valor: object) -> None:
    assert _campo_invalido({**CLASSES_OK, "default_capacity": valor}) == "value.default_capacity"


def test_allow_over_capacity_da_422() -> None:
    campo = _campo_invalido({**CLASSES_OK, "allow_over_capacity": True})
    assert campo == "value.allow_over_capacity"
