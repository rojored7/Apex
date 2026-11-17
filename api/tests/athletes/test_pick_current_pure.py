"""`rules.pick_current` (S9-B1, US-180; S9-D10, N-45): el récord vigente. Pura: sin base. Rojo B1.

- RM: el mayor `value_g`. Benchmark: el de menor `results.service.score_key(score_type)`
  (grupo `rx`/`rx_plus` antes que `scaled`; `time`: terminó antes que `capped`; `rounds_reps`,
  `reps` y `load` por mayor marca).
- Empate (misma marca y mismo grupo): el `achieved_on` más antiguo y luego el `created_at` más
  antiguo (N-45). Manual y derivado se tratan igual.
- Los invalidados no cuentan; vacía o solo invalidados da `None`.
- Con filas de benchmark `score_type` es obligatorio (`ValueError`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest

from app.modules.athletes.rules import RecordRow, pick_current

MOV = UUID(int=500)
BENCH = UUID(int=600)
INSTANTE = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)


def rm(n: int, value_g: int, **cambios: Any) -> RecordRow:
    base: dict[str, Any] = {
        "id": UUID(int=n),
        "kind": "rm",
        "movement_id": MOV,
        "benchmark_id": None,
        "value_g": value_g,
        "level": None,
        "seconds": None,
        "rounds": None,
        "reps": None,
        "load_g": None,
        "capped": False,
        "achieved_on": date(2026, 5, 1),
        "created_at": INSTANTE,
    }
    base.update(cambios)
    return RecordRow(**base)


def bench(n: int, level: str = "rx", **marca: Any) -> RecordRow:
    base: dict[str, Any] = {
        "id": UUID(int=n),
        "kind": "benchmark",
        "movement_id": None,
        "benchmark_id": BENCH,
        "value_g": None,
        "level": level,
        "seconds": None,
        "rounds": None,
        "reps": None,
        "load_g": None,
        "capped": False,
        "achieved_on": date(2026, 5, 1),
        "created_at": INSTANTE,
    }
    base.update(marca)
    return RecordRow(**base)


def ganador(filas: list[RecordRow], score_type: str | None = None) -> int | None:
    elegido = pick_current(filas, score_type=score_type)
    return None if elegido is None else elegido.id.int


# RM --------------------------------------------------------------------------------------------


def test_rm_gana_el_mayor_value_g() -> None:
    assert ganador([rm(1, 80_000), rm(2, 100_000), rm(3, 90_000)]) == 2


def test_rm_con_un_solo_record_es_el_vigente() -> None:
    assert ganador([rm(7, 1)]) == 7


def test_rm_empate_gana_el_achieved_on_mas_antiguo() -> None:
    filas = [
        rm(1, 100_000, achieved_on=date(2026, 5, 1)),
        rm(2, 100_000, achieved_on=date(2026, 3, 1)),
        rm(3, 100_000, achieved_on=date(2026, 4, 1)),
    ]
    assert ganador(filas) == 2


def test_rm_empate_de_valor_y_fecha_gana_el_created_at_mas_antiguo() -> None:
    filas = [
        rm(1, 100_000, created_at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC)),
        rm(2, 100_000, created_at=datetime(2026, 10, 20, 9, 0, tzinfo=UTC)),
        rm(3, 100_000, created_at=datetime(2026, 10, 20, 11, 0, tzinfo=UTC)),
    ]
    assert ganador(filas) == 2


def test_rm_un_valor_mayor_gana_aunque_sea_mas_reciente() -> None:
    filas = [
        rm(1, 100_000, achieved_on=date(2026, 1, 1)),
        rm(2, 100_001, achieved_on=date(2026, 9, 1)),
    ]
    assert ganador(filas) == 2


def test_rm_manual_y_derivado_se_tratan_igual() -> None:
    assert ganador([rm(1, 100_000, source="manual"), rm(2, 110_000, source="derived")]) == 2
    assert ganador([rm(1, 110_000, source="manual"), rm(2, 100_000, source="derived")]) == 1
    # Empate exacto: no manda el origen, manda el más antiguo.
    filas = [
        rm(1, 100_000, source="derived", achieved_on=date(2026, 6, 1)),
        rm(2, 100_000, source="manual", achieved_on=date(2026, 2, 1)),
    ]
    assert ganador(filas) == 2


# Invalidados y vacías -------------------------------------------------------------------------


def test_vacia_da_none() -> None:
    assert pick_current([]) is None
    assert pick_current([], score_type="time") is None


def test_un_invalidado_no_gana_aunque_tenga_la_mejor_marca() -> None:
    filas = [rm(1, 150_000, invalidated_at=INSTANTE), rm(2, 100_000)]
    assert ganador(filas) == 2


def test_si_todos_estan_invalidados_da_none() -> None:
    filas = [rm(1, 150_000, invalidated_at=INSTANTE), rm(2, 100_000, invalidated_at=INSTANTE)]
    assert pick_current(filas) is None
    marcas = [bench(1, seconds=100, invalidated_at=INSTANTE)]
    assert pick_current(marcas, score_type="time") is None


def test_devuelve_una_de_las_filas_recibidas_y_no_las_modifica() -> None:
    filas = [rm(1, 80_000), rm(2, 100_000)]
    copia = list(filas)
    elegido = pick_current(filas)
    assert elegido is filas[1]
    assert filas == copia


# Benchmark `time` ------------------------------------------------------------------------------


def test_time_gana_el_menor_tiempo() -> None:
    filas = [bench(1, seconds=300), bench(2, seconds=250), bench(3, seconds=280)]
    assert ganador(filas, "time") == 2


def test_time_un_rx_lento_gana_a_un_scaled_rapido() -> None:
    filas = [bench(1, "scaled", seconds=100), bench(2, "rx", seconds=300)]
    assert ganador(filas, "time") == 2


def test_time_rx_y_rx_plus_van_en_el_mismo_grupo() -> None:
    filas = [bench(1, "rx", seconds=290), bench(2, "rx_plus", seconds=280)]
    assert ganador(filas, "time") == 2
    filas = [bench(1, "rx", seconds=270), bench(2, "rx_plus", seconds=280)]
    assert ganador(filas, "time") == 1


def test_time_entre_dos_scaled_gana_el_menor_tiempo() -> None:
    filas = [bench(1, "scaled", seconds=400), bench(2, "scaled", seconds=350)]
    assert ganador(filas, "time") == 2


def test_time_el_que_termino_gana_al_cortado_por_time_cap() -> None:
    filas = [bench(1, capped=True, seconds=600, reps=40), bench(2, seconds=590)]
    assert ganador(filas, "time") == 2


def test_time_entre_dos_cortados_gana_el_de_mas_reps() -> None:
    filas = [
        bench(1, capped=True, seconds=600, reps=40),
        bench(2, capped=True, seconds=600, reps=55),
    ]
    assert ganador(filas, "time") == 2


def test_time_un_cortado_puede_ser_el_unico_vigente() -> None:
    assert ganador([bench(9, capped=True, seconds=600, reps=40)], "time") == 9


def test_time_empate_gana_el_achieved_on_mas_antiguo_y_luego_el_created_at() -> None:
    filas = [
        bench(1, seconds=250, achieved_on=date(2026, 8, 1)),
        bench(2, seconds=250, achieved_on=date(2026, 6, 1)),
    ]
    assert ganador(filas, "time") == 2
    filas = [
        bench(1, seconds=250, created_at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC)),
        bench(2, seconds=250, created_at=datetime(2026, 10, 20, 8, 0, tzinfo=UTC)),
    ]
    assert ganador(filas, "time") == 2


# Otros tipos de marca ---------------------------------------------------------------------------


def test_rounds_reps_gana_mas_rondas_y_luego_mas_reps() -> None:
    filas = [
        bench(1, rounds=5, reps=10),
        bench(2, rounds=5, reps=12),
        bench(3, rounds=4, reps=30),
    ]
    assert ganador(filas, "rounds_reps") == 2


def test_reps_gana_el_mayor() -> None:
    assert ganador([bench(1, reps=50), bench(2, reps=71), bench(3, reps=70)], "reps") == 2


def test_load_gana_la_mayor_carga_pero_un_rx_plus_gana_a_un_scaled_mas_pesado() -> None:
    assert ganador([bench(1, load_g=90_000), bench(2, load_g=100_000)], "load") == 2
    filas = [bench(1, "rx_plus", load_g=90_000), bench(2, "scaled", load_g=120_000)]
    assert ganador(filas, "load") == 1


# Contrato de `score_type` -----------------------------------------------------------------------


def test_con_filas_de_benchmark_el_score_type_es_obligatorio() -> None:
    with pytest.raises(ValueError, match=r"."):
        pick_current([bench(1, seconds=100)])


def test_un_score_type_sin_leaderboard_lanza_value_error() -> None:
    with pytest.raises(ValueError, match=r"."):
        pick_current([bench(1, seconds=100)], score_type="none")
