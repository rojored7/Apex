"""Proyección pública de la TV (S8-C2, S8-D18, S8-D19): pura, sin base."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.modules.results.schemas import PublicRow
from app.modules.tv import rules
from app.modules.wods.schemas import WodMovementOut, WodOut
from tests.tv._apoyo import config

AHORA = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
DIA = date(2026, 10, 21)


def _wod() -> WodOut:
    return WodOut(
        id=uuid4(),
        date=DIA,
        title="Fran",
        score_type="time",
        time_cap_s=600,
        benchmark_id=uuid4(),
        benchmark_name="Fran",
        is_benchmark=True,
        description="21-15-9",
        movements=[
            WodMovementOut(
                id=uuid4(),
                movement_id=uuid4(),
                movement_name="Thruster",
                position=1,
                reps="21-15-9",
                load_rx_m_g=43_000,
                load_rx_f_g=30_000,
                notes="nota interna",
                is_primary=True,
            )
        ],
        result_count=3,
        created_at=AHORA,
        updated_at=AHORA,
    )


def _fila(posicion: int = 1, **cambios: object) -> PublicRow:
    valores: dict[str, object] = {
        "position": posicion,
        "first_name": "Ana María",
        "last_name": "pérez",
        "level": "rx",
        "seconds": 200,
        "rounds": None,
        "reps": None,
        "load_g": None,
        "capped": False,
    }
    valores.update(cambios)
    return PublicRow.model_validate(valores)


def test_display_name_ana_p() -> None:
    assert rules.display_name("Ana", "Pérez") == "Ana P."
    assert rules.display_name("Valentina", "R") == "Valentina R."


def test_primera_palabra_del_nombre() -> None:
    assert rules.display_name("Ana María", "pérez gómez") == "Ana P."
    assert rules.display_name("  Luis  Felipe ", " Zapata") == "Luis Z."


@pytest.mark.parametrize("apellido", ["", "   "])
def test_sin_apellido_solo_el_nombre(apellido: str) -> None:
    assert rules.display_name("Ana", apellido) == "Ana"


def test_claves_exactas_en_cada_nivel() -> None:
    tablero = rules.to_public_board(DIA, config(), _wod(), [_fila()])
    cuerpo = tablero.model_dump(mode="json")
    assert set(cuerpo) == {"date", "refresh_seconds", "wod", "leaderboard"}
    assert set(cuerpo["wod"]) == {
        "title",
        "score_type",
        "time_cap_s",
        "is_benchmark",
        "description",
        "movements",
    }
    assert set(cuerpo["wod"]["movements"][0]) == {"name", "reps", "load_rx_m_g", "load_rx_f_g"}
    assert set(cuerpo["leaderboard"][0]) == {"position", "display_name", "level", "score"}
    assert set(cuerpo["leaderboard"][0]["score"]) == {
        "seconds",
        "rounds",
        "reps",
        "load_g",
        "capped",
    }
    assert cuerpo["leaderboard"][0]["display_name"] == "Ana P."
    assert cuerpo["wod"]["movements"][0]["load_rx_m_g"] == 43_000


def test_sin_member_id_sexo_ni_scaled() -> None:
    texto = rules.to_public_board(DIA, config(), _wod(), [_fila()]).model_dump_json()
    for prohibido in ("member_id", "sex", "scaled", "notes", "nota interna", "result_id"):
        assert prohibido not in texto, prohibido
    assert "pérez" not in texto  # solo la inicial del apellido


def test_sin_wod_o_sin_ranking_las_listas_van_vacias() -> None:
    sin_wod = rules.to_public_board(DIA, config(), None, [_fila()])
    assert sin_wod.wod is None and sin_wod.leaderboard == []
    oculto = rules.to_public_board(DIA, config(show_leaderboard=False), _wod(), [_fila()])
    assert oculto.wod is not None and oculto.leaderboard == []


def test_refresh_y_fecha_salen_de_los_argumentos() -> None:
    tablero = rules.to_public_board(DIA, config(refresh_seconds=45), None, [])
    assert tablero.refresh_seconds == 45 and tablero.date == DIA
