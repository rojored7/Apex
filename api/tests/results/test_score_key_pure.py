"""`leaderboard.score_key` (S9-B1, US-180; S9-D6): la clave «grupo y marca» pública. Pura. Rojo B1.

- Da la MISMA clave que `_tie_key_of` para el mismo `score_type` y la misma marca (con un `Mark`).
- Ordena igual que `leaderboard_order` (sin los desempates de nombre): menor es mejor.
- Acepta cualquier objeto con la forma de `ScoreLike` (sin nombres de socio).
- `ValueError` con un `score_type` sin leaderboard; `results.service` exporta `score_key` y
  `validate_score`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest

from app.modules.results import service
from app.modules.results.leaderboard import Mark, _tie_key_of, leaderboard_order, score_key


@dataclass(frozen=True)
class Marca:
    level: str = "rx"
    seconds: int | None = None
    rounds: int | None = None
    reps: int | None = None
    load_g: int | None = None
    capped: bool = False


def como_mark(m: Marca, n: int = 1) -> Mark:
    return Mark(
        result_id=UUID(int=n),
        member_id=UUID(int=1000 + n),
        first_name="Ana",
        last_name="Perez",
        level=m.level,
        seconds=m.seconds,
        rounds=m.rounds,
        reps=m.reps,
        load_g=m.load_g,
        capped=m.capped,
    )


CASOS: list[tuple[str, Marca]] = [
    ("time", Marca(seconds=250)),
    ("time", Marca("scaled", seconds=100)),
    ("time", Marca("rx_plus", seconds=300)),
    ("time", Marca(capped=True, seconds=600, reps=40)),
    ("time", Marca(capped=True, seconds=600, rounds=2, reps=15)),
    ("rounds_reps", Marca(rounds=5, reps=12)),
    ("rounds_reps", Marca("scaled", rounds=9, reps=1)),
    ("reps", Marca(reps=71)),
    ("load", Marca(load_g=100_000)),
    ("load", Marca("scaled", load_g=120_000)),
]


@pytest.mark.parametrize(("tipo", "marca"), CASOS)
def test_misma_clave_que_tie_key_of(tipo: str, marca: Marca) -> None:
    assert score_key(tipo)(marca) == _tie_key_of(tipo)(como_mark(marca))


def test_valores_a_mano_de_la_clave() -> None:
    assert score_key("time")(Marca(seconds=250)) == (0, (0, 250))
    assert score_key("time")(Marca("scaled", seconds=100)) == (1, (0, 100))
    assert score_key("time")(Marca(capped=True, seconds=600, reps=40)) == (0, (1, 0, -40))
    assert score_key("rounds_reps")(Marca(rounds=5, reps=12)) == (0, (-5, -12))
    assert score_key("reps")(Marca(reps=71)) == (0, (-71,))
    assert score_key("load")(Marca("rx_plus", load_g=100_000)) == (0, (-100_000,))


@pytest.mark.parametrize("tipo", ["time", "rounds_reps", "reps", "load"])
def test_mismo_orden_que_leaderboard_order(tipo: str) -> None:
    marcas: dict[str, list[Marca]] = {
        "time": [
            Marca(seconds=300),
            Marca("scaled", seconds=100),
            Marca(capped=True, seconds=600, reps=40),
            Marca("rx_plus", seconds=250),
            Marca(capped=True, seconds=600, reps=55),
        ],
        "rounds_reps": [
            Marca(rounds=5, reps=10),
            Marca(rounds=5, reps=12),
            Marca("scaled", rounds=9, reps=0),
            Marca(rounds=4, reps=30),
        ],
        "reps": [Marca(reps=50), Marca(reps=71), Marca("scaled", reps=90)],
        "load": [Marca(load_g=90_000), Marca("scaled", load_g=120_000), Marca(load_g=100_000)],
    }
    lista = marcas[tipo]
    por_clave = sorted(range(len(lista)), key=lambda i: score_key(tipo)(lista[i]))
    # `leaderboard_order` desempata por nombre e id: con claves distintas el orden es el mismo.
    por_tablero = sorted(
        range(len(lista)), key=lambda i: leaderboard_order(tipo)(como_mark(lista[i], i + 1))
    )
    assert por_clave == por_tablero


def test_empate_da_claves_iguales() -> None:
    assert score_key("time")(Marca(seconds=250)) == score_key("time")(Marca("rx_plus", seconds=250))


@pytest.mark.parametrize("tipo", ["none", "", "TIME"])
def test_score_type_sin_leaderboard_lanza_value_error(tipo: str) -> None:
    with pytest.raises(ValueError, match=r"."):
        score_key(tipo)(Marca(seconds=1))


def test_el_service_exporta_score_key_y_validate_score() -> None:
    assert service.score_key is score_key
    assert callable(service.validate_score)
    exportados: Any = service.__all__
    assert {"score_key", "validate_score"} <= set(exportados)
