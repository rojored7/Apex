"""`0035_wods_wod_movements` (S8-A3, US-166; S8-D7, S8-D41). Rojo A3.

Padre `0034_wods_wods`. Crea `wods.wod_movements`: posición única por WOD, índice único parcial del
principal, cargas en gramos enteros con CHECK de 0 a 1.000.000 y `DELETE` permitido (E6).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_BENCHMARKS, LIMPIAR_MOVEMENTS, LIMPIAR_WODS
from tests.migrations._apoyo_notificaciones import (
    CHECK_VIOLATION,
    columnas,
    consultar,
    existe,
    resultados,
)
from tests.migrations.test_0023_attachments import _ejecutar

REVISION = "0035_wods_wod_movements"
PADRE = "0034_wods_wods"
TABLA = "wods.wod_movements"
UNICO = "23505"
FK_VIOLATION = "23503"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

COLUMNAS = {
    "id": ("uuid", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
    "created_by": ("uuid", "NO"),
    "wod_id": ("uuid", "NO"),
    "movement_id": ("uuid", "NO"),
    "movement_name": ("text", "NO"),
    "position": ("integer", "NO"),
    "reps": ("text", "NO"),
    "load_rx_m_g": ("integer", "YES"),
    "load_rx_f_g": ("integer", "YES"),
    "notes": ("text", "NO"),
    "is_primary": ("boolean", "NO"),
}

WOD = uuid4()
OTRO_WOD = uuid4()
MOVIMIENTO = uuid4()
PREPARAR: list[tuple[str, list[Any]]] = [
    (
        "INSERT INTO wods.movements (id, created_by, name, name_norm, category, unit) "
        "VALUES ($1, $2, 'Thruster', 'thruster', 'weightlifting', 'kg')",
        [MOVIMIENTO, SYSTEM_USER_ID],
    ),
    (
        "INSERT INTO wods.wods (id, created_by, date, title, score_type) "
        "VALUES ($1, $2, '2026-10-22', 'Fran', 'time')",
        [WOD, SYSTEM_USER_ID],
    ),
    (
        "INSERT INTO wods.wods (id, created_by, date, title, score_type) "
        "VALUES ($1, $2, '2026-10-23', 'Otro', 'time')",
        [OTRO_WOD, SYSTEM_USER_ID],
    ),
]
INSERTAR = (
    "INSERT INTO wods.wod_movements (id, created_by, wod_id, movement_id, movement_name, "
    "position, reps, load_rx_m_g, load_rx_f_g, notes, is_primary) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)"
)


def _paso(**cambios: Any) -> tuple[str, list[Any]]:
    v: dict[str, Any] = {
        "w": WOD, "m": MOVIMIENTO, "n": "Thruster", "p": 1, "r": "21-15-9",
        "lm": 43_000, "lf": 30_000, "no": "", "pr": False,
    }  # fmt: skip
    v.update(cambios)
    return INSERTAR, [
        uuid4(), SYSTEM_USER_ID, v["w"], v["m"], v["n"], v["p"], v["r"], v["lm"], v["lf"],
        v["no"], v["pr"],
    ]  # fmt: skip


def _revision_existe(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> Iterator[str]:
    _revision_existe(alembic_config)
    try:
        yield migrated_database
    finally:
        if existe(migrated_database, TABLA):
            for sql in (LIMPIAR_WODS, LIMPIAR_BENCHMARKS, LIMPIAR_MOVEMENTS):
                _ejecutar(migrated_database, sql)


def _correr(base: str, *grupos: list[tuple[str, list[Any]]]) -> list[tuple[str, str | None]]:
    return resultados(base, [[*PREPARAR, *g] for g in grupos])


def test_cuelga_de_0034_y_esta_en_la_cadena(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_las_columnas(base: str) -> None:
    assert columnas(base, TABLA) == COLUMNAS


def test_un_solo_principal_por_wod(base: str) -> None:
    salidas = _correr(
        base,
        [_paso(pr=True)],
        [_paso(pr=True), _paso(p=2, pr=True)],
        [_paso(pr=True), _paso(p=2), _paso(p=3)],
        [_paso(pr=True), _paso(w=OTRO_WOD, pr=True)],
    )
    assert salidas[0] == ("", None)
    assert salidas[1] == (UNICO, "uq_wod_movements_primary")
    assert salidas[2] == ("", None)
    assert salidas[3] == ("", None)


def test_position_unica(base: str) -> None:
    salidas = _correr(base, [_paso(), _paso()], [_paso(), _paso(p=2)], [_paso(), _paso(w=OTRO_WOD)])
    assert salidas[0] == (UNICO, "uq_wod_movements_wod_position")
    assert salidas[1] == ("", None) and salidas[2] == ("", None)


def test_check_de_cargas_posicion_y_largos(base: str) -> None:
    casos = [
        (_paso(lm=-1), "ck_wod_movements_load_rx_m_g"),
        (_paso(lm=1_000_001), "ck_wod_movements_load_rx_m_g"),
        (_paso(lf=-1), "ck_wod_movements_load_rx_f_g"),
        (_paso(lf=1_000_001), "ck_wod_movements_load_rx_f_g"),
        (_paso(p=0), "ck_wod_movements_position"),
        (_paso(p=31), "ck_wod_movements_position"),
        (_paso(n=""), "ck_wod_movements_movement_name_length"),
        (_paso(r="x" * 41), "ck_wod_movements_reps_length"),
        (_paso(no="x" * 201), "ck_wod_movements_notes_length"),
    ]
    assert _correr(base, *[[paso] for paso, _ in casos]) == [
        (CHECK_VIOLATION, nombre) for _, nombre in casos
    ]
    ok = _correr(
        base,
        [_paso(lm=0, lf=1_000_000, r="x" * 40, no="x" * 200, p=30)],
        [_paso(lm=None, lf=None, r="")],
    )
    assert ok == [("", None), ("", None)]


def test_fk_de_wod_y_de_movimiento(base: str) -> None:
    salidas = _correr(base, [_paso(w=uuid4())], [_paso(m=uuid4())])
    assert salidas == [
        (FK_VIOLATION, "fk_wod_movements_wod_id"),
        (FK_VIOLATION, "fk_wod_movements_movement_id"),
    ]


def test_delete_permitido_truncate_no_hay_trigger_de_guarda(base: str) -> None:
    salidas = _correr(base, [_paso(), ("DELETE FROM wods.wod_movements", [])])
    assert salidas == [("", None)]
    filas = consultar(
        base,
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'wods.wod_movements'::regclass "
        "AND NOT tgisinternal",
    )
    assert filas == []


def test_el_wod_no_se_borra_aunque_tenga_movimientos(base: str) -> None:
    salidas = _correr(base, [_paso(), ("DELETE FROM wods.wods", [])])
    assert salidas[0][0] == "P0001"


def test_ciclo_downgrade_upgrade(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert not existe(base, TABLA)
        assert existe(base, "wods.wods")
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)
