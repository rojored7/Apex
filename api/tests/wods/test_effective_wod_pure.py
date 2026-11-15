"""WOD efectivo de una sesión (S8-A4, US-168 CA2, S8-D9). Pura: sin base ni reloj."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from app.modules.classes.rules import effective_wod_id, local_date


def test_asignado_gana() -> None:
    asignado, del_dia = uuid4(), uuid4()
    assert effective_wod_id(asignado, del_dia) == asignado
    assert effective_wod_id(asignado, None) == asignado


def test_null_hereda_el_del_dia() -> None:
    del_dia = uuid4()
    assert effective_wod_id(None, del_dia) == del_dia
    assert effective_wod_id(None, None) is None


def test_23_30_de_bogota_es_04_30z_del_dia_siguiente() -> None:
    """La clase de las 23:30 del 22 en Bogotá empieza el 23 a las 04:30Z: hereda el WOD del 22."""
    inicio = datetime(2026, 10, 23, 4, 30, tzinfo=UTC)
    dia = local_date(inicio)
    assert dia == date(2026, 10, 22)
    wod_22, wod_23 = uuid4(), uuid4()
    por_dia = {date(2026, 10, 22): wod_22, date(2026, 10, 23): wod_23}
    assert effective_wod_id(None, por_dia.get(dia)) == wod_22
