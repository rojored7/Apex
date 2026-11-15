"""Semana ISO y tiempo de las sesiones, puras (S7-B2, US-157; S7-D11, S7-D32 L-1). Rojo B2.

Calendario verificado a mano: Bogotá es UTC-5 todo el año, el lunes 19 de octubre de 2026 empieza
la semana 43 (00:00 local = 05:00Z). 2026 empieza en jueves y tiene 53 semanas (la 53 va del 28 de
diciembre al 3 de enero); 2025 empieza en miércoles y tiene 52; 2020 es bisiesto y empieza en
miércoles: tiene 53.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.modules.classes.exceptions import ClassValidationError
from app.modules.classes.rules import (
    date_range_utc,
    local_date,
    parse_week,
    session_status,
    validate_extra_start,
    week_of,
    week_range,
)

AHORA = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)  # miércoles, 10:00 en Bogotá


def test_una_semana_normal() -> None:
    assert parse_week("2026-W43") == (2026, 43)
    assert week_range(2026, 43) == (
        datetime(2026, 10, 19, 5, 0, tzinfo=UTC),
        datetime(2026, 10, 26, 5, 0, tzinfo=UTC),
    )


def test_semana_53_existe_y_no_existe() -> None:
    assert parse_week("2026-W53") == (2026, 53)
    assert parse_week("2020-W53") == (2020, 53)
    for mala in ("2025-W53", "2027-W53", "2024-W53"):
        with pytest.raises(ClassValidationError) as error:
            parse_week(mala)
        assert error.value.field == "week", mala


def test_la_semana_53_cruza_el_fin_de_anio() -> None:
    assert week_range(2026, 53) == (
        datetime(2026, 12, 28, 5, 0, tzinfo=UTC),
        datetime(2027, 1, 4, 5, 0, tzinfo=UTC),
    )
    assert week_of(date(2027, 1, 3)) == "2026-W53"
    assert week_of(date(2024, 12, 30)) == "2025-W01"
    assert week_range(2025, 1)[0] == datetime(2024, 12, 30, 5, 0, tzinfo=UTC)


def test_domingo_2330_bogota_es_lunes_utc_pero_sigue_en_su_semana() -> None:
    domingo = datetime(2026, 10, 25, 23, 30, tzinfo=UTC) - timedelta(hours=0)
    domingo = datetime(2026, 10, 26, 4, 30, tzinfo=UTC)  # 23:30 del domingo 25 en Bogotá
    assert domingo.weekday() == 0  # en UTC ya es lunes
    desde, hasta = week_range(2026, 43)
    assert desde <= domingo < hasta
    assert local_date(domingo) == date(2026, 10, 25)
    assert week_of(local_date(domingo)) == "2026-W43"
    siguiente = week_range(2026, 44)
    assert not (siguiente[0] <= domingo < siguiente[1])


@pytest.mark.parametrize(
    "mala",
    [
        "",
        "2026-43",
        "2026-W4",
        "2026-W043",
        "2026W43",
        "2026-w43",
        "26-W43",
        "2026-W00",
        "2026-W54",
        "2026-W99",
        " 2026-W43",
        "2026-W43\n",
        f"2026-W4{chr(0x0663)}",
        f"{chr(0xFF12)}026-W43",
    ],
)
def test_week_mal_formado_da_422_week(mala: str) -> None:
    with pytest.raises(ClassValidationError) as error:
        parse_week(mala)
    assert error.value.field == "week"


@pytest.mark.parametrize("anio", ["2019", "2101", "9999", "0001"])
def test_anio_fuera_de_2020_a_2100_da_422_week(anio: str) -> None:
    with pytest.raises(ClassValidationError) as error:
        parse_week(f"{anio}-W52")
    assert error.value.field == "week"


def test_los_anios_limite_se_aceptan() -> None:
    assert parse_week("2020-W01") == (2020, 1)
    assert parse_week("2100-W52") == (2100, 52)
    week_range(2100, 52)  # no desborda


def test_date_range_utc_es_medio_abierto_y_en_hora_de_bogota() -> None:
    assert date_range_utc(date(2026, 10, 26), date(2026, 10, 26)) == (
        datetime(2026, 10, 26, 5, 0, tzinfo=UTC),
        datetime(2026, 10, 27, 5, 0, tzinfo=UTC),
    )
    assert date_range_utc(date(2026, 12, 31), date(2027, 1, 1))[1] == datetime(
        2027, 1, 2, 5, 0, tzinfo=UTC
    )


def test_local_date_a_las_2330_de_bogota() -> None:
    assert local_date(datetime(2027, 1, 1, 4, 30, tzinfo=UTC)) == date(2026, 12, 31)
    assert local_date(datetime(2027, 1, 1, 5, 0, tzinfo=UTC)) == date(2027, 1, 1)


def test_session_status() -> None:
    inicio = datetime(2026, 10, 21, 11, 0, tzinfo=UTC)
    fin = inicio + timedelta(minutes=60)
    assert session_status("scheduled", inicio, 60, fin - timedelta(seconds=1)) == "scheduled"
    assert session_status("scheduled", inicio, 60, fin) == "done"
    assert session_status("scheduled", inicio, 60, fin + timedelta(days=1)) == "done"
    assert session_status("cancelled", inicio, 60, fin + timedelta(days=1)) == "cancelled"
    assert session_status("cancelled", inicio, 60, inicio - timedelta(days=1)) == "cancelled"
    assert session_status("scheduled", inicio, 60, inicio - timedelta(days=1)) == "scheduled"


def test_la_sesion_extra_va_de_ayer_a_90_dias() -> None:
    ayer = datetime(2026, 10, 20, 5, 0, tzinfo=UTC)  # lunes... ayer martes 00:00 Bogotá
    validate_extra_start(ayer, AHORA)
    validate_extra_start(AHORA + timedelta(days=90), AHORA)
    for mala in (ayer - timedelta(seconds=1), AHORA + timedelta(days=90, seconds=1)):
        with pytest.raises(ClassValidationError) as error:
            validate_extra_start(mala, AHORA)
        assert error.value.field == "starts_at"


@pytest.mark.parametrize(
    "inicio",
    [
        AHORA + timedelta(days=1, seconds=30),
        AHORA + timedelta(days=1, microseconds=1),
    ],
)
def test_la_sesion_extra_no_admite_segundos_ni_microsegundos(inicio: datetime) -> None:
    """S7-B3b (LOW 1): 06:00:30 esquivaba el 409 `session_duplicate` (mismo `starts_at` exacto)."""
    with pytest.raises(ClassValidationError) as error:
        validate_extra_start(inicio, AHORA)
    assert error.value.field == "starts_at"
    validate_extra_start(AHORA + timedelta(days=1), AHORA)
