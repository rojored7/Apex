"""Regla pura de quién anula una medición (S9-A3; S9-D33, M-3). Sin base de datos.

Derivado a mano: el admin anula todo; el coach solo lo suyo y hasta 24 h después de crearlo (la
hora 24 exacta aún cuenta); un reloj anterior a la creación cuenta como dentro de la ventana.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.modules.athletes.rules import SELF_UNDO_WINDOW_H, can_void

YO = UUID(int=1)
OTRO = UUID(int=2)
CREADA = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def _puede(role: str, autor: UUID, despues: timedelta) -> bool:
    return can_void(
        role=role, caller=YO, recorded_by=autor, created_at=CREADA, now=CREADA + despues
    )


def test_la_ventana_es_de_24_horas() -> None:
    assert SELF_UNDO_WINDOW_H == 24


@pytest.mark.parametrize("autor", [YO, OTRO])
@pytest.mark.parametrize("despues", [timedelta(0), timedelta(hours=24), timedelta(days=400)])
def test_el_admin_anula_todo(autor: UUID, despues: timedelta) -> None:
    assert _puede("admin", autor, despues) is True


@pytest.mark.parametrize(
    ("despues", "esperado"),
    [
        (timedelta(hours=-3), True),
        (timedelta(0), True),
        (timedelta(hours=23, minutes=59, seconds=59), True),
        (timedelta(hours=24), True),
        (timedelta(hours=24, seconds=1), False),
        (timedelta(days=3), False),
    ],
)
def test_el_coach_anula_lo_suyo_solo_dentro_de_la_ventana(
    despues: timedelta, esperado: bool
) -> None:
    assert _puede("coach", YO, despues) is esperado


def test_el_coach_nunca_anula_lo_de_otro() -> None:
    assert _puede("coach", OTRO, timedelta(0)) is False


@pytest.mark.parametrize("rol", ["member", "", "ADMIN"])
def test_cualquier_otro_rol_no_anula(rol: str) -> None:
    assert _puede(rol, YO, timedelta(0)) is False


# La búsqueda de claros no se confunde con un blob aleatorio (S9-D50) -------------------------


def test_claros_en_ignora_los_blobs_y_ve_el_claro_de_verdad() -> None:
    from tests.athletes._apoyo import claros_en

    blob = "apx1.0000.A256GCM.xx165yy.zz62500ww"
    assert claros_en({"weight_g": blob, "id": "a165b"}, ("165", "62500")) == []
    assert claros_en({"weight_g": blob, "extra": 165}, ("165", "62500")) == ["165"]
    assert claros_en({"notes": "Primera vez"}, ("Primera",)) == ["Primera"]
