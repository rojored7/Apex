"""`validate_wod` puro (S8-A3, US-166; S8-D7, S8-D41). Rojo A3. Sin base ni reloj."""

from __future__ import annotations

import pytest

from app.modules.wods.exceptions import WodsValidationError
from app.modules.wods.rules import MovementSpec, validate_wod


def _mov(posicion: int = 1, **cambios: object) -> MovementSpec:
    valores: dict[str, object] = {"position": posicion, "is_primary": False, "unit": "reps"}
    valores.update(cambios)
    return MovementSpec(**valores)  # type: ignore[arg-type]


def _campo(**kw: object) -> str | None:
    try:
        validate_wod(**kw)  # type: ignore[arg-type]
    except WodsValidationError as error:
        return error.field
    return None


def test_un_wod_valido_pasa() -> None:
    validate_wod("time", 600, [_mov(1, is_primary=True, unit="kg", load_rx_m_g=43000), _mov(2)])
    validate_wod("reps", None, [_mov()])
    validate_wod("none", None, [_mov()])


def test_sin_movimientos() -> None:
    assert _campo(score_type="time", time_cap_s=None, movements=[]) == "movements"


def test_mas_de_30() -> None:
    treinta = [_mov(i) for i in range(1, 31)]
    validate_wod("reps", None, treinta)
    assert _campo(score_type="reps", time_cap_s=None, movements=[*treinta, _mov(31)]) == "movements"


def test_dos_principales() -> None:
    movs = [_mov(1, is_primary=True), _mov(2, is_primary=True)]
    assert _campo(score_type="time", time_cap_s=None, movements=movs) == "movements"


@pytest.mark.parametrize("cap", [0, -1, 14_401])
def test_cap_fuera_de_rango(cap: int) -> None:
    assert _campo(score_type="time", time_cap_s=cap, movements=[_mov()]) == "time_cap_s"


def test_los_extremos_del_cap_valen() -> None:
    validate_wod("time", 1, [_mov()])
    validate_wod("rounds_reps", 14_400, [_mov()])


@pytest.mark.parametrize("tipo", ["reps", "load", "none"])
def test_cap_con_reps_o_load_da_422(tipo: str) -> None:
    assert _campo(score_type=tipo, time_cap_s=600, movements=[_mov()]) == "time_cap_s"


def test_none_sin_cap() -> None:
    assert _campo(score_type="none", time_cap_s=60, movements=[_mov()]) == "time_cap_s"


@pytest.mark.parametrize("unidad", ["reps", "m", "cal", "s"])
def test_carga_sin_unidad_kg(unidad: str) -> None:
    movs = [_mov(1), _mov(2, unit=unidad, load_rx_f_g=20000)]
    assert _campo(score_type="time", time_cap_s=None, movements=movs) == "movements.1.load_rx_f_g"
    movs = [_mov(1, unit=unidad, load_rx_m_g=0)]
    assert _campo(score_type="time", time_cap_s=None, movements=movs) == "movements.0.load_rx_m_g"


def test_carga_cero_con_kg_vale() -> None:
    validate_wod("load", None, [_mov(1, unit="kg", load_rx_m_g=0, load_rx_f_g=0)])


@pytest.mark.parametrize("posiciones", [[2, 3], [1, 3], [1, 1], [0, 1], [1, 2, 4]])
def test_posiciones_1_a_n(posiciones: list[int]) -> None:
    movs = [_mov(p) for p in posiciones]
    assert _campo(score_type="reps", time_cap_s=None, movements=movs) == "movements"


def test_las_posiciones_valen_en_cualquier_orden_de_la_lista() -> None:
    validate_wod("reps", None, [_mov(2), _mov(1), _mov(3)])
