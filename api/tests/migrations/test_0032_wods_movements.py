"""`0032_wods_movements` (S8-A1, US-165; S8-D5). Rojo A1.

Padre `0031_refresh_kiosk_path`; id de 20 caracteres (cabe en `varchar(32)`). Crea el esquema `wods`
y `wods.movements` (CHECK de categoría, unidad y largos), el índice único sobre `name_norm` y dos
triggers `ENABLE ALWAYS` (`movements_forbid_delete` y `_forbid_truncate`, `P0001`). Cada CHECK y la
unicidad se prueban con SQL crudo (asyncpg). `downgrade`: triggers, función, tabla y esquema.
La revisión «está en la cadena de head» (E1), no «es head».
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_MOVEMENTS
from tests.migrations._apoyo_notificaciones import (
    CHECK_VIOLATION,
    columnas,
    consultar,
    existe,
    resultados,
)
from tests.migrations.test_0023_attachments import _ejecutar

REVISION = "0032_wods_movements"
PADRE = "0031_refresh_kiosk_path"
TABLA = "wods.movements"
INMUTABLE = "P0001"
UNICO = "23505"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
TRIGGERS = ("movements_forbid_delete", "movements_forbid_truncate")

COLUMNAS = {
    "id": ("uuid", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
    "created_by": ("uuid", "NO"),
    "name": ("text", "NO"),
    "name_norm": ("text", "NO"),
    "category": ("text", "NO"),
    "unit": ("text", "NO"),
    "is_active": ("boolean", "NO"),
}

INSERTAR = (
    "INSERT INTO wods.movements (id, created_by, name, name_norm, category, unit) "
    "VALUES ($1, $2, $3, $4, $5, $6)"
)


def _paso(**cambios: Any) -> tuple[str, list[Any]]:
    v: dict[str, Any] = {"n": "Back Squat", "nn": "back squat", "c": "weightlifting", "u": "kg"}
    v.update(cambios)
    return INSERTAR, [uuid4(), SYSTEM_USER_ID, v["n"], v["nn"], v["c"], v["u"]]


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
            _ejecutar(migrated_database, LIMPIAR_MOVEMENTS)


def test_cuelga_de_0031_y_esta_en_la_cadena(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_el_esquema_y_las_columnas(base: str) -> None:
    assert consultar(base, "SELECT 1 FROM pg_namespace WHERE nspname = 'wods'")
    assert columnas(base, TABLA) == COLUMNAS


def test_name_norm_unico(base: str) -> None:
    salidas = resultados(
        base,
        [[_paso()], [_paso(), _paso(n="BACK SQUAT")], [_paso(), _paso(nn="otro", n="Otro")]],
    )
    assert salidas[0] == ("", None)
    assert salidas[1][0] == UNICO and salidas[1][1] == "uq_movements_name_norm"
    assert salidas[2] == ("", None)


def test_un_movimiento_valido_por_categoria_y_unidad(base: str) -> None:
    casos = [
        _paso(nn="a", c="weightlifting", u="kg"),
        _paso(nn="b", c="gymnastics", u="reps"),
        _paso(nn="c", c="monostructural", u="m"),
        _paso(nn="d", c="other", u="cal"),
        _paso(nn="e", c="other", u="s"),
    ]
    assert resultados(base, [[c] for c in casos]) == [("", None)] * len(casos)


def test_check_de_categoria_unidad_y_largos(base: str) -> None:
    casos = [
        (_paso(c="cardio"), "ck_movements_category"),
        (_paso(u="lb"), "ck_movements_unit"),
        (_paso(n=""), "ck_movements_name_length"),
        (_paso(n="x" * 61), "ck_movements_name_length"),
        (_paso(nn=""), "ck_movements_name_norm_length"),
        (_paso(nn="x" * 61), "ck_movements_name_norm_length"),
    ]
    salidas = resultados(base, [[paso] for paso, _ in casos])
    assert salidas == [(CHECK_VIOLATION, nombre) for _, nombre in casos]


def test_delete_y_truncate_prohibidos(base: str) -> None:
    paso = _paso()
    salidas = resultados(
        base,
        [
            [paso, ("DELETE FROM wods.movements", [])],
            [paso, ("TRUNCATE wods.movements", [])],
        ],
    )
    assert [s for s, _ in salidas] == [INMUTABLE, INMUTABLE]


def test_los_dos_triggers_estan_en_always(base: str) -> None:
    filas = consultar(
        base,
        "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
        "WHERE tgrelid = 'wods.movements'::regclass AND NOT tgisinternal",
    )
    assert {f["tgname"]: f["estado"] for f in filas} == dict.fromkeys(TRIGGERS, "A")
    definicion = consultar(
        base,
        "SELECT prosecdef, proconfig FROM pg_proc "
        "WHERE oid = 'wods.forbid_mutation()'::regprocedure",
    )[0]
    assert definicion["prosecdef"] is False
    assert list(definicion["proconfig"]) == ["search_path=pg_catalog"]


def test_la_limpieza_deja_los_triggers_en_always(base: str) -> None:
    _ejecutar(base, LIMPIAR_MOVEMENTS)
    filas = consultar(
        base,
        "SELECT tgenabled::text AS estado FROM pg_trigger WHERE tgname = ANY($1::text[])",
        list(TRIGGERS),
    )
    assert [f["estado"] for f in filas] == ["A", "A"]


def test_ciclo_downgrade_upgrade(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert not existe(base, TABLA)
        assert consultar(base, "SELECT 1 FROM pg_namespace WHERE nspname = 'wods'") == []
        assert (
            consultar(
                base,
                "SELECT 1 FROM pg_proc WHERE oid::regprocedure::text = 'wods.forbid_mutation()'",
            )
            == []
        )
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)
