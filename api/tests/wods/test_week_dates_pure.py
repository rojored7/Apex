"""`week_dates` puro (S8-A3, US-167; S8-D8). Rojo A3."""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.wods.exceptions import WodsValidationError
from app.modules.wods.rules import week_dates


def test_2026_w43_es_19_a_25_de_octubre() -> None:
    assert week_dates("2026-W43") == (date(2026, 10, 19), date(2026, 10, 25))


def test_la_semana_1_puede_empezar_en_el_anio_anterior() -> None:
    assert week_dates("2026-W01") == (date(2025, 12, 29), date(2026, 1, 4))


def test_w53_existente_vale() -> None:
    assert week_dates("2020-W53") == (date(2020, 12, 28), date(2021, 1, 3))


def test_w53_inexistente_da_422_week() -> None:
    with pytest.raises(WodsValidationError) as error:
        week_dates("2025-W53")
    assert error.value.field == "week"


@pytest.mark.parametrize("año", ["2019", "2101", "0000"])
def test_anio_fuera_de_2020_a_2100(año: str) -> None:
    with pytest.raises(WodsValidationError) as error:
        week_dates(f"{año}-W10")
    assert error.value.field == "week"


@pytest.mark.parametrize("malo", ["2026-43", "2026W43", "2026-W4", "2026-W00", "26-W43", "", "x"])
def test_formato_mal_formado(malo: str) -> None:
    with pytest.raises(WodsValidationError) as error:
        week_dates(malo)
    assert error.value.field == "week"


def test_los_limites_del_rango_valen() -> None:
    assert week_dates("2020-W10")[0].year == 2020
    assert week_dates("2100-W10")[0].year == 2100
