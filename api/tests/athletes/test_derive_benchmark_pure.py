"""`derive_benchmark`: la regla pura del récord de benchmark derivado (S9-B4, US-182; S9-D10).

Sin base ni bus; valores a mano. Crea solo si el WOD es de un benchmark y la marca es ESTRICTAMENTE
mejor que la vigente según `score_key` (el orden del leaderboard): el empate no crea, un `scaled`
nunca gana a un `rx`, `rx_plus` compite con `rx`, y un `capped` puede ser el primer récord pero va
detrás de todo el que terminó.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.modules.athletes.rules import RecordDraft, RecordRow, derive_benchmark
from app.modules.results.schemas import ResultMark
from app.modules.wods.catalog import WodRecordMeta

BENCHMARK = UUID(int=10)
MOVIMIENTO = UUID(int=1)
RESULTADO = UUID(int=2)
WOD = UUID(int=3)
SOCIO = UUID(int=4)
VALIDADOR = UUID(int=5)
DIA = date(2026, 10, 21)


def marca(**cambios: Any) -> ResultMark:
    valores: dict[str, Any] = {
        "result_id": RESULTADO,
        "member_id": SOCIO,
        "wod_id": WOD,
        "wod_date": DIA,
        "benchmark_id": BENCHMARK,
        "level": "rx",
        "seconds": 245,
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


def meta(score_type: str = "time", **cambios: Any) -> WodRecordMeta:
    valores: dict[str, Any] = {
        "score_type": score_type,
        "primary_movement_id": None,
        "benchmark_id": BENCHMARK,
        "date": DIA,
    }
    valores.update(cambios)
    return WodRecordMeta(**valores)


def vigente(**cambios: Any) -> RecordRow:
    valores: dict[str, Any] = {
        "id": uuid4(),
        "kind": "benchmark",
        "movement_id": None,
        "benchmark_id": BENCHMARK,
        "value_g": None,
        "level": "rx",
        "seconds": 260,
        "rounds": None,
        "reps": None,
        "load_g": None,
        "capped": False,
        "achieved_on": date(2026, 10, 1),
        "created_at": datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    }
    valores.update(cambios)
    return RecordRow(**valores)


# time: menor es mejor ---------------------------------------------------------------------------


def test_245_s_sobre_260_s_crea_el_borrador_completo() -> None:
    borrador = derive_benchmark(marca(seconds=245), meta(), vigente(seconds=260))

    assert borrador == RecordDraft(
        kind="benchmark",
        movement_id=None,
        benchmark_id=BENCHMARK,
        value_g=None,
        level="rx",
        seconds=245,
        rounds=None,
        reps=None,
        load_g=None,
        capped=False,
        achieved_on=DIA,
        result_id=RESULTADO,
        wod_id=WOD,
    )


def test_270_s_sobre_260_s_no_crea() -> None:
    assert derive_benchmark(marca(seconds=270), meta(), vigente(seconds=260)) is None


def test_el_empate_exacto_no_crea() -> None:
    assert derive_benchmark(marca(seconds=260), meta(), vigente(seconds=260)) is None


def test_un_segundo_mejor_crea_y_un_segundo_peor_no() -> None:
    assert derive_benchmark(marca(seconds=259), meta(), vigente(seconds=260)) is not None
    assert derive_benchmark(marca(seconds=261), meta(), vigente(seconds=260)) is None


def test_sin_vigente_la_primera_marca_crea() -> None:
    borrador = derive_benchmark(marca(seconds=600), meta(), None)

    assert borrador is not None and borrador.seconds == 600


# rounds_reps, reps y load: mayor es mejor -------------------------------------------------------


@pytest.mark.parametrize(
    ("rondas", "reps", "crea"),
    [(5, 12, True), (5, 10, False), (4, 30, False), (6, 0, True), (5, 9, False)],
)
def test_rounds_reps_compara_rondas_y_luego_repeticiones(
    rondas: int, reps: int, crea: bool
) -> None:
    actual = vigente(seconds=None, rounds=5, reps=10)

    borrador = derive_benchmark(
        marca(seconds=None, rounds=rondas, reps=reps), meta("rounds_reps"), actual
    )

    assert (borrador is not None) is crea
    if borrador is not None:
        assert (borrador.rounds, borrador.reps, borrador.seconds) == (rondas, reps, None)


@pytest.mark.parametrize(("reps", "crea"), [(51, True), (50, False), (49, False)])
def test_reps_gana_con_mas_repeticiones(reps: int, crea: bool) -> None:
    actual = vigente(seconds=None, reps=50)

    borrador = derive_benchmark(marca(seconds=None, reps=reps), meta("reps"), actual)

    assert (borrador is not None) is crea


@pytest.mark.parametrize(("carga", "crea"), [(100_000, True), (95_000, False), (90_000, False)])
def test_load_gana_con_mas_carga(carga: int, crea: bool) -> None:
    actual = vigente(seconds=None, load_g=95_000)

    borrador = derive_benchmark(marca(seconds=None, load_g=carga), meta("load"), actual)

    assert (borrador is not None) is crea
    if borrador is not None:
        assert borrador.kind == "benchmark" and borrador.load_g == carga
        assert borrador.value_g is None and borrador.movement_id is None


def test_un_benchmark_de_carga_con_cero_gramos_no_crea_record() -> None:
    """S9-D59: coherente con `derive_rm`, que exige más de 0 g; 0 g no es un récord."""
    assert derive_benchmark(marca(seconds=None, load_g=0), meta("load"), None) is None


# nivel: scaled contra rx ------------------------------------------------------------------------


def test_un_scaled_mas_rapido_nunca_gana_a_un_rx() -> None:
    actual = vigente(level="rx", seconds=300)

    assert derive_benchmark(marca(level="scaled", seconds=100), meta(), actual) is None


def test_un_rx_lento_gana_a_un_scaled_rapido() -> None:
    actual = vigente(level="scaled", seconds=100)

    borrador = derive_benchmark(marca(level="rx", seconds=400), meta(), actual)

    assert borrador is not None and borrador.level == "rx" and borrador.seconds == 400


def test_un_scaled_gana_a_otro_scaled_mas_lento() -> None:
    actual = vigente(level="scaled", seconds=300)

    assert derive_benchmark(marca(level="scaled", seconds=290), meta(), actual) is not None
    assert derive_benchmark(marca(level="scaled", seconds=310), meta(), actual) is None


def test_rx_plus_compite_con_rx_solo_por_la_marca() -> None:
    actual = vigente(level="rx", seconds=260)

    borrador = derive_benchmark(marca(level="rx_plus", seconds=250), meta(), actual)

    assert borrador is not None and borrador.level == "rx_plus"
    assert derive_benchmark(marca(level="rx_plus", seconds=270), meta(), actual) is None


def test_el_primer_scaled_sin_vigente_crea() -> None:
    borrador = derive_benchmark(marca(level="scaled", seconds=500), meta(), None)

    assert borrador is not None and borrador.level == "scaled"


# capped: time cap alcanzado ---------------------------------------------------------------------


def test_un_capped_puede_ser_el_primer_record() -> None:
    borrador = derive_benchmark(marca(seconds=600, reps=30, capped=True), meta(), None)

    assert borrador is not None
    assert (borrador.capped, borrador.seconds, borrador.reps) == (True, 600, 30)


def test_un_capped_va_detras_de_quien_termino_aunque_sean_mas_segundos() -> None:
    actual = vigente(seconds=599)

    assert derive_benchmark(marca(seconds=600, reps=30, capped=True), meta(), actual) is None


def test_quien_termino_gana_a_un_capped() -> None:
    actual = vigente(seconds=600, reps=30, capped=True)

    borrador = derive_benchmark(marca(seconds=599), meta(), actual)

    assert borrador is not None and borrador.capped is False


def test_entre_dos_capped_gana_el_de_mas_rondas_y_luego_mas_repeticiones() -> None:
    actual = vigente(seconds=600, rounds=2, reps=10, capped=True)

    mas_reps = marca(seconds=600, rounds=2, reps=11, capped=True)
    menos_reps = marca(seconds=600, rounds=2, reps=9, capped=True)
    mas_rondas = marca(seconds=600, rounds=3, reps=0, capped=True)
    igual = marca(seconds=600, rounds=2, reps=10, capped=True)

    assert derive_benchmark(mas_reps, meta(), actual) is not None
    assert derive_benchmark(mas_rondas, meta(), actual) is not None
    assert derive_benchmark(menos_reps, meta(), actual) is None
    assert derive_benchmark(igual, meta(), actual) is None


# lo que no deriva -------------------------------------------------------------------------------


def test_un_wod_sin_benchmark_no_deriva() -> None:
    assert derive_benchmark(marca(), meta(benchmark_id=None), None) is None


def test_un_tipo_sin_leaderboard_no_deriva_ni_lanza() -> None:
    assert derive_benchmark(marca(), meta("none"), None) is None


def test_una_marca_sin_ningun_valor_no_deriva() -> None:
    sin_valores = marca(seconds=None, rounds=None, reps=None, load_g=None)

    assert derive_benchmark(sin_valores, meta(), None) is None


def test_el_borrador_toma_el_benchmark_del_wod_y_la_fecha_de_la_marca() -> None:
    otro = UUID(int=77)

    borrador = derive_benchmark(
        marca(wod_date=date(2026, 9, 9), benchmark_id=otro),
        meta(benchmark_id=otro),
        vigente(benchmark_id=otro),
    )

    assert borrador is not None
    assert borrador.benchmark_id == otro and borrador.achieved_on == date(2026, 9, 9)
    assert (borrador.result_id, borrador.wod_id) == (RESULTADO, WOD)


# LOW-3 y LOW-4 (revisión de seguridad): la marca debe traer el campo de su tipo y ser del WOD ----


def test_una_marca_de_otro_benchmark_no_deriva() -> None:
    assert derive_benchmark(marca(benchmark_id=UUID(int=99)), meta(), None) is None
    assert derive_benchmark(marca(benchmark_id=None), meta(), None) is None


@pytest.mark.parametrize(
    ("tipo", "campos"),
    [
        ("time", {"seconds": None, "reps": 30}),
        ("rounds_reps", {"seconds": None, "rounds": 5}),
        ("rounds_reps", {"seconds": None, "reps": 10}),
        ("reps", {"seconds": 245}),
        ("load", {"seconds": 245}),
        ("load", {"seconds": None, "reps": 5}),
    ],
)
def test_una_marca_sin_el_campo_de_su_tipo_no_deriva(tipo: str, campos: dict[str, Any]) -> None:
    assert derive_benchmark(marca(**campos), meta(tipo), None) is None


def test_un_capped_sin_repeticiones_no_deriva() -> None:
    assert derive_benchmark(marca(seconds=600, reps=None, capped=True), meta(), None) is None


def test_rounds_reps_con_cero_rondas_y_cero_repeticiones_si_deriva() -> None:
    borrador = derive_benchmark(marca(seconds=None, rounds=0, reps=0), meta("rounds_reps"), None)

    assert borrador is not None and (borrador.rounds, borrador.reps) == (0, 0)
