"""Esquema de `memberships` (US-058 T3; N-18): bordes de los cuatro rangos y enteros estrictos."""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.settings.exceptions import SettingsValidationError
from app.modules.settings.schemas import SECTION_REGISTRY, MembershipsSettings, SectionKey
from app.modules.settings.service import validate_section
from tests.settings._apoyo import MEMBERSHIPS_DEFAULTS, MEMBERSHIPS_OK

# (campo, mínimo, máximo) de N-18.
RANGOS = (
    ("expiring_days", 1, 30),
    ("max_freeze_days_per_membership", 0, 180),
    ("max_freezes_per_membership", 0, 12),
    ("max_retroactive_days", 0, 30),
)
CAMPOS = [campo for campo, _, _ in RANGOS]


def _campo_invalido(valor: dict[str, Any]) -> str | None:
    with pytest.raises(SettingsValidationError) as excinfo:
        validate_section(SectionKey.memberships, valor)
    assert excinfo.value.status == 422
    return excinfo.value.field


def test_memberships_esta_registrada_con_su_esquema() -> None:
    assert SECTION_REGISTRY[SectionKey.memberships] is MembershipsSettings


def test_valor_valido() -> None:
    modelo = validate_section(SectionKey.memberships, MEMBERSHIPS_OK)
    assert modelo.model_dump() == MEMBERSHIPS_OK


def test_campos_omitidos_vuelven_a_su_default() -> None:
    assert validate_section(SectionKey.memberships, {}).model_dump() == MEMBERSHIPS_DEFAULTS


@pytest.mark.parametrize(("campo", "minimo", "maximo"), RANGOS)
def test_bordes_validos(campo: str, minimo: int, maximo: int) -> None:
    for valor in (minimo, maximo):
        modelo = validate_section(SectionKey.memberships, {**MEMBERSHIPS_OK, campo: valor})
        assert modelo.model_dump()[campo] == valor


@pytest.mark.parametrize(("campo", "minimo", "maximo"), RANGOS)
def test_fuera_de_rango_da_su_field(campo: str, minimo: int, maximo: int) -> None:
    for valor in (minimo - 1, maximo + 1):
        assert _campo_invalido({**MEMBERSHIPS_OK, campo: valor}) == f"value.{campo}"


def test_cero_dias_de_congelacion_vale_y_181_no() -> None:
    modelo = validate_section(
        SectionKey.memberships, {**MEMBERSHIPS_OK, "max_freeze_days_per_membership": 0}
    )
    assert modelo.model_dump()["max_freeze_days_per_membership"] == 0
    campo = _campo_invalido({**MEMBERSHIPS_OK, "max_freeze_days_per_membership": 181})
    assert campo == "value.max_freeze_days_per_membership"


@pytest.mark.parametrize("campo", CAMPOS)
@pytest.mark.parametrize("valor", [7.5, "7", 7.0], ids=["decimal", "texto", "flotante-entero"])
def test_no_enteros_se_rechazan_en_modo_estricto(campo: str, valor: object) -> None:
    assert _campo_invalido({**MEMBERSHIPS_OK, campo: valor}) == f"value.{campo}"


def test_campo_desconocido_se_rechaza() -> None:
    assert _campo_invalido({**MEMBERSHIPS_OK, "grace_days": 3}) == "value.grace_days"
