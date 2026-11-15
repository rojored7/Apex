"""Contrato de `GET /tv/today` (S8-C2, S8-D18, S8-D19, S8-D41): lista blanca con `extra="forbid"`
en cada nivel. Nunca `member_id`, sexo, notas ni campos cifrados; las cargas van en gramos."""

from __future__ import annotations

from datetime import date as date_type
from typing import Literal

from pydantic import BaseModel, ConfigDict

TvLevel = Literal["rx", "rx_plus", "scaled"]
TvScoreType = Literal["time", "rounds_reps", "reps", "load", "none"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TvMovement(_Strict):
    name: str
    reps: str
    load_rx_m_g: int | None
    load_rx_f_g: int | None


class TvWod(_Strict):
    title: str
    score_type: TvScoreType
    time_cap_s: int | None
    is_benchmark: bool
    description: str
    movements: list[TvMovement]


class TvScore(_Strict):
    seconds: int | None
    rounds: int | None
    reps: int | None
    load_g: int | None
    capped: bool


class TvRow(_Strict):
    position: int
    display_name: str
    level: TvLevel
    score: TvScore


class TvBoard(_Strict):
    date: date_type
    refresh_seconds: int
    show_leaderboard: bool
    wod: TvWod | None
    leaderboard: list[TvRow]
