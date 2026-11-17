"""`rules.current_records` y `rules.summarize_records` (S9-C2, US-184; S9-D10, S9-D27). Pura. Rojo.

- Un récord vigente por objetivo (movimiento o benchmark), con la misma regla de `pick_current`
  (N-45): RM por mayor `value_g`; benchmark por menor `score_key`; empate por `achieved_on` y
  `created_at` más antiguos y luego el id.
- Los invalidados no cuentan: un movimiento solo con invalidados no es un RM vigente.
- Un benchmark sin tipo de marca en el catálogo se ignora (no se puede ordenar).
- `summarize_records`: `current_rms` = movimientos con RM vigente; `recent` = los vigentes más
  recientes (`achieved_on`, `created_at` e id descendentes), a lo sumo `recent_limit` (3 por
  omisión, US-184 CA1). No depende del orden de la entrada y no muta.
"""

from __future__ import annotations

import dataclasses
import random
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from app.modules.athletes.rules import (
    RECENT_RECORDS,
    RecordRow,
    current_records,
    pick_current,
    summarize_records,
)

BASE = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
MOV_A, MOV_B, MOV_C, MOV_D = (UUID(int=100 + n) for n in range(4))
FRAN, HELEN = UUID(int=700), UUID(int=701)
TIPOS = {FRAN: "time", HELEN: "reps"}


def rm(n: int, movimiento: UUID, value_g: int, dia: int = 1, **cambios: Any) -> RecordRow:
    base: dict[str, Any] = {
        "id": UUID(int=n),
        "kind": "rm",
        "movement_id": movimiento,
        "benchmark_id": None,
        "value_g": value_g,
        "level": None,
        "seconds": None,
        "rounds": None,
        "reps": None,
        "load_g": None,
        "capped": False,
        "achieved_on": date(2026, 9, dia),
        "created_at": BASE + timedelta(minutes=n),
    }
    base.update(cambios)
    return RecordRow(**base)


def bm(n: int, benchmark: UUID, dia: int = 1, **cambios: Any) -> RecordRow:
    base: dict[str, Any] = {
        "id": UUID(int=n),
        "kind": "benchmark",
        "movement_id": None,
        "benchmark_id": benchmark,
        "value_g": None,
        "level": "rx",
        "seconds": 300,
        "rounds": None,
        "reps": None,
        "load_g": None,
        "capped": False,
        "achieved_on": date(2026, 9, dia),
        "created_at": BASE + timedelta(minutes=n),
    }
    base.update(cambios)
    return RecordRow(**base)


def ids(filas: Any) -> list[int]:
    return [f.id.int for f in filas]


def invalidado(fila: RecordRow) -> RecordRow:
    return dataclasses.replace(fila, invalidated_at=BASE)


# --- current_records ------------------------------------------------------------------------


def test_sin_registros_no_hay_vigentes() -> None:
    assert current_records([], {}) == []


def test_un_vigente_por_movimiento_el_de_mayor_carga() -> None:
    filas = [rm(1, MOV_A, 90_000), rm(2, MOV_A, 100_000), rm(3, MOV_B, 50_000)]

    assert sorted(ids(current_records(filas, {}))) == [2, 3]


def test_los_invalidados_no_cuentan_y_el_siguiente_pasa_a_vigente() -> None:
    filas = [invalidado(rm(1, MOV_A, 100_000)), rm(2, MOV_A, 90_000)]

    assert ids(current_records(filas, {})) == [2]


def test_un_movimiento_solo_con_invalidados_no_tiene_vigente() -> None:
    assert current_records([invalidado(rm(1, MOV_A, 100_000))], {}) == []


def test_el_empate_gana_el_mas_antiguo_por_fecha_luego_alta_luego_id() -> None:
    mismo_dia = [rm(3, MOV_A, 100_000, dia=5), rm(4, MOV_A, 100_000, dia=5)]
    otro_dia = [rm(6, MOV_B, 100_000, dia=9), rm(5, MOV_B, 100_000, dia=2)]
    mismo_alta = [
        rm(8, MOV_C, 100_000, dia=5, created_at=BASE),
        rm(7, MOV_C, 100_000, dia=5, created_at=BASE),
    ]

    vigentes = current_records([*mismo_dia, *otro_dia, *mismo_alta], {})

    assert sorted(ids(vigentes)) == [3, 5, 7]


def test_benchmark_vigente_por_score_key_del_tipo() -> None:
    filas = [
        bm(1, FRAN, seconds=300),
        bm(2, FRAN, seconds=250),
        bm(3, HELEN, reps=40, seconds=None),
    ]

    vigentes = current_records(filas, TIPOS)

    assert sorted(ids(vigentes)) == [2, 3]


