"""Esquema de `gym` (US-055 T2; N-18): campos, rangos y `extra="forbid"`."""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.settings.exceptions import SettingsValidationError
from app.modules.settings.schemas import SECTION_REGISTRY, GymSettings, SectionKey
from app.modules.settings.service import validate_section
from tests.settings._apoyo import GYM_OK


def _campo_invalido(valor: dict[str, Any]) -> str | None:
    with pytest.raises(SettingsValidationError) as excinfo:
        validate_section(SectionKey.gym, valor)
    assert excinfo.value.status == 422
    return excinfo.value.field


def test_gym_esta_registrado_con_su_esquema() -> None:
    assert SECTION_REGISTRY[SectionKey.gym] is GymSettings


def test_valor_completo_valido() -> None:
    assert validate_section(SectionKey.gym, GYM_OK).model_dump(mode="json") == GYM_OK


def test_solo_el_nombre_es_obligatorio() -> None:
    modelo = validate_section(SectionKey.gym, {"name": "APEX Box"})
    assert modelo.model_dump(mode="json") == {
        "name": "APEX Box",
        "nit": None,
        "address": None,
        "city": None,
        "phone": None,
        "whatsapp": None,
        "email": None,
    }


@pytest.mark.parametrize("nombre", ["", "   ", "x" * 81], ids=["vacio", "espacios", "81"])
def test_nombre_invalido_da_value_name(nombre: str) -> None:
    assert _campo_invalido({**GYM_OK, "name": nombre}) == "value.name"


def test_sin_nombre_da_value_name() -> None:
    sin_nombre = {k: v for k, v in GYM_OK.items() if k != "name"}
    assert _campo_invalido(sin_nombre) == "value.name"


def test_nombre_de_80_y_espacios_recortados() -> None:
    assert validate_section(SectionKey.gym, {"name": "x" * 80}).model_dump()["name"] == "x" * 80
    assert validate_section(SectionKey.gym, {"name": "  APEX  "}).model_dump()["name"] == "APEX"


@pytest.mark.parametrize("nit", ["901234567-8", "900123456", "1"])
def test_nit_valido(nit: str) -> None:
    assert validate_section(SectionKey.gym, {**GYM_OK, "nit": nit}).model_dump()["nit"] == nit


@pytest.mark.parametrize(
    "nit",
    ["90-12-3", "ABC", "901234567-89", "90123456789012-4", "1234567890123456", "-1", "901234567-"],
)
def test_nit_invalido_da_value_nit(nit: str) -> None:
    assert _campo_invalido({**GYM_OK, "nit": nit}) == "value.nit"


@pytest.mark.parametrize("correo", ["no-es-correo", "a@b", "con espacio@x.co", "@x.co"])
def test_correo_mal_formado_da_value_email(correo: str) -> None:
    assert _campo_invalido({**GYM_OK, "email": correo}) == "value.email"


def test_correo_se_normaliza_a_minusculas() -> None:
    modelo = validate_section(SectionKey.gym, {**GYM_OK, "email": " Hola@CrossFit.CO "})
    assert modelo.model_dump()["email"] == "hola@crossfit.co"


@pytest.mark.parametrize(
    ("campo", "maximo"), [("address", 120), ("city", 60), ("phone", 20), ("whatsapp", 20)]
)
def test_longitudes_maximas(campo: str, maximo: int) -> None:
    assert validate_section(SectionKey.gym, {**GYM_OK, campo: "1" * maximo})
    assert _campo_invalido({**GYM_OK, campo: "1" * (maximo + 1)}) == f"value.{campo}"


@pytest.mark.parametrize("viejo", ["legal_id", "contact_email", "timezone"])
def test_campos_viejos_o_desconocidos_se_rechazan(viejo: str) -> None:
    assert _campo_invalido({**GYM_OK, viejo: "x"}) == f"value.{viejo}"
