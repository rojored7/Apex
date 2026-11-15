"""Orden y posiciones del leaderboard (S8-B4, US-171, S8-D13, N-43). Puras: sin base."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.results.leaderboard import Mark, rank_rows


def _id(n: int) -> UUID:
    return UUID(int=n)


def marca(n: int, apellido: str = "Perez", nombre: str = "Ana", **campos: Any) -> Mark:
    base: dict[str, Any] = {
        "result_id": _id(n),
        "member_id": _id(1000 + n),
        "first_name": nombre,
        "last_name": apellido,
        "level": "rx",
        "seconds": None,
        "rounds": None,
        "reps": None,
        "load_g": None,
        "capped": False,
    }
    base.update(campos)
    return Mark(**base)


def orden(score_type: str, *marcas: Mark) -> list[tuple[int, int]]:
    """`(posición, n)` de cada fila, con `n` = el número con que se armó el id del resultado."""
    return [(r.position, r.mark.result_id.int) for r in rank_rows(score_type, marcas)]


def test_empates_1_2_2_4() -> None:
    filas = orden(
        "time",
        marca(1, seconds=200),
        marca(2, apellido="Gomez", seconds=210),
        marca(3, apellido="Alvarez", seconds=210),
        marca(4, seconds=230),
    )
    assert filas == [(1, 1), (2, 3), (2, 2), (4, 4)]


def test_rx_y_rx_plus_juntos_scaled_despues() -> None:
    filas = orden(
        "time",
        marca(1, level="scaled", seconds=100),
        marca(2, level="rx", seconds=250),
        marca(3, level="rx_plus", seconds=240),
        marca(4, level="scaled", seconds=120),
    )
    assert [n for _p, n in filas] == [3, 2, 1, 4]
    # La posición sigue la lista completa: el escalado más rápido es el tercero, no el primero.
    assert [p for p, _n in filas] == [1, 2, 3, 4]


def test_misma_marca_en_grupos_distintos_no_empata() -> None:
    filas = orden("time", marca(1, level="rx", seconds=200), marca(2, level="scaled", seconds=200))
    assert filas == [(1, 1), (2, 2)]


def test_rx_y_rx_plus_con_la_misma_marca_empatan() -> None:
    filas = orden(
        "time",
        marca(1, level="rx", seconds=200),
        marca(2, level="rx_plus", seconds=200),
        marca(3, level="rx", seconds=250),
    )
    assert [p for p, _n in filas] == [1, 1, 3]


def test_capped_tras_los_que_terminaron_por_reps() -> None:
    filas = orden(
        "time",
        marca(1, capped=True, seconds=600, reps=40),
        marca(2, seconds=590),
        marca(3, capped=True, seconds=600, reps=55),
        marca(4, seconds=300),
        marca(5, capped=True, seconds=600, rounds=2, reps=15),
    )
    # Terminados por tiempo; después los cortados por (rondas o 0, reps) descendente.
    assert [n for _p, n in filas] == [4, 2, 5, 3, 1]


def test_capped_con_mismas_reps_empatan() -> None:
    filas = orden(
        "time",
        marca(1, apellido="Zapata", capped=True, seconds=600, reps=40),
        marca(2, apellido="Aguirre", capped=True, seconds=600, reps=40),
    )
    assert filas == [(1, 2), (1, 1)]


def test_rounds_reps_y_load_descendente() -> None:
    rr = orden(
        "rounds_reps",
        marca(1, rounds=5, reps=10),
        marca(2, rounds=6, reps=0),
        marca(3, rounds=5, reps=12),
    )
    assert [n for _p, n in rr] == [2, 3, 1]
    reps = orden("reps", marca(1, reps=30), marca(2, reps=45), marca(3, reps=30))
    assert [p for p, _n in reps] == [1, 2, 2] and reps[0][1] == 2
    carga = orden("load", marca(1, load_g=100_000), marca(2, load_g=142_500), marca(3, load_g=0))
    assert [n for _p, n in carga] == [2, 1, 3]
    assert [p for p, _n in carga] == [1, 2, 3]


def test_desempate_por_apellido_nombre_e_id() -> None:
    filas = orden(
        "reps",
        marca(5, apellido="Moreno", nombre="Zoe", reps=10),
        marca(4, apellido="Moreno", nombre="Ana", reps=10),
        marca(3, apellido="Álvarez", nombre="Luis", reps=10),
        marca(2, apellido="Moreno", nombre="Ana", reps=10),
        marca(1, apellido="zapata", nombre="Eva", reps=10),
    )
    # Sin tildes ni mayúsculas en la comparación; mismo apellido y nombre: el id manda.
    assert [n for _p, n in filas] == [3, 2, 4, 5, 1]
    assert {p for p, _n in filas} == {1}


def test_lista_vacia() -> None:
    assert rank_rows("time", []) == []
