"""`derive_rm`: la regla pura del RM derivado (S9-B3, US-181; S9-D10). Sin base ni bus.

Valores a mano, en gramos enteros (S8-D41): la marca solo deriva si el WOD es de tipo `load`, tiene
movimiento principal, el nivel no es `scaled`, la carga es mayor que 0 y ESTRICTAMENTE mayor que el
RM vigente (o no hay vigente). `rx_plus` deriva igual que `rx`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.modules.athletes.rules import RecordDraft, RecordRow, derive_rm
from app.modules.results.schemas import ResultMark
from app.modules.wods.catalog import WodRecordMeta

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
        "benchmark_id": None,
        "level": "rx",
        "seconds": None,
        "rounds": None,
        "reps": None,
        "load_g": 100_000,
        "capped": False,
        "status": "validated",
        "is_current": True,
        "supersedes_id": None,
        "validated_by": VALIDADOR,
        "source": "desk",
    }
    valores.update(cambios)
    return ResultMark(**valores)


def meta(**cambios: Any) -> WodRecordMeta:
    valores: dict[str, Any] = {
        "score_type": "load",
        "primary_movement_id": MOVIMIENTO,
        "benchmark_id": None,
        "date": DIA,
    }
    valores.update(cambios)
    return WodRecordMeta(**valores)


def vigente(value_g: int) -> RecordRow:
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
        achieved_on=date(2026, 10, 1),
        created_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )


def test_una_carga_mayor_que_el_vigente_crea_el_borrador_completo() -> None:
    borrador = derive_rm(marca(load_g=100_000), meta(), vigente(95_000))

    assert borrador == RecordDraft(
        kind="rm",
        movement_id=MOVIMIENTO,
        benchmark_id=None,
        value_g=100_000,
        level=None,
        seconds=None,
        rounds=None,
        reps=None,
        load_g=None,
        capped=False,
        achieved_on=DIA,
        result_id=RESULTADO,
        wod_id=WOD,
    )


def test_una_carga_igual_al_vigente_no_crea() -> None:
    assert derive_rm(marca(load_g=95_000), meta(), vigente(95_000)) is None


def test_una_carga_menor_que_el_vigente_no_crea() -> None:
    assert derive_rm(marca(load_g=90_000), meta(), vigente(95_000)) is None


def test_un_gramo_mas_que_el_vigente_crea() -> None:
    borrador = derive_rm(marca(load_g=95_001), meta(), vigente(95_000))

    assert borrador is not None and borrador.value_g == 95_001


def test_sin_vigente_la_primera_carga_crea() -> None:
    borrador = derive_rm(marca(load_g=60_000), meta(), None)

    assert borrador is not None and borrador.value_g == 60_000


def test_cero_gramos_no_crea_ni_sin_vigente() -> None:
    assert derive_rm(marca(load_g=0), meta(), None) is None
    assert derive_rm(marca(load_g=0), meta(), vigente(95_000)) is None


def test_load_g_ausente_no_crea() -> None:
    assert derive_rm(marca(load_g=None), meta(), None) is None


def test_un_scaled_no_deriva_aunque_supere_al_vigente() -> None:
    assert derive_rm(marca(level="scaled", load_g=200_000), meta(), vigente(95_000)) is None
    assert derive_rm(marca(level="scaled", load_g=200_000), meta(), None) is None


@pytest.mark.parametrize("nivel", ["rx", "rx_plus"])
def test_rx_y_rx_plus_derivan_igual(nivel: str) -> None:
    borrador = derive_rm(marca(level=nivel, load_g=100_000), meta(), vigente(95_000))

    assert borrador is not None and borrador.value_g == 100_000 and borrador.level is None


def test_sin_movimiento_principal_no_deriva() -> None:
    assert derive_rm(marca(), meta(primary_movement_id=None), None) is None


@pytest.mark.parametrize("tipo", ["time", "rounds_reps", "reps", "none"])
def test_un_wod_que_no_es_de_carga_no_deriva(tipo: str) -> None:
    assert derive_rm(marca(load_g=100_000), meta(score_type=tipo), None) is None


def test_la_fecha_del_borrador_es_la_del_wod_de_la_marca() -> None:
    borrador = derive_rm(marca(wod_date=date(2026, 9, 3)), meta(date=date(2026, 9, 3)), None)

    assert borrador is not None and borrador.achieved_on == date(2026, 9, 3)


def test_no_muta_ni_depende_del_vigente_invalidado_que_no_se_le_pasa() -> None:
    """La regla compara solo con el `current` recibido: el handler decide qué vigente leer."""
    actual = vigente(95_000)

    derive_rm(marca(load_g=100_000), meta(), actual)

    assert actual.value_g == 95_000
