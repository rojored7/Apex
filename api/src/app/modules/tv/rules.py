"""Proyección pública de la TV (S8-C2, S8-D18, S8-D19). Puro: sin sesión, reloj ni base."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from app.modules.results.schemas import PublicRow
from app.modules.settings.schemas import TvConfig
from app.modules.tv.schemas import TvBoard, TvMovement, TvRow, TvScore, TvWod
from app.modules.wods.schemas import WodOut


def display_name(first_name: str, last_name: str) -> str:
    """«Ana P.»: primera palabra del nombre e inicial del apellido (sin apellido, el nombre)."""
    palabras = first_name.split()
    nombre = palabras[0] if palabras else ""
    inicial = last_name.strip()[:1].upper()
    return f"{nombre} {inicial}." if inicial else nombre


def _wod(wod: WodOut) -> TvWod:
    return TvWod(
        title=wod.title,
        score_type=wod.score_type,
        time_cap_s=wod.time_cap_s,
        is_benchmark=wod.is_benchmark,
        description=wod.description,
        movements=[
            TvMovement(
                name=m.movement_name,
                reps=m.reps,
                load_rx_m_g=m.load_rx_m_g,
                load_rx_f_g=m.load_rx_f_g,
            )
            for m in wod.movements
        ],
    )


def _row(fila: PublicRow) -> TvRow:
    return TvRow(
        position=fila.position,
        display_name=display_name(fila.first_name, fila.last_name),
        level=fila.level,
        score=TvScore(
            seconds=fila.seconds,
            rounds=fila.rounds,
            reps=fila.reps,
            load_g=fila.load_g,
            capped=fila.capped,
        ),
    )


def to_public_board(
    day: date, config: TvConfig, wod: WodOut | None, rows: Sequence[PublicRow]
) -> TvBoard:
    """Solo deja los campos de la lista blanca; sin WOD o sin ranking las listas van vacías."""
    visibles = rows if wod is not None and config.show_leaderboard else ()
    return TvBoard(
        date=day,
        refresh_seconds=config.refresh_seconds,
        show_leaderboard=config.show_leaderboard,
        wod=_wod(wod) if wod is not None else None,
        leaderboard=[_row(f) for f in visibles],
    )
