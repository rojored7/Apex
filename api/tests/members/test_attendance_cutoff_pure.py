"""Fecha de corte del filtro `last_attendance` (S7-R2, US-163; S7-D15). Pura, sin base.

`attendance_cutoff(valor, hoy)` es el primer día civil de Bogotá que cuenta como asistencia
reciente: `hoy - N`. Un socio entra al filtro si su última asistencia es anterior a ese día o si
nunca asistió; `never` no tiene corte (`None`: cualquier asistencia lo saca del filtro).
"""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.members.rules import LAST_ATTENDANCE_DAYS, attendance_cutoff

HOY = date(2026, 10, 21)


@pytest.mark.parametrize(
    ("valor", "esperada"),
    [
        ("7d", date(2026, 10, 14)),
        ("14d", date(2026, 10, 7)),
        ("30d", date(2026, 9, 21)),
        ("60d", date(2026, 8, 22)),
    ],
)
def test_el_corte_es_hoy_menos_n_dias(valor: str, esperada: date) -> None:
    assert attendance_cutoff(valor, HOY) == esperada


def test_never_no_tiene_corte() -> None:
    assert attendance_cutoff("never", HOY) is None


def test_cruza_mes_y_anio_y_el_29_de_febrero() -> None:
    assert attendance_cutoff("30d", date(2027, 1, 10)) == date(2026, 12, 11)
    assert attendance_cutoff("7d", date(2028, 3, 3)) == date(2028, 2, 25)  # bisiesto
    assert attendance_cutoff("60d", date(2028, 3, 1)) == date(2028, 1, 1)


def test_los_valores_admitidos_son_exactamente_cuatro_dias() -> None:
    assert dict(LAST_ATTENDANCE_DAYS) == {"7d": 7, "14d": 14, "30d": 30, "60d": 60}


@pytest.mark.parametrize("valor", ["mucho", "", "7", "7D", "90d", " 7d", "NEVER", "0d"])
def test_un_valor_desconocido_es_value_error(valor: str) -> None:
    with pytest.raises(ValueError, match="last_attendance"):
        attendance_cutoff(valor, HOY)
