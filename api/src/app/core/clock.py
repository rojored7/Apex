"""Reloj del sistema y fecha civil de Bogotá (US-013, Q28).

Único lugar del api que llama a `datetime.now()`
(`tests/architecture/test_no_direct_now.py`). El "hoy" de negocio es siempre la
fecha civil en `America/Bogota`, sin horario de verano, y la dan
`today_bogota()` del reloj actual o la función pura `to_bogota_date`.

El bus de eventos (US-014), la auditoría (US-015) y el worker toman la hora de
`current_clock()`; los routers usan la dependencia `get_clock`. Las pruebas
congelan el tiempo con `set_clock(FrozenClock(...))` o con
`app.dependency_overrides[get_clock]`. El accesor es un `ContextVar`, así que un
reloj fijado en un contexto no se filtra a otro.

`func.now()` en SQL solo vale para `created_at` y `updated_at` técnicos; nunca
para calcular "hoy".
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")


def to_bogota_date(instant_utc: datetime) -> date:
    """Fecha civil de Bogotá de un instante con zona. Rechaza instantes ingenuos."""
    if instant_utc.tzinfo is None or instant_utc.utcoffset() is None:
        raise ValueError("el instante debe llevar tzinfo; nunca un datetime ingenuo")
    return instant_utc.astimezone(BOGOTA).date()


class Clock(Protocol):
    def now_utc(self) -> datetime: ...

    def today_bogota(self) -> date: ...


class SystemClock:
    def now_utc(self) -> datetime:
        return datetime.now(UTC)

    def today_bogota(self) -> date:
        return to_bogota_date(self.now_utc())


class FrozenClock:
    """Reloj fijo para pruebas y jobs simulados."""

    def __init__(self, instant: datetime) -> None:
        self._instant = self._a_utc(instant)

    @staticmethod
    def _a_utc(instant: datetime) -> datetime:
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("FrozenClock exige un instante con tzinfo")
        return instant.astimezone(UTC)

    def now_utc(self) -> datetime:
        return self._instant

    def today_bogota(self) -> date:
        return to_bogota_date(self._instant)

    def advance(self, *, days: int = 0, hours: int = 0, minutes: int = 0) -> None:
        self._instant = self._instant + timedelta(days=days, hours=hours, minutes=minutes)

    def set(self, instant: datetime) -> None:
        self._instant = self._a_utc(instant)


_SISTEMA = SystemClock()
_reloj: ContextVar[Clock] = ContextVar("apex_clock")


def current_clock() -> Clock:
    return _reloj.get(_SISTEMA)


def set_clock(clock: Clock) -> Token[Clock]:
    return _reloj.set(clock)


def reset_clock(token: Token[Clock]) -> None:
    _reloj.reset(token)


def get_clock() -> Clock:
    """Dependencia de FastAPI: `clock: Clock = Depends(get_clock)`."""
    return current_clock()
