"""`wods.normalize_movement_name` (S8-A1, US-165; S8-D5). Pura: sin base. Rojo A1."""

from __future__ import annotations

import pytest

from app.modules.wods.exceptions import WodsValidationError
from app.modules.wods.rules import clean_movement_name, normalize_movement_name


def test_nfkc_recorte_y_espacios_colapsados() -> None:
    nbsp = chr(0xA0)
    assert normalize_movement_name(f"  Back \t  Squat{nbsp}{nbsp}Alto ") == "back squat alto"
    # NFKC: ligadura y ancho completo pasan a su forma de compatibilidad.
    assert normalize_movement_name(chr(0xFB01) + "nisher") == "finisher"
    assert normalize_movement_name(chr(0xFF21) + "ir squat") == "air squat"


def test_minusculas() -> None:
    assert normalize_movement_name("PULL-UP") == "pull-up"
    assert normalize_movement_name(" pull-up ") == normalize_movement_name("Pull-Up")


def test_conserva_tildes_y_enes() -> None:
    assert normalize_movement_name("Salto de Cuerda Doble Año") == "salto de cuerda doble año"


@pytest.mark.parametrize("valor", ["", "   ", "\t\n", chr(0xA0) + chr(0x3000)])
def test_vacio_tras_normalizar_da_422(valor: str) -> None:
    with pytest.raises(WodsValidationError) as error:
        normalize_movement_name(valor)
    assert error.value.status == 422
    assert error.value.field == "name"


def test_expansion_de_nfkc_que_pasa_de_60_da_422() -> None:
    # U+FDFA expande a 18 caracteres: cuatro pasan de 60.
    with pytest.raises(WodsValidationError) as error:
        normalize_movement_name(chr(0xFDFA) * 4)
    assert error.value.field == "name"


def test_exactamente_60_pasa() -> None:
    assert normalize_movement_name("a" * 60) == "a" * 60


def test_clean_movement_name_colapsa_espacios_y_conserva_mayusculas() -> None:
    assert clean_movement_name("  Back \t  Squat ") == "Back Squat"
