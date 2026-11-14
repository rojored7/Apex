"""`classes.rules` puras (S7-A2, US-155; S7-D9). Sin base ni reloj."""

from __future__ import annotations

import pytest

from app.modules.classes.exceptions import ClassValidationError
from app.modules.classes.rules import normalize_weekdays, slots_overlap, validate_slot


def _campo(**cambios: object) -> str:
    valores: dict[str, object] = {
        "weekdays": [0],
        "start_time": "06:00",
        "duration_min": 60,
        "capacity": 15,
    }
    valores.update(cambios)
    with pytest.raises(ClassValidationError) as error:
        validate_slot(**valores)  # type: ignore[arg-type]
    assert error.value.status == 422
    return str(error.value.field)


def test_una_franja_valida_no_lanza() -> None:
    validate_slot([0, 2, 4], "06:00", 60, 15)
    validate_slot(list(range(7)), "23:59", 240, 100)
    validate_slot([6], "00:00", 15, 1)


@pytest.mark.parametrize("dias", [[], [0, 0], [-1], [7], [0, 1, 2, 3, 4, 5, 6, 6]])
def test_dias_vacios_repetidos_o_fuera_de_rango(dias: list[int]) -> None:
    assert _campo(weekdays=dias) == "weekdays"


@pytest.mark.parametrize("hora", ["", "6:00", "24:00", "12:60", "06:00:00", "ab:cd"])
def test_hora_invalida(hora: str) -> None:
    assert _campo(start_time=hora) == "start_time"


@pytest.mark.parametrize("duracion", [0, 14, 241, -5])
def test_duracion_15_a_240(duracion: int) -> None:
    assert _campo(duration_min=duracion) == "duration_min"


@pytest.mark.parametrize("cupo", [0, -1, 101])
def test_cupo_1_a_100(cupo: int) -> None:
    assert _campo(capacity=cupo) == "capacity"


def test_el_mensaje_no_repite_el_valor() -> None:
    with pytest.raises(ClassValidationError) as error:
        validate_slot([0], "06:00", 9999, 15)
    assert "9999" not in str(error.value)


def test_normalize_weekdays_ordena_y_quita_repetidos() -> None:
    assert normalize_weekdays([4, 0, 2, 0]) == [0, 2, 4]


def test_slots_overlap_exige_un_dia_y_la_hora_en_comun() -> None:
    assert slots_overlap([0, 2], "06:00", [2, 3], "06:00")
    assert not slots_overlap([0, 2], "06:00", [1, 3], "06:00")
    assert not slots_overlap([0, 2], "06:00", [0, 2], "06:30")
