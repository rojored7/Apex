"""`classes.planned_sessions` pura (S7-B1, US-156; S7-D10). Rojo B1.

Sin base ni reloj. Fechas verificadas a mano (calendario de 2026): el 21 de octubre es
miércoles; los
lunes siguientes son el 26 de octubre y el 2 de noviembre; Bogotá es UTC-5 todo el año, así que las
06:00 locales son las 11:00Z. El 31 de diciembre de 2026 es jueves: las 23:30 locales ya son el 1 de
enero a las 04:30Z, pero `session_date` sigue siendo la fecha civil de Bogotá (el 31).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.modules.classes.service import SlotSpec, planned_sessions

HOY = date(2026, 10, 21)  # miércoles
COACH = UUID("11111111-1111-1111-1111-111111111111")


def _franja(**cambios: object) -> SlotSpec:
    valores: dict[str, object] = {
        "id": uuid4(),
        "weekdays": [0],
        "start_time": "06:00",
        "duration_min": 60,
        "capacity": 15,
        "default_coach_id": None,
        "name": None,
        "valid_from": date(2026, 10, 1),
        "is_active": True,
    }
    valores.update(cambios)
    return SlotSpec(**valores)  # type: ignore[arg-type]


def test_lunes_26_oct_y_2_nov_a_las_11_utc() -> None:
    franja = _franja(capacity=15)
    planeadas = planned_sessions([franja], HOY, HOY + timedelta(days=13))
    assert [p.starts_at for p in planeadas] == [
        datetime(2026, 10, 26, 11, 0, tzinfo=UTC),
        datetime(2026, 11, 2, 11, 0, tzinfo=UTC),
    ]
    assert [p.session_date for p in planeadas] == [date(2026, 10, 26), date(2026, 11, 2)]
    assert all(p.capacity == 15 and p.duration_min == 60 for p in planeadas)
    assert all(p.slot_id == franja.id for p in planeadas)


def test_copia_coach_nombre_y_duracion_de_la_franja() -> None:
    franja = _franja(default_coach_id=COACH, name="Fuerza AM", duration_min=90, capacity=8)
    (p,) = planned_sessions([franja], date(2026, 10, 26), date(2026, 10, 26))
    assert (p.coach_id, p.name, p.duration_min, p.capacity) == (COACH, "Fuerza AM", 90, 8)


def test_cruza_fin_de_mes_y_de_anio() -> None:
    franja = _franja(weekdays=[3], start_time="23:30")  # jueves 23:30 de Bogotá
    planeadas = planned_sessions([franja], date(2026, 12, 28), date(2027, 1, 10))
    assert [p.session_date for p in planeadas] == [date(2026, 12, 31), date(2027, 1, 7)]
    assert [p.starts_at for p in planeadas] == [
        datetime(2027, 1, 1, 4, 30, tzinfo=UTC),  # cruza de año en UTC
        datetime(2027, 1, 8, 4, 30, tzinfo=UTC),
    ]


def test_los_dos_extremos_del_rango_se_incluyen() -> None:
    franja = _franja(weekdays=[0, 1, 2, 3, 4, 5, 6])
    planeadas = planned_sessions([franja], date(2026, 10, 21), date(2026, 11, 3))
    assert len(planeadas) == 14
    assert planeadas[0].session_date == date(2026, 10, 21)
    assert planeadas[-1].session_date == date(2026, 11, 3)


def test_respeta_valid_from() -> None:
    franja = _franja(valid_from=date(2026, 10, 27))  # después del lunes 26
    planeadas = planned_sessions([franja], HOY, HOY + timedelta(days=13))
    assert [p.session_date for p in planeadas] == [date(2026, 11, 2)]


def test_valid_from_es_inclusivo() -> None:
    franja = _franja(valid_from=date(2026, 10, 26))
    planeadas = planned_sessions([franja], HOY, HOY + timedelta(days=13))
    assert [p.session_date for p in planeadas] == [date(2026, 10, 26), date(2026, 11, 2)]


def test_franja_pausada_sin_sesiones() -> None:
    assert planned_sessions([_franja(is_active=False)], HOY, HOY + timedelta(days=13)) == []


def test_varias_franjas_salen_ordenadas_por_hora_y_luego_por_franja() -> None:
    tarde = _franja(start_time="18:00")
    temprano = _franja(start_time="06:00")
    planeadas = planned_sessions([tarde, temprano], date(2026, 10, 26), date(2026, 10, 26))
    assert [p.slot_id for p in planeadas] == [temprano.id, tarde.id]


def test_rango_invertido_o_sin_franjas_no_da_nada() -> None:
    assert planned_sessions([], HOY, HOY + timedelta(days=13)) == []
    assert planned_sessions([_franja()], HOY + timedelta(days=13), HOY) == []


@pytest.mark.parametrize("dia", range(7))
def test_cada_dia_de_la_semana_cae_en_su_fecha(dia: int) -> None:
    """0 lunes ... 6 domingo: en la semana del 26 de octubre al 1 de noviembre."""
    franja = _franja(weekdays=[dia])
    (p,) = planned_sessions([franja], date(2026, 10, 26), date(2026, 11, 1))
    assert p.session_date == date(2026, 10, 26) + timedelta(days=dia)
