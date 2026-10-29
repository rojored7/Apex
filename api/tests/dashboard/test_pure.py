"""Funciones puras del tablero (S4A-B8; US-108, US-110; S4A-D27, S4A-D28).

- `month_of(today)`: `AAAA-MM` del día (fin de mes, fin de año, primer día del año).
- `short_name(first, last)`: nombre y la inicial del apellido con punto (apellido compuesto, con
  tildes y con la eñe).
- `format_cop(amount)`: `$ ` y punto de miles (cero, cientos, miles y millones).
"""

from __future__ import annotations

from datetime import date

import pytest

from tests.dashboard.conftest import dashboard_service


@pytest.mark.parametrize(
    ("hoy", "esperado"),
    [
        (date(2026, 10, 20), "2026-10"),
        (date(2026, 10, 31), "2026-10"),
        (date(2026, 11, 1), "2026-11"),
        (date(2026, 2, 28), "2026-02"),
        (date(2026, 12, 31), "2026-12"),
        (date(2027, 1, 1), "2027-01"),
    ],
    ids=str,
)
def test_month_of_da_el_mes_del_dia(hoy: date, esperado: str) -> None:
    assert dashboard_service.month_of(hoy) == esperado


@pytest.mark.parametrize(
    ("nombre", "apellido", "esperado"),
    [
        ("Laura", "Gómez Restrepo", "Laura G."),
        ("Laura", "Gómez", "Laura G."),
        ("Lucía", "Gómez", "Lucía G."),
        ("Íñigo", "Ñúñez Pérez", "Íñigo Ñ."),
        ("Juan", "Ríos", "Juan R."),
        ("Ángela", "Álvarez", "Ángela Á."),
    ],
)
def test_short_name_es_nombre_e_inicial_del_apellido(
    nombre: str, apellido: str, esperado: str
) -> None:
    assert dashboard_service.short_name(nombre, apellido) == esperado


@pytest.mark.parametrize(
    ("monto", "esperado"),
    [
        (120_000, "$ 120.000"),
        (0, "$ 0"),
        (950, "$ 950"),
        (1_000, "$ 1.000"),
        (1_234_567, "$ 1.234.567"),
    ],
)
def test_format_cop_usa_punto_de_miles(monto: int, esperado: str) -> None:
    assert dashboard_service.format_cop(monto) == esperado
