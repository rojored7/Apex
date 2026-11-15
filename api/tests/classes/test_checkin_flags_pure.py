"""Banderas del check-in, puras (S7-C1, US-159; S7-D12, S7-D25, S7-D27). Rojo C1.

Siete banderas (`other_day` es la séptima, S7-D27): el check-in nunca bloquea (RN-09, N-38, N-39).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.modules.classes.rules import (
    CHECKIN_FLAGS,
    MEMBERSHIP_STATUSES,
    capacity_outcome,
    checkin_flags,
    checkin_on_date,
    is_other_day,
    membership_flag,
    within_checkin_window,
)

INICIO = datetime(2026, 10, 21, 23, 0, tzinfo=UTC)  # hoy 18:00 en Bogotá
HOY = date(2026, 10, 21)


def test_son_siete_banderas_y_seis_estados() -> None:
    assert len(CHECKIN_FLAGS) == 7 and "other_day" in CHECKIN_FLAGS
    assert set(MEMBERSHIP_STATUSES) == {
        "active",
        "expiring",
        "expired",
        "frozen",
        "pending_payment",
        "none",
    }


@pytest.mark.parametrize(
    ("estado", "bandera"),
    [
        ("active", None),
        ("expiring", None),
        ("expired", "expired"),
        ("none", "no_membership"),
        ("frozen", "frozen"),
        ("pending_payment", "pending_payment"),
    ],
)
def test_membership_flag_de_los_seis_estados(estado: str, bandera: str | None) -> None:
    assert membership_flag(estado) == bandera


def test_un_estado_desconocido_es_error_de_programacion() -> None:
    with pytest.raises(ValueError, match="estado"):
        membership_flag("vencida")


@pytest.mark.parametrize(
    ("estado", "esperadas"),
    [
        ("active", ()),
        ("expiring", ()),
        ("expired", ("expired",)),
        ("none", ("no_membership",)),
        ("frozen", ("frozen",)),
        ("pending_payment", ("pending_payment",)),
    ],
)
def test_los_seis_estados_registran_siempre_sin_error(
    estado: str, esperadas: tuple[str, ...]
) -> None:
    """Dentro de ventana, con cupo y hoy: solo la bandera del estado; jamás una excepción."""
    assert checkin_flags(estado, 3, 15, INICIO, INICIO, 30, HOY) == esperadas


def test_asistente_16_de_cupo_15_over_capacity() -> None:
    assert capacity_outcome(14, 15) == "available"  # el 15.º cabe
    assert capacity_outcome(15, 15) == "over_capacity"  # el 16.º no
    assert capacity_outcome(40, 15) == "over_capacity"
    assert checkin_flags("active", 15, 15, INICIO, INICIO, 30, HOY) == ("over_capacity",)
    assert checkin_flags("active", 14, 15, INICIO, INICIO, 30, HOY) == ()


def test_bordes_de_la_ventana_incluidos() -> None:
    w = 30
    assert within_checkin_window(INICIO, INICIO - timedelta(minutes=w), w)
    assert within_checkin_window(INICIO, INICIO + timedelta(minutes=w), w)
    assert not within_checkin_window(INICIO, INICIO - timedelta(minutes=w, seconds=1), w)
    assert not within_checkin_window(INICIO, INICIO + timedelta(minutes=w, seconds=1), w)
    assert within_checkin_window(INICIO, INICIO, 0)
    assert not within_checkin_window(INICIO, INICIO + timedelta(seconds=1), 0)


def test_out_of_window_en_el_check_in() -> None:
    tarde = INICIO + timedelta(minutes=31)
    assert checkin_flags("active", 0, 15, INICIO, tarde, 30, HOY) == ("out_of_window",)
    borde = INICIO + timedelta(minutes=30)
    assert checkin_flags("active", 0, 15, INICIO, borde, 30, HOY) == ()


def test_other_day_fuera_de_hoy_o_ayer_en_bogota() -> None:
    assert is_other_day(date(2026, 10, 19), HOY)  # antier
    assert is_other_day(date(2026, 9, 21), HOY)  # hace un mes
    assert is_other_day(date(2026, 10, 22), HOY)  # mañana
    assert is_other_day(date(2026, 11, 3), HOY)  # dentro de 13 días
    mes = checkin_flags("active", 0, 15, INICIO, INICIO, 30, date(2026, 9, 21))
    assert mes == ("other_day",)


def test_ayer_y_hoy_sin_other_day() -> None:
    assert not is_other_day(HOY, HOY)
    assert not is_other_day(date(2026, 10, 20), HOY)
    assert "other_day" not in checkin_flags("active", 0, 15, INICIO, INICIO, 30, date(2026, 10, 20))


def test_el_orden_de_las_banderas_es_el_del_catalogo() -> None:
    flags = checkin_flags(
        "expired", 15, 15, INICIO, INICIO + timedelta(hours=3), 30, date(2026, 9, 21)
    )
    assert flags == ("expired", "over_capacity", "out_of_window", "other_day")
    assert list(flags) == [f for f in CHECKIN_FLAGS if f in flags]


def test_on_date_es_el_minimo_entre_la_sesion_y_hoy() -> None:
    assert checkin_on_date(date(2026, 10, 20), HOY) == date(2026, 10, 20)  # ayer
    assert checkin_on_date(HOY, HOY) == HOY
    assert checkin_on_date(date(2026, 11, 3), HOY) == HOY  # futura: nunca una tiquetera futura
    assert checkin_on_date(date(2026, 9, 21), HOY) == date(2026, 9, 21)
