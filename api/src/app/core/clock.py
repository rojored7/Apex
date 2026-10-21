"""Reloj del sistema y fecha civil de Bogotá (US-013, Q28). Stub: se implementa en S0-B1."""

from __future__ import annotations

from contextvars import Token
from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    def now_utc(self) -> datetime: ...

    def today_bogota(self) -> date: ...


def to_bogota_date(instant_utc: datetime) -> date:
    raise NotImplementedError


class SystemClock:
    def now_utc(self) -> datetime:
        raise NotImplementedError

    def today_bogota(self) -> date:
        raise NotImplementedError


class FrozenClock:
    def __init__(self, instant: datetime) -> None:
        raise NotImplementedError

    def now_utc(self) -> datetime:
        raise NotImplementedError

    def today_bogota(self) -> date:
        raise NotImplementedError

    def advance(self, *, days: int = 0, hours: int = 0, minutes: int = 0) -> None:
        raise NotImplementedError

    def set(self, instant: datetime) -> None:
        raise NotImplementedError


def current_clock() -> Clock:
    raise NotImplementedError


def set_clock(clock: Clock) -> Token[Clock]:
    raise NotImplementedError


def reset_clock(token: Token[Clock]) -> None:
    raise NotImplementedError


def get_clock() -> Clock:
    raise NotImplementedError
