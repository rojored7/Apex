"""Esquema de `privacy` (US-057 T3; N-18): versión, texto, retención y fecha de consentimiento."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.modules.settings.exceptions import SettingsValidationError
from app.modules.settings.schemas import SECTION_REGISTRY, PrivacySettings, SectionKey
from app.modules.settings.service import validate_section
from tests.settings._apoyo import PRIVACY_OK


def _campo_invalido(valor: dict[str, Any]) -> str | None:
    with pytest.raises(SettingsValidationError) as excinfo:
        validate_section(SectionKey.privacy, valor)
    assert excinfo.value.status == 422
    return excinfo.value.field


def _sin(campo: str) -> dict[str, Any]:
    return {k: v for k, v in PRIVACY_OK.items() if k != campo}


def test_privacy_esta_registrada_con_su_esquema() -> None:
    assert SECTION_REGISTRY[SectionKey.privacy] is PrivacySettings


def test_valor_valido() -> None:
    assert validate_section(SectionKey.privacy, PRIVACY_OK).model_dump(mode="json") == PRIVACY_OK


def test_retencion_por_defecto_5_y_fecha_por_defecto_nula() -> None:
    modelo = validate_section(
        SectionKey.privacy, {"policy_version": "2026-10", "policy_text": "Texto."}
    )
    assert modelo.model_dump()["retention_years"] == 5
    assert modelo.model_dump()["consent_required_from"] is None


@pytest.mark.parametrize("texto", ["", None], ids=["vacio", "nulo"])
def test_texto_vacio_o_nulo_da_value_policy_text(texto: str | None) -> None:
    assert _campo_invalido({**PRIVACY_OK, "policy_text": texto}) == "value.policy_text"


def test_sin_texto_da_value_policy_text() -> None:
    assert _campo_invalido(_sin("policy_text")) == "value.policy_text"


def test_texto_de_20000_vale_y_de_20001_no() -> None:
    assert validate_section(SectionKey.privacy, {**PRIVACY_OK, "policy_text": "a" * 20_000})
    assert _campo_invalido({**PRIVACY_OK, "policy_text": "a" * 20_001}) == "value.policy_text"


@pytest.mark.parametrize("version", ["", "x" * 21], ids=["vacia", "21"])
def test_version_invalida_da_value_policy_version(version: str) -> None:
    assert _campo_invalido({**PRIVACY_OK, "policy_version": version}) == "value.policy_version"


def test_sin_version_da_value_policy_version() -> None:
    assert _campo_invalido(_sin("policy_version")) == "value.policy_version"


def test_version_de_20_vale() -> None:
    modelo = validate_section(SectionKey.privacy, {**PRIVACY_OK, "policy_version": "x" * 20})
    assert modelo.model_dump()["policy_version"] == "x" * 20


@pytest.mark.parametrize("anos", [0, 21, 2.5, "5", True], ids=["0", "21", "2.5", "texto", "bool"])
def test_retencion_fuera_de_rango_o_no_entera_da_value_retention_years(anos: object) -> None:
    assert _campo_invalido({**PRIVACY_OK, "retention_years": anos}) == "value.retention_years"


@pytest.mark.parametrize("anos", [1, 20])
def test_retencion_en_los_bordes_vale(anos: int) -> None:
    modelo = validate_section(SectionKey.privacy, {**PRIVACY_OK, "retention_years": anos})
    assert modelo.model_dump()["retention_years"] == anos


def test_fecha_de_consentimiento_invalida_da_su_field() -> None:
    campo = _campo_invalido({**PRIVACY_OK, "consent_required_from": "2026-13-01"})
    assert campo == "value.consent_required_from"


def test_fecha_de_consentimiento_valida() -> None:
    modelo = validate_section(
        SectionKey.privacy, {**PRIVACY_OK, "consent_required_from": "2026-11-01"}
    )
    assert modelo.model_dump()["consent_required_from"] == date(2026, 11, 1)
    assert modelo.model_dump(mode="json")["consent_required_from"] == "2026-11-01"


@pytest.mark.parametrize("viejo", ["policy_url", "effective_from"])
def test_campos_que_n18_no_tiene_se_rechazan(viejo: str) -> None:
    assert _campo_invalido({**PRIVACY_OK, viejo: "x"}) == f"value.{viejo}"
