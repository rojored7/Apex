"""`best_candidate`: la regla pura de la reposición del mejor (S9-B5, US-181; S9-D11, N-45).

Sin base ni bus; valores a mano en gramos enteros (S8-D41). Las candidatas son marcas vigentes y
validadas del MISMO objetivo SIN récord vivo (el filtro lo hace quien llama):
- RM: gana el mayor `load_g` entre las que no son `scaled` y pesan más de 0 g; solo vuelve si es
  ESTRICTAMENTE mayor que el vigente que quedó (o no hay vigente).
- Benchmark: gana la de menor `score_key` del tipo; solo vuelve si es ESTRICTAMENTE mejor.
- Empate entre candidatas: `wod_date` más antigua y, luego, el `result_id` menor.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.modules.athletes.rules import RecordRow, best_candidate
from app.modules.results.schemas import ResultMark

MOVIMIENTO = UUID(int=1)
BENCHMARK = UUID(int=2)
SOCIO = UUID(int=4)
VALIDADOR = UUID(int=5)
DIA = date(2026, 10, 21)


def marca(numero: int, **cambios: Any) -> ResultMark:
    """Una marca con `result_id = UUID(int=numero)` (el desempate por id es legible)."""
    valores: dict[str, Any] = {
        "result_id": UUID(int=numero),
        "member_id": SOCIO,
        "wod_id": uuid4(),
        "wod_date": DIA,
        "benchmark_id": None,
        "level": "rx",
        "seconds": None,
        "rounds": None,
        "reps": None,
        "load_g": None,
        "capped": False,
        "status": "validated",
        "is_current": True,
        "supersedes_id": None,
        "validated_by": VALIDADOR,
        "source": "desk",
    }
    valores.update(cambios)
    return ResultMark(**valores)


def carga(numero: int, load_g: int, **cambios: Any) -> ResultMark:
    return marca(numero, load_g=load_g, **cambios)


def tiempo(numero: int, seconds: int, **cambios: Any) -> ResultMark:
    return marca(numero, benchmark_id=BENCHMARK, seconds=seconds, **cambios)


def rm_vigente(value_g: int) -> RecordRow:
    return RecordRow(
        id=uuid4(),
        kind="rm",
        movement_id=MOVIMIENTO,
        benchmark_id=None,
        value_g=value_g,
        level=None,
        seconds=None,
        rounds=None,
        reps=None,
        load_g=None,
        capped=False,
        achieved_on=DIA,
        created_at=datetime(2026, 10, 21, 15, 0, tzinfo=UTC),
    )


def tiempo_vigente(seconds: int, level: str = "rx") -> RecordRow:
    return RecordRow(
        id=uuid4(),
        kind="benchmark",
        movement_id=None,
        benchmark_id=BENCHMARK,
        value_g=None,
        level=level,
        seconds=seconds,
        rounds=None,
        reps=None,
        load_g=None,
        capped=False,
        achieved_on=DIA,
        created_at=datetime(2026, 10, 21, 15, 0, tzinfo=UTC),
    )


def rm(candidatas: list[ResultMark], current: RecordRow | None = None) -> ResultMark | None:
    return best_candidate(candidatas, kind="rm", score_type=None, current=current)


def bench(
    candidatas: list[ResultMark], current: RecordRow | None = None, score_type: str = "time"
) -> ResultMark | None:
    return best_candidate(candidatas, kind="benchmark", score_type=score_type, current=current)


# RM ------------------------------------------------------------------------------------------


def test_rm_sin_candidatas_no_repone() -> None:
    assert rm([]) is None


def test_rm_gana_la_de_mayor_carga_y_sin_vigente_repone() -> None:
    ganadora = rm([carga(1, 90_000), carga(2, 95_000), carga(3, 92_000)])

    assert ganadora is not None and ganadora.result_id == UUID(int=2)


def test_rm_solo_vuelve_si_supera_estrictamente_al_vigente() -> None:
    assert rm([carga(1, 90_000)], rm_vigente(90_000)) is None, "el empate no repone"
    assert rm([carga(1, 89_999)], rm_vigente(90_000)) is None
    mejor = rm([carga(1, 90_001)], rm_vigente(90_000))
    assert mejor is not None and mejor.load_g == 90_001


def test_rm_ignora_scaled_y_cargas_de_cero() -> None:
    assert rm([carga(1, 200_000, level="scaled")]) is None
    assert rm([carga(1, 0)]) is None
    ganadora = rm([carga(1, 200_000, level="scaled"), carga(2, 0), carga(3, 80_000)])
    assert ganadora is not None and ganadora.result_id == UUID(int=3)


def test_rm_rx_plus_compite_como_rx() -> None:
    ganadora = rm([carga(1, 100_000), carga(2, 101_000, level="rx_plus")])

    assert ganadora is not None and ganadora.result_id == UUID(int=2)


def test_rm_empate_gana_la_del_wod_mas_antiguo_y_luego_el_id_menor() -> None:
    antigua = carga(7, 100_000, wod_date=date(2026, 10, 1))
    reciente = carga(3, 100_000, wod_date=date(2026, 10, 15))
    assert rm([reciente, antigua]) == antigua

    mismo_dia_a = carga(5, 100_000)
    mismo_dia_b = carga(4, 100_000)
    assert rm([mismo_dia_a, mismo_dia_b]) == mismo_dia_b
    assert rm([mismo_dia_b, mismo_dia_a]) == mismo_dia_b, "el orden de entrada no importa"


def test_rm_con_un_hueco_en_el_historial_repone_la_mejor_que_quedo() -> None:
    """90, 1.000 (error, invalidado), 95 y 92: sin récord vivo quedan 95 y 92; el vigente es 90."""
    ganadora = rm([carga(1, 95_000), carga(2, 92_000)], rm_vigente(90_000))

    assert ganadora is not None and ganadora.load_g == 95_000


def test_no_muta_la_entrada() -> None:
    entrada = [carga(2, 95_000), carga(1, 90_000)]
    copia = list(entrada)

    rm(entrada)

    assert entrada == copia


# Benchmark -----------------------------------------------------------------------------------


def test_benchmark_gana_el_menor_tiempo() -> None:
    ganadora = bench([tiempo(1, 300), tiempo(2, 280), tiempo(3, 290)])

    assert ganadora is not None and ganadora.seconds == 280


def test_benchmark_solo_vuelve_si_mejora_estrictamente_al_vigente() -> None:
    assert bench([tiempo(1, 280)], tiempo_vigente(280)) is None, "el empate no repone"
    assert bench([tiempo(1, 281)], tiempo_vigente(280)) is None
    mejor = bench([tiempo(1, 279)], tiempo_vigente(280))
    assert mejor is not None and mejor.seconds == 279


def test_benchmark_un_scaled_nunca_gana_a_un_rx() -> None:
    ganadora = bench([tiempo(1, 200, level="scaled"), tiempo(2, 300)])

    assert ganadora is not None and ganadora.result_id == UUID(int=2)
    assert bench([tiempo(1, 200, level="scaled")], tiempo_vigente(300)) is None


def test_benchmark_un_capped_va_detras_de_todo_el_que_termino() -> None:
    topado = tiempo(1, 600, capped=True, reps=150)
    ganadora = bench([topado, tiempo(2, 590)])

    assert ganadora is not None and ganadora.result_id == UUID(int=2)
    unico = bench([topado])
    assert unico is not None and unico.result_id == UUID(int=1), "un capped puede ser el primero"


def test_benchmark_ignora_la_marca_sin_el_campo_de_su_tipo() -> None:
    sin_tiempo = marca(1, benchmark_id=BENCHMARK, reps=100)

    valida = tiempo(2, 300)  # una sola instancia: cada `marca` trae un `wod_id` aleatorio

    assert bench([sin_tiempo]) is None
    assert bench([sin_tiempo, valida]) == valida


def test_benchmark_exige_score_type() -> None:
    with pytest.raises(ValueError):
        best_candidate([tiempo(1, 300)], kind="benchmark", score_type=None, current=None)


def test_benchmark_empate_gana_el_wod_mas_antiguo_luego_el_id_menor() -> None:
    antigua = tiempo(9, 300, wod_date=date(2026, 9, 1))
    assert bench([tiempo(1, 300), antigua]) == antigua
    menor, mayor = tiempo(5, 300), tiempo(6, 300)  # instancias únicas: `wod_id` aleatorio
    assert bench([mayor, menor]) == menor


def test_benchmark_de_repeticiones_gana_el_mayor() -> None:
    ganadora = bench(
        [marca(1, benchmark_id=BENCHMARK, reps=50), marca(2, benchmark_id=BENCHMARK, reps=60)],
        score_type="reps",
    )

    assert ganadora is not None and ganadora.reps == 60
