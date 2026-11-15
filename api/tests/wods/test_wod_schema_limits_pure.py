"""Topes del esquema de WODs (S8-A3b, L-2 y L-3): la lista de movimientos y la fecha se acotan en
el borde, antes del service. Puro: sin base ni reloj."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.wods.schemas import WodCreate, WodPatch


def _movimientos(n: int) -> list[dict[str, Any]]:
    return [{"movement_id": str(uuid4()), "position": i, "reps": "10"} for i in range(1, n + 1)]


def _cuerpo(**cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {
        "date": "2026-10-22",
        "title": "Fran",
        "score_type": "reps",
        "movements": _movimientos(1),
    }
    valores.update(cambios)
    return valores


def test_treinta_movimientos_valen_y_treinta_y_uno_no() -> None:
    WodCreate.model_validate(_cuerpo(movements=_movimientos(30)))
    WodPatch.model_validate({"movements": _movimientos(30)})
    with pytest.raises(ValidationError) as alta:
        WodCreate.model_validate(_cuerpo(movements=_movimientos(31)))
    assert alta.value.errors()[0]["loc"] == ("movements",)
    with pytest.raises(ValidationError) as parche:
        WodPatch.model_validate({"movements": _movimientos(31)})
    assert parche.value.errors()[0]["loc"] == ("movements",)


@pytest.mark.parametrize("fecha", ["2020-01-01", "2026-10-22", "2100-12-31"])
def test_las_fechas_de_2020_a_2100_valen(fecha: str) -> None:
    WodCreate.model_validate(_cuerpo(date=fecha))
    WodPatch.model_validate({"date": fecha})


@pytest.mark.parametrize("fecha", ["2019-12-31", "2101-01-01", "0001-01-01", "9999-12-31"])
def test_las_fechas_fuera_de_2020_a_2100_dan_422(fecha: str) -> None:
    with pytest.raises(ValidationError) as alta:
        WodCreate.model_validate(_cuerpo(date=fecha))
    assert alta.value.errors()[0]["loc"] == ("date",)
    with pytest.raises(ValidationError) as parche:
        WodPatch.model_validate({"date": fecha})
    assert parche.value.errors()[0]["loc"] == ("date",)
