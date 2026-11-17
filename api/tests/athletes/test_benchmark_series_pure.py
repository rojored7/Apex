"""`benchmark_series` y `summarize_benchmarks`: reglas puras de la serie (S9-C1, US-183; S9-D27).

Sin base ni bus; valores a mano. La entrada llega en orden cronológico ascendente y se conserva.
- Exactamente UN `is_best` por serie, el de menor `results.score_key` del tipo; en empate, el
  primero de la entrada. El grupo de nivel pesa antes que la marca (un `rx` lento le gana a un
  `scaled` rápido, Q20).
- `level_changed`: el nivel difiere del intento anterior; el primero nunca.
- Un solo intento: es el mejor y no cambió de nivel. Entrada vacía: salida vacía.
- `summarize_benchmarks`: por benchmark, intentos, el mejor y la última fecha; ignora marcas sin
  benchmark o de un benchmark sin tipo; orden de primera aparición.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.modules.athletes.rules import Attempt, benchmark_series, summarize_benchmarks
from app.modules.results.schemas import ResultMark

SOCIO = UUID(int=4)
FRAN = UUID(int=100)
GRACE = UUID(int=200)
DIA0 = date(2026, 9, 1)


def marca(numero: int, dia: int = 0, **cambios: Any) -> ResultMark:
    """Una marca con `result_id = UUID(int=numero)` y `wod_date = DIA0 + dia`."""
    valores: dict[str, Any] = {
        "result_id": UUID(int=numero),
        "member_id": SOCIO,
        "wod_id": uuid4(),
        "wod_date": DIA0 + timedelta(days=dia),
        "benchmark_id": FRAN,
        "level": "rx",
        "seconds": None,
        "rounds": None,
        "reps": None,
        "load_g": None,
        "capped": False,
        "status": "validated",
        "is_current": True,
        "supersedes_id": None,
        "validated_by": UUID(int=5),
        "source": "desk",
    }
    valores.update(cambios)
    return ResultMark(**valores)


def mejores(serie: list[Attempt]) -> list[int]:
    return [i for i, a in enumerate(serie) if a.is_best]


# --- por tipo de marca ------------------------------------------------------------------------


def test_time_el_menor_tiempo_es_el_mejor() -> None:
    marcas = [marca(1, 0, seconds=280), marca(2, 7, seconds=260), marca(3, 14, seconds=245)]

    serie = benchmark_series(marcas, "time")

    assert [a.mark.seconds for a in serie] == [280, 260, 245]
    assert mejores(serie) == [2]


def test_time_con_tope_de_tiempo_pierde_ante_quien_termino() -> None:
    marcas = [
        marca(1, 0, seconds=600, capped=True, rounds=2, reps=10),
        marca(2, 7, seconds=590),
    ]

    assert mejores(benchmark_series(marcas, "time")) == [1]


def test_time_entre_dos_con_tope_gana_el_de_mas_trabajo() -> None:
    marcas = [
        marca(1, 0, seconds=600, capped=True, rounds=2, reps=10),
        marca(2, 7, seconds=600, capped=True, rounds=3, reps=0),
        marca(3, 14, seconds=600, capped=True, rounds=2, reps=40),
    ]

    assert mejores(benchmark_series(marcas, "time")) == [1]


def test_rounds_reps_gana_mas_rondas_y_luego_mas_repeticiones() -> None:
    marcas = [
        marca(1, 0, rounds=5, reps=10),
        marca(2, 7, rounds=6, reps=2),
        marca(3, 14, rounds=6, reps=9),
        marca(4, 21, rounds=4, reps=30),
    ]

    assert mejores(benchmark_series(marcas, "rounds_reps")) == [2]


def test_reps_gana_mas_repeticiones() -> None:
    marcas = [marca(1, 0, reps=50), marca(2, 7, reps=80), marca(3, 14, reps=65)]

    assert mejores(benchmark_series(marcas, "reps")) == [1]


def test_load_gana_la_mayor_carga() -> None:
    marcas = [
        marca(1, 0, load_g=100_000),
        marca(2, 7, load_g=120_500),
        marca(3, 14, load_g=110_000),
    ]

    assert mejores(benchmark_series(marcas, "load")) == [1]


def test_un_tipo_sin_leaderboard_falla_con_valueerror() -> None:
    with pytest.raises(ValueError, match="sin leaderboard"):
        benchmark_series([marca(1, seconds=100)], "inventado")


# --- un solo intento, vacío, empates ----------------------------------------------------------


def test_un_solo_intento_es_el_mejor_y_no_cambio_de_nivel() -> None:
    serie = benchmark_series([marca(1, seconds=300)], "time")

    assert len(serie) == 1
    assert (serie[0].is_best, serie[0].level_changed) == (True, False)


def test_sin_intentos_la_serie_esta_vacia() -> None:
    assert benchmark_series([], "time") == []


def test_empate_exacto_solo_el_primero_en_fecha_es_el_mejor() -> None:
    marcas = [
        marca(9, 0, seconds=300),
        marca(1, 7, seconds=300),
        marca(2, 14, seconds=320),
        marca(3, 21, seconds=300),
    ]

    serie = benchmark_series(marcas, "time")

    assert mejores(serie) == [0]
    assert sum(a.is_best for a in serie) == 1


def test_empate_se_decide_por_el_orden_de_entrada_no_por_el_id() -> None:
    """El primero de la ENTRADA gana aunque su `result_id` sea mayor (orden cronológico)."""
    marcas = [marca(50, 0, load_g=90_000), marca(1, 7, load_g=90_000)]

    assert mejores(benchmark_series(marcas, "load")) == [0]


# --- nivel ------------------------------------------------------------------------------------


def test_level_changed_marca_cada_cambio_de_nivel_menos_el_primero() -> None:
    marcas = [
        marca(1, 0, level="scaled", seconds=400),
        marca(2, 7, level="scaled", seconds=380),
        marca(3, 14, level="rx", seconds=420),
        marca(4, 21, level="rx_plus", seconds=410),
        marca(5, 28, level="rx_plus", seconds=400),
    ]

    serie = benchmark_series(marcas, "time")

    assert [a.level_changed for a in serie] == [False, False, True, True, False]


def test_el_grupo_de_nivel_pesa_antes_que_la_marca() -> None:
    """Un `rx` lento es mejor que un `scaled` rápido (Q20: manda `score_key`)."""
    marcas = [marca(1, 0, level="scaled", seconds=150), marca(2, 7, level="rx", seconds=400)]

    assert mejores(benchmark_series(marcas, "time")) == [1]


# --- contrato general -------------------------------------------------------------------------


def test_conserva_el_orden_de_entrada_y_no_muta_la_lista() -> None:
    marcas = [marca(3, 0, seconds=300), marca(1, 7, seconds=250), marca(2, 14, seconds=275)]
    copia = list(marcas)

    serie = benchmark_series(marcas, "time")

    assert marcas == copia
    assert [a.mark.result_id for a in serie] == [UUID(int=3), UUID(int=1), UUID(int=2)]
    assert all(isinstance(a, Attempt) for a in serie)


def test_cada_intento_trae_la_marca_original() -> None:
    marcas = [marca(1, 0, seconds=300), marca(2, 7, seconds=280)]

    assert [a.mark for a in benchmark_series(marcas, "time")] == marcas


# --- summarize_benchmarks ---------------------------------------------------------------------


def test_resumen_cuenta_intentos_mejor_y_ultima_fecha_por_benchmark() -> None:
    marcas = [
        marca(1, 0, benchmark_id=FRAN, seconds=300),
        marca(2, 3, benchmark_id=GRACE, seconds=200),
        marca(3, 7, benchmark_id=FRAN, seconds=250),
        marca(4, 10, benchmark_id=FRAN, seconds=270),
    ]

    resumen = summarize_benchmarks(marcas, {FRAN: "time", GRACE: "time"})

    assert [r.benchmark_id for r in resumen] == [FRAN, GRACE]
    fran, grace = resumen
    assert (fran.attempts, fran.best.result_id, fran.last_on) == (
        3,
        UUID(int=3),
        DIA0 + timedelta(days=10),
    )
    assert (grace.attempts, grace.best.result_id, grace.last_on) == (
        1,
        UUID(int=2),
        DIA0 + timedelta(days=3),
    )


def test_resumen_usa_el_tipo_de_cada_benchmark() -> None:
    marcas = [
        marca(1, 0, benchmark_id=FRAN, seconds=300),
        marca(2, 1, benchmark_id=FRAN, seconds=250),
        marca(3, 2, benchmark_id=GRACE, load_g=80_000),
        marca(4, 3, benchmark_id=GRACE, load_g=95_000),
    ]

    resumen = summarize_benchmarks(marcas, {FRAN: "time", GRACE: "load"})

    assert [r.best.result_id for r in resumen] == [UUID(int=2), UUID(int=4)]


def test_resumen_empate_gana_el_primero_de_la_entrada() -> None:
    marcas = [marca(7, 0, seconds=300), marca(1, 5, seconds=300)]

    (fila,) = summarize_benchmarks(marcas, {FRAN: "time"})

    assert (fila.attempts, fila.best.result_id) == (2, UUID(int=7))


def test_resumen_ignora_marcas_sin_benchmark_o_sin_tipo() -> None:
    marcas = [
        marca(1, 0, benchmark_id=None, seconds=100),
        marca(2, 1, benchmark_id=GRACE, seconds=100),
        marca(3, 2, benchmark_id=FRAN, seconds=300),
    ]

    resumen = summarize_benchmarks(marcas, {FRAN: "time"})

    assert [r.benchmark_id for r in resumen] == [FRAN]


def test_resumen_vacio() -> None:
    assert summarize_benchmarks([], {FRAN: "time"}) == []
