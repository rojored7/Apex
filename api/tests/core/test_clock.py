"""Pruebas de `core/clock.py` (US-013, T4; Q28)."""

from __future__ import annotations

import contextvars
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.clock import (
    FrozenClock,
    SystemClock,
    current_clock,
    get_clock,
    reset_clock,
    set_clock,
    to_bogota_date,
)


def test_now_utc_es_aware_en_utc() -> None:
    ahora = SystemClock().now_utc()
    assert ahora.tzinfo is not None
    assert ahora.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    ("instante", "esperada"),
    [
        (datetime(2026, 10, 21, 2, 30, tzinfo=UTC), date(2026, 10, 20)),
        (datetime(2026, 10, 21, 4, 59, 59, tzinfo=UTC), date(2026, 10, 20)),
        (datetime(2026, 10, 21, 5, 0, 0, tzinfo=UTC), date(2026, 10, 21)),
        (datetime(2026, 10, 21, 23, 59, 59, tzinfo=UTC), date(2026, 10, 21)),
    ],
)
def test_to_bogota_date_en_los_bordes(instante: datetime, esperada: date) -> None:
    assert to_bogota_date(instante) == esperada


def test_to_bogota_date_rechaza_instante_ingenuo() -> None:
    with pytest.raises(ValueError, match="tzinfo"):
        to_bogota_date(datetime(2026, 10, 21, 2, 30))  # noqa: DTZ001


def test_frozen_clock_fijo_hasta_advance() -> None:
    reloj = FrozenClock(datetime(2026, 10, 20, 12, 0, tzinfo=UTC))
    assert reloj.now_utc() == datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    assert reloj.now_utc() == reloj.now_utc()
    assert reloj.today_bogota() == date(2026, 10, 20)
    reloj.advance(days=1)
    assert reloj.today_bogota() == date(2026, 10, 21)
    reloj.advance(hours=12, minutes=30)
    assert reloj.now_utc() == datetime(2026, 10, 22, 0, 30, tzinfo=UTC)
    reloj.set(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    assert reloj.today_bogota() == date(2025, 12, 31)


def test_frozen_clock_normaliza_a_utc_y_rechaza_ingenuos() -> None:
    from zoneinfo import ZoneInfo

    bogota = datetime(2026, 10, 21, 0, 30, tzinfo=ZoneInfo("America/Bogota"))
    reloj = FrozenClock(bogota)
    assert reloj.now_utc() == datetime(2026, 10, 21, 5, 30, tzinfo=UTC)
    assert reloj.now_utc().tzinfo is UTC or reloj.now_utc().utcoffset() == timedelta(0)
    with pytest.raises(ValueError, match="tzinfo"):
        FrozenClock(datetime(2026, 10, 21))  # noqa: DTZ001


def test_current_clock_por_defecto_es_el_sistema() -> None:
    assert isinstance(current_clock(), SystemClock)
    assert get_clock() is current_clock()


def test_set_clock_no_se_filtra_a_otro_contexto() -> None:
    congelado = FrozenClock(datetime(2026, 10, 20, 12, 0, tzinfo=UTC))
    token = set_clock(congelado)
    try:
        assert current_clock() is congelado
        contexto = contextvars.copy_context()
        otro: list[object] = []
        contexto.run(lambda: otro.append(current_clock()))
        assert otro[0] is congelado

        def _en_contexto_limpio() -> object:
            set_clock(SystemClock())
            return current_clock()

        assert isinstance(contextvars.copy_context().run(_en_contexto_limpio), SystemClock)
        assert current_clock() is congelado
    finally:
        reset_clock(token)
    assert isinstance(current_clock(), SystemClock)
