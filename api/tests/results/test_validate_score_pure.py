"""`validate_score` (S8-B1, US-169; S8-D12, N-43, L-2): reglas puras de la marca, sin base."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.modules.results.exceptions import ResultValidationError
from app.modules.results.rules import validate_score

MOVS = [uuid4(), uuid4(), uuid4()]


def _v(**cambios: Any) -> Any:
    base: dict[str, Any] = {
        "score_type": "time", "time_cap_s": 600, "level": "rx", "seconds": 300, "rounds": None,
        "reps": None, "load_g": None, "capped": False, "scaled_movement_ids": [],
        "wod_movement_ids": MOVS,
    }  # fmt: skip
    base.update(cambios)
    return validate_score(**base)


def _campo(**cambios: Any) -> str | None:
    with pytest.raises(ResultValidationError) as info:
        _v(**cambios)
    return info.value.field


def test_time_exige_seconds_y_respeta_cap() -> None:
    assert _v().seconds == 300
    assert _v(seconds=600).seconds == 600
    assert _campo(seconds=None) == "seconds"
    assert _campo(seconds=601) == "seconds"
    assert _v(time_cap_s=None, seconds=7_200).seconds == 7_200


def test_capped_exige_cap_en_el_wod_y_reps() -> None:
    assert _campo(capped=True, seconds=None, reps=None) == "reps"
    assert _campo(capped=True, seconds=None, reps=50, time_cap_s=None) == "capped"


def test_capped_fija_seconds_igual_al_cap_y_rechaza_seconds_del_cliente() -> None:
    marca = _v(capped=True, seconds=None, reps=87)
    assert (marca.seconds, marca.reps, marca.capped) == (600, 87, True)
    assert _campo(capped=True, seconds=300, reps=87) == "seconds"


@pytest.mark.parametrize("tipo", ["rounds_reps", "reps", "load"])
def test_capped_fuera_de_time_422_capped(tipo: str) -> None:
    assert (
        _campo(score_type=tipo, capped=True, seconds=None, reps=5, rounds=1, load_g=1) == "capped"
    )


def test_rounds_reps_reps_y_load() -> None:
    mixto = _v(score_type="rounds_reps", seconds=None, rounds=5, reps=12)
    assert (mixto.rounds, mixto.reps) == (5, 12)
    assert _v(score_type="reps", time_cap_s=None, seconds=None, reps=100).reps == 100
    pesado = _v(score_type="load", time_cap_s=None, seconds=None, load_g=102_500)
    assert pesado.load_g == 102_500
    assert _campo(score_type="rounds_reps", seconds=None, rounds=5) == "reps"
    assert _campo(score_type="load", time_cap_s=None, seconds=None) == "load_g"


def test_campos_ajenos_al_tipo_422() -> None:
    assert _campo(reps=3) == "reps"
    assert _campo(rounds=1) == "rounds"
    assert _campo(load_g=1) == "load_g"
    assert _campo(score_type="load", time_cap_s=None, seconds=5, load_g=1000) == "seconds"
    assert _campo(score_type="none", seconds=None) == "wod_id"


def test_ceros_validos_salvo_seconds() -> None:
    assert _v(score_type="rounds_reps", seconds=None, rounds=0, reps=0).rounds == 0
    assert _v(score_type="load", time_cap_s=None, seconds=None, load_g=0).load_g == 0
    assert _v(score_type="reps", time_cap_s=None, seconds=None, reps=0).reps == 0
    assert _campo(seconds=0) == "seconds"


def test_negativos_422() -> None:
    assert _campo(seconds=-1) == "seconds"
    assert _campo(score_type="rounds_reps", seconds=None, rounds=-1, reps=1) == "rounds"
    assert _campo(score_type="load", time_cap_s=None, seconds=None, load_g=-5) == "load_g"
    assert _campo(score_type="load", time_cap_s=None, seconds=None, load_g=1_000_001) == "load_g"


def test_scaled_movement_ids_solo_con_scaled_y_del_wod() -> None:
    assert _v(level="scaled", scaled_movement_ids=[MOVS[0]]).scaled_movement_ids == (MOVS[0],)
    assert _campo(level="rx", scaled_movement_ids=[MOVS[0]]) == "scaled_movement_ids"
    assert _campo(level="scaled", scaled_movement_ids=[uuid4()]) == "scaled_movement_ids"
    assert _campo(level="scaled", scaled_movement_ids=[MOVS[0], MOVS[0]]) == "scaled_movement_ids"