def test_un_scaled_no_gana_a_un_rx_aunque_sea_mas_rapido() -> None:
    filas = [bm(1, FRAN, seconds=300, level="rx"), bm(2, FRAN, seconds=100, level="scaled")]

    assert ids(current_records(filas, TIPOS)) == [1]


def test_un_benchmark_sin_tipo_en_el_catalogo_se_ignora() -> None:
    filas = [bm(1, FRAN), rm(2, MOV_A, 90_000)]

    assert ids(current_records(filas, {})) == [2]


def test_coincide_con_pick_current_por_objetivo() -> None:
    rng = random.Random(7)  # noqa: S311
    movimientos = [MOV_A, MOV_B, MOV_C]
    filas = [
        rm(n, rng.choice(movimientos), rng.choice([80_000, 90_000, 100_000]), rng.randint(1, 9))
        for n in range(1, 40)
    ]
    esperados: dict[UUID, UUID] = {}
    for m in movimientos:
        elegido = pick_current([f for f in filas if f.movement_id == m])
        assert elegido is not None
        esperados[m] = elegido.id

    vigentes = current_records(filas, {})

    assert {f.movement_id: f.id for f in vigentes} == esperados


def test_no_depende_del_orden_de_la_entrada_ni_la_muta() -> None:
    filas = [rm(n, MOV_A if n % 2 else MOV_B, 100_000, dia=n % 5 + 1) for n in range(1, 12)]
    copia = list(filas)
    barajada = list(filas)
    random.Random(3).shuffle(barajada)  # noqa: S311

    assert sorted(ids(current_records(filas, {}))) == sorted(ids(current_records(barajada, {})))
    assert filas == copia


# --- summarize_records ----------------------------------------------------------------------


def test_el_resumen_vacio_es_cero_y_sin_recientes() -> None:
    resumen = summarize_records([], {})

    assert (resumen.current_rms, resumen.recent) == (0, ())


def test_current_rms_cuenta_movimientos_con_rm_vigente_y_no_benchmarks() -> None:
    filas = [
        rm(1, MOV_A, 90_000),
        rm(2, MOV_A, 100_000),
        rm(3, MOV_B, 50_000),
        invalidado(rm(4, MOV_C, 70_000)),
        bm(5, FRAN),
    ]

    assert summarize_records(filas, TIPOS).current_rms == 2


def test_recent_son_los_vigentes_mas_recientes_y_no_los_superados() -> None:
    filas = [
        rm(1, MOV_A, 80_000, dia=1),  # superado por el 2: no es vigente
        rm(2, MOV_A, 100_000, dia=3),
        rm(3, MOV_B, 50_000, dia=7),
        bm(4, FRAN, dia=5),
        rm(5, MOV_C, 60_000, dia=9),
        rm(6, MOV_D, 40_000, dia=2),
    ]

    resumen = summarize_records(filas, TIPOS)

    assert ids(resumen.recent) == [5, 3, 4]
    assert resumen.current_rms == 4


def test_recent_desempata_por_alta_descendente_y_luego_id_descendente() -> None:
    filas = [
        rm(1, MOV_A, 100_000, dia=5, created_at=BASE),
        rm(2, MOV_B, 100_000, dia=5, created_at=BASE + timedelta(hours=1)),
        rm(3, MOV_C, 100_000, dia=5, created_at=BASE + timedelta(hours=1)),
    ]

    assert ids(summarize_records(filas, {}).recent) == [3, 2, 1]


def test_recent_es_como_maximo_tres_por_omision_y_acepta_otro_limite() -> None:
    filas = [rm(n, UUID(int=900 + n), 50_000, dia=n) for n in range(1, 8)]

    assert RECENT_RECORDS == 3
    assert ids(summarize_records(filas, {}).recent) == [7, 6, 5]
    assert ids(summarize_records(filas, {}, recent_limit=5).recent) == [7, 6, 5, 4, 3]
    assert summarize_records(filas, {}, recent_limit=0).recent == ()
    assert summarize_records(filas, {}).current_rms == 7


def test_el_resumen_no_depende_del_orden_de_la_entrada() -> None:
    filas = [rm(n, UUID(int=900 + n % 4), 40_000 + n * 1_000, dia=n % 9 + 1) for n in range(1, 30)]
    barajada = list(filas)
    random.Random(11).shuffle(barajada)  # noqa: S311

    assert summarize_records(filas, {}) == summarize_records(barajada, {})
