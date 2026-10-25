"""`payments.rules.parse_month` y `month_bounds_utc` (S3-B8, US-100; D23, M-4, S3-D47).

El mes se lee en Bogotá (UTC-5 sin horario de verano desde 1993) y se devuelve como el rango
semiabierto `[inicio, fin)` en UTC. Cálculos a mano:
- `2026-10`: inicio 2026-10-01 00:00 Bogotá = 2026-10-01T05:00Z; fin 2026-11-01 00:00 Bogotá =
  2026-11-01T05:00Z;
- `2026-12`: fin 2027-01-01T05:00Z (cruza de año con aritmética de `(año, mes)`);
- `2100-12`: fin 2101-01-01T05:00Z (el último mes válido no desborda);
- `2020-01`: inicio 2020-01-01T05:00Z (el primero válido).

Formato estricto `AAAA-MM` con dígitos ASCII y año entre `MONTH_MIN` (2020) y `MONTH_MAX`
(2100): cualquier otra cosa es `InvalidMonth` (422 `validation_error`, `field="month"`, sin el
valor en el mensaje), nunca `ValueError` ni `OverflowError` (M-4: `9999-12` y `0000-01`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.payments import rules
from app.modules.payments.exceptions import InvalidMonth


def test_los_limites_de_anio_son_2020_y_2100() -> None:
    assert (rules.MONTH_MIN, rules.MONTH_MAX) == (2020, 2100)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("2026-10", (2026, 10)), ("2020-01", (2020, 1)), ("2100-12", (2100, 12))],
)
def test_parse_month_da_anio_y_mes(valor: str, esperado: tuple[int, int]) -> None:
    assert rules.parse_month(valor) == esperado


def test_octubre_de_2026_va_de_las_5_utc_del_1_a_las_5_utc_del_1_de_noviembre() -> None:
    inicio, fin = rules.month_bounds_utc("2026-10")
    assert inicio == datetime(2026, 10, 1, 5, 0, tzinfo=UTC)
    assert fin == datetime(2026, 11, 1, 5, 0, tzinfo=UTC)
    assert inicio.utcoffset() == timedelta(0)
    assert fin.utcoffset() == timedelta(0)


def test_diciembre_cruza_de_anio() -> None:
    assert rules.month_bounds_utc("2026-12") == (
        datetime(2026, 12, 1, 5, 0, tzinfo=UTC),
        datetime(2027, 1, 1, 5, 0, tzinfo=UTC),
    )


def test_los_meses_extremos_validos_no_desbordan() -> None:
    assert rules.month_bounds_utc("2100-12") == (
        datetime(2100, 12, 1, 5, 0, tzinfo=UTC),
        datetime(2101, 1, 1, 5, 0, tzinfo=UTC),
    )
    assert rules.month_bounds_utc("2020-01") == (
        datetime(2020, 1, 1, 5, 0, tzinfo=UTC),
        datetime(2020, 2, 1, 5, 0, tzinfo=UTC),
    )


def test_febrero_bisiesto_termina_el_1_de_marzo() -> None:
    assert rules.month_bounds_utc("2028-02")[1] == datetime(2028, 3, 1, 5, 0, tzinfo=UTC)


ANCHO_COMPLETO = "".join(chr(ord(c) + 0xFEE0) if c.isdigit() else c for c in "2026-10")
INVALIDOS = [
    "2026-13",
    "2026-00",
    "2026-1",
    "26-10",
    "abcd-ef",
    "9999-12",
    "0000-01",
    "2019-12",
    "2101-01",
    "",
    "2026/10",
    "2026-10-01",
    " 2026-10",
    "2026-10\n",
    ANCHO_COMPLETO,  # dígitos de ancho completo: `int()` los aceptaría
    "+202-10",
    "-2026-10",
]


@pytest.mark.parametrize("valor", INVALIDOS, ids=[repr(v) for v in INVALIDOS])
def test_un_mes_invalido_es_invalid_month_en_month(valor: str) -> None:
    with pytest.raises(InvalidMonth) as error:
        rules.parse_month(valor)
    assert (error.value.status, error.value.code, error.value.field) == (
        422,
        "validation_error",
        "month",
    )
    if valor.strip():
        assert valor.strip() not in error.value.message


@pytest.mark.parametrize("valor", INVALIDOS, ids=[repr(v) for v in INVALIDOS])
def test_month_bounds_utc_tambien_rechaza_sin_value_error_ni_overflow(valor: str) -> None:
    """M-4: `month_bounds_utc` valida igual; ningún mes extremo llega a un 500."""
    with pytest.raises(InvalidMonth):
        rules.month_bounds_utc(valor)


def test_invalid_month_no_es_value_error_ni_overflow_error() -> None:
    """El 422 sale por el handler de `DomainError`; un `ValueError` sería otra cosa."""
    assert not issubclass(InvalidMonth, ValueError | OverflowError)
