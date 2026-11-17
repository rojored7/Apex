"""Orden del leaderboard (S8-B4, US-171, S8-D13, N-43). Puro: sin sesión, reloj ni base.

- Grupo: `rx` y `rx_plus` van juntos y se ordenan solo por marca; `scaled` va después.
- `time`: primero los que terminaron, por `seconds` ascendente; después los `capped` (cortados por
  time cap), por `(rounds o 0, reps)` descendente («DNF · 2 + 15»).
- `rounds_reps`: `(rounds, reps)` descendente. `reps`: `reps`. `load`: `load_g`, descendente.
- Posición de competencia (1, 2, 2, 4): dos filas empatan solo con el mismo grupo y la misma marca;
  la posición sigue la lista completa (el primer escalado va después del último RX). El desempate
  de la presentación es apellido, nombre (sin tildes ni mayúsculas) e id: estable y sin azar.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

_SCALED = "scaled"


@dataclass(frozen=True, slots=True)
class Mark:
    result_id: UUID
    member_id: UUID
    first_name: str
    last_name: str
    level: str
    seconds: int | None
    rounds: int | None
    reps: int | None
    load_g: int | None
    capped: bool


@dataclass(frozen=True, slots=True)
class Ranked:
    position: int
    mark: Mark


class ScoreLike(Protocol):
    """Lo que `score_key` lee de una marca: sin nombres de socio (S9-D6). Solo lectura: acepta
    tanto un `Mark` congelado como un récord."""

    @property
    def level(self) -> str: ...
    @property
    def seconds(self) -> int | None: ...
    @property
    def rounds(self) -> int | None: ...
    @property
    def reps(self) -> int | None: ...
    @property
    def load_g(self) -> int | None: ...
    @property
    def capped(self) -> bool: ...


def _fold(text: str) -> str:
    """Minúsculas y sin diacríticos, solo para comparar nombres."""
    base = unicodedata.normalize("NFKD", text)
    return "".join(c for c in base if not unicodedata.combining(c)).casefold()


def _time_key(m: ScoreLike) -> tuple[Any, ...]:
    if m.capped:
        return (1, -(m.rounds or 0), -(m.reps or 0))
    return (0, m.seconds or 0)


def _tie_key_of(score_type: str) -> Callable[[ScoreLike], tuple[Any, ...]]:
    """Grupo y marca: lo que decide el empate."""
    match score_type:
        case "time":
            mark_key = _time_key
        case "rounds_reps":

            def mark_key(m: ScoreLike) -> tuple[Any, ...]:
                return (-(m.rounds or 0), -(m.reps or 0))

        case "reps":

            def mark_key(m: ScoreLike) -> tuple[Any, ...]:
                return (-(m.reps or 0),)

        case "load":

            def mark_key(m: ScoreLike) -> tuple[Any, ...]:
                return (-(m.load_g or 0),)

        case _:
            raise ValueError(f"score_type sin leaderboard: {score_type}")

    def key(m: ScoreLike) -> tuple[Any, ...]:
        return (1 if m.level == _SCALED else 0, mark_key(m))

    return key


def leaderboard_order(score_type: str) -> Callable[[Mark], tuple[Any, ...]]:
    """Clave de orden completa (grupo, marca, apellido, nombre, id) para `sorted`."""
    tie_key = _tie_key_of(score_type)

    def key(m: Mark) -> tuple[Any, ...]:
        return (tie_key(m), _fold(m.last_name), _fold(m.first_name), m.result_id)

    return key


def rank_rows(score_type: str, marks: Sequence[Mark]) -> list[Ranked]:
    """Las filas ordenadas con su posición de competencia."""
    tie_key = _tie_key_of(score_type)
    ordenadas = sorted(marks, key=leaderboard_order(score_type))
    salida: list[Ranked] = []
    for indice, marca in enumerate(ordenadas):
        if indice > 0 and tie_key(marca) == tie_key(ordenadas[indice - 1]):
            posicion = salida[-1].position
        else:
            posicion = indice + 1
        salida.append(Ranked(posicion, marca))
    return salida


def score_key(score_type: str) -> Callable[[ScoreLike], tuple[Any, ...]]:
    """Clave pública «grupo y marca» (menor es mejor): la misma de `_tie_key_of` pero sobre
    cualquier objeto con la forma de `ScoreLike`, sin armar un `Mark` con nombres vacíos
    (S9-D6, US-180). `ValueError` con un `score_type` sin leaderboard."""
    return _tie_key_of(score_type)
