"""`inventory.job_percent(total, done)` pura (S6-B2, US-144; S6-D16). Rojo B2.

0 con `total = 0`; `done * 100 // total` (división entera hacia abajo); 100 con `done = total`;
nunca más de 100; una entrada negativa es `ValueError`. Sin base de datos ni reloj.
"""

from __future__ import annotations

import pytest

from app.core.crypto.inventory import job_percent


@pytest.mark.parametrize(
    ("total", "done", "esperado"),
    [
        (0, 0, 0),
        (0, 5, 0),
        (10, 0, 0),
        (10, 1, 10),
        (3, 1, 33),
        (3, 2, 66),
        (3, 3, 100),
        (7, 1, 14),
        (200, 200, 100),
        (1, 0, 0),
        (1, 1, 100),
        (1_000_000, 999_999, 99),
        (10, 15, 100),
        (3, 99, 100),
    ],
)
def test_tabla_de_job_percent(total: int, done: int, esperado: int) -> None:
    resultado = job_percent(total, done)

    assert resultado == esperado
    assert type(resultado) is int


def test_el_porcentaje_es_done_por_cien_entre_total_y_nunca_pasa_de_cien() -> None:
    for total in range(1, 60):
        anterior = -1
        for done in range(total + 1):
            resultado = job_percent(total, done)

            assert resultado == done * 100 // total, (total, done)
            assert 0 <= resultado <= 100, (total, done)
            assert resultado >= anterior, (total, done)  # no decrece al avanzar
            anterior = resultado
        assert job_percent(total, total) == 100


def test_total_cero_da_cero_sin_dividir() -> None:
    assert job_percent(0, 0) == 0


@pytest.mark.parametrize(
    ("total", "done"), [(-1, 0), (10, -1), (-5, -5), (0, -1), (-1, 5)], ids=str
)
def test_entradas_negativas_son_value_error(total: int, done: int) -> None:
    with pytest.raises(ValueError):
        job_percent(total, done)
