"""`weekly_summary`, `week_starts` y `check_summary_range`, puras (S7-R1, US-162; S7-D15, M-5).

Calendario: el lunes 19 de octubre de 2026 empieza la semana ISO 43; el 12 es la 42. La función
pura solo arma grupos desde filas ya agregadas por SQL; no ve asistencias sueltas.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest

from app.modules.classes.exceptions import ClassValidationError
from app.modules.classes.reports import (
    EXTRA_LABEL,
    SUMMARY_MAX_WEEKS,
    SummaryRow,
    check_summary_range,
    week_starts,
    weekly_summary,
)

W42 = date(2026, 10, 12)
W43 = date(2026, 10, 19)


def _fila(
    week_start: date = W43,
    *,
    slot_id: UUID | None = None,
    name: str | None = None,
    start_time: str | None = None,
    sessions: int = 1,
    attendance: int = 0,
    flagged: int = 0,
    capacity: int = 15,
) -> SummaryRow:
    return SummaryRow(
        week_start=week_start,
        slot_id=slot_id,
        slot_name=name,
        slot_start_time=start_time,
        sessions=sessions,
        attendance=attendance,
        flagged=flagged,
        capacity_sum=capacity,
    )


def test_semanas_vacias() -> None:
    assert weekly_summary([]) == []
    vacias = weekly_summary([], weeks=[W42, W43])
    assert [(s.week, s.week_start, s.total, s.flagged, s.slots) for s in vacias] == [
        ("2026-W42", W42, 0, 0, []),
        ("2026-W43", W43, 0, 0, []),
    ]


def test_las_semanas_piden_aparecen_aunque_la_fila_sea_de_otra() -> None:
    semanas = weekly_summary([_fila(W43, attendance=3)], weeks=[W42, W43])
    assert [(s.week, s.total) for s in semanas] == [("2026-W42", 0), ("2026-W43", 3)]


def test_cupo_0_no_divide() -> None:
    (semana,) = weekly_summary([_fila(attendance=4, capacity=0, sessions=0)])
    assert semana.slots[0].occupancy_pct == 0
    assert semana.total == 4


@pytest.mark.parametrize(
    ("asistentes", "cupo", "esperado"),
    [(0, 15, 0), (15, 15, 100), (7, 15, 47), (8, 15, 53), (1, 2, 50), (1, 3, 33), (2, 3, 67)],
)
def test_ocupacion_entera_redondeada(asistentes: int, cupo: int, esperado: int) -> None:
    (semana,) = weekly_summary([_fila(attendance=asistentes, capacity=cupo)])
    assert semana.slots[0].occupancy_pct == esperado


def test_sobrecupo_supera_100() -> None:
    (semana,) = weekly_summary([_fila(attendance=16, capacity=15)])
    assert semana.slots[0].occupancy_pct == 107


def test_extras_bajo_extra() -> None:
    una, otra = _fila(attendance=2, capacity=15), _fila(attendance=3, capacity=15, name="x")
    (semana,) = weekly_summary([una, otra])
    assert [s.label for s in semana.slots] == [EXTRA_LABEL]
    (extra,) = semana.slots
    assert (extra.slot_id, extra.start_time) == (None, None)
    assert (extra.sessions, extra.attendance, extra.capacity_sum) == (2, 5, 30)
    assert extra.occupancy_pct == 17


def test_franja_con_nombre_o_con_hora_y_orden_por_hora_con_extra_al_final() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    filas = [
        _fila(slot_id=None, attendance=1),
        _fila(slot_id=a, name="WOD", start_time="18:00", attendance=5),
        _fila(slot_id=b, name=None, start_time="06:00", attendance=7),
        _fila(slot_id=c, name="Open", start_time="06:00", attendance=2),
    ]
    (semana,) = weekly_summary(filas)
    assert [(s.label, s.start_time) for s in semana.slots] == [
        ("06:00", "06:00"),
        ("Open", "06:00"),
        ("WOD", "18:00"),
        (EXTRA_LABEL, None),
    ]
    assert semana.total == 15


def test_totales_de_la_semana_suman_las_franjas() -> None:
    a = uuid4()
    filas = [
        _fila(W42, slot_id=a, start_time="06:00", attendance=4, flagged=1),
        _fila(W42, attendance=2, flagged=2),
        _fila(W43, slot_id=a, start_time="06:00", attendance=9, flagged=0),
    ]
    s42, s43 = weekly_summary(filas)
    assert (s42.total, s42.flagged, len(s42.slots)) == (6, 3, 2)
    assert (s43.total, s43.flagged, len(s43.slots)) == (9, 0, 1)


def test_week_starts_son_los_lunes_del_rango() -> None:
    assert week_starts(date(2026, 10, 14), date(2026, 10, 20)) == [W42, W43]
    assert week_starts(date(2026, 10, 19), date(2026, 10, 25)) == [W43]
    assert week_starts(date(2026, 10, 25), date(2026, 10, 26)) == [W43, date(2026, 10, 26)]


def test_rango_valido_no_lanza() -> None:
    check_summary_range(W43, W43)
    desde = date(2026, 4, 27)
    check_summary_range(desde, desde + timedelta(days=7 * SUMMARY_MAX_WEEKS - 1))


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        (date(2026, 10, 31), date(2026, 10, 1)),
        (date(2026, 4, 27), date(2026, 4, 27) + timedelta(days=7 * SUMMARY_MAX_WEEKS)),
        (date(2019, 12, 31), date(2020, 1, 5)),
        (date(2026, 1, 1), date(2101, 1, 1)),
        (date(2100, 12, 31), date(2101, 1, 2)),
    ],
)
def test_rango_invalido_da_422_con_field_from(desde: date, hasta: date) -> None:
    with pytest.raises(ClassValidationError) as caught:
        check_summary_range(desde, hasta)
    assert caught.value.status == 422
    assert caught.value.field == "from"
