"""`0026_class_slots` (S7-A2, US-155; S7-D9, M-3). Rojo A2.

Padre `0025_s6_hardening`; id de 16 caracteres (cabe en `varchar(32)`). Crea el esquema `classes`
y `classes.class_slots` (CHECK de días, duración, cupo y nombre), el índice por `is_active` y dos
triggers `ENABLE ALWAYS` (`class_slots_forbid_delete` y `_forbid_truncate`, `P0001`). Cada CHECK se
prueba con SQL crudo (asyncpg): 23514. `downgrade`: triggers, función, tabla y esquema.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_CLASS_SLOTS
from tests.migrations._apoyo_notificaciones import (
    CHECK_VIOLATION,
    columnas,
    consultar,
    existe,
    resultados,
)
from tests.migrations.test_0023_attachments import _ejecutar

REVISION = "0026_class_slots"
PADRE = "0025_s6_hardening"
TABLA = "classes.class_slots"
INMUTABLE = "P0001"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
TRIGGERS = ("class_slots_forbid_delete", "class_slots_forbid_truncate")

COLUMNAS = {
    "id": ("uuid", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
    "created_by": ("uuid", "NO"),
    "weekdays": ("ARRAY", "NO"),
    "start_time": ("time without time zone", "NO"),
    "duration_min": ("integer", "NO"),
    "capacity": ("integer", "NO"),
    "default_coach_id": ("uuid", "YES"),
    "name": ("text", "YES"),
    "valid_from": ("date", "NO"),
    "is_active": ("boolean", "NO"),
}

INSERTAR = (
    "INSERT INTO classes.class_slots (id, created_by, weekdays, start_time, duration_min, "
    "capacity, name, valid_from) VALUES ($1, $2, $3::smallint[], '06:00', $4, $5, $6, '2026-11-14')"
)


def _paso(**cambios: Any) -> tuple[str, list[Any]]:
    v: dict[str, Any] = {"w": [0, 2], "d": 60, "c": 15, "n": "WOD"}
    v.update(cambios)
    return INSERTAR, [uuid4(), SYSTEM_USER_ID, v["w"], v["d"], v["c"], v["n"]]


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
            _ejecutar(migrated_database, LIMPIAR_CLASS_SLOTS)


def test_la_revision_cuelga_de_0025_tiene_id_corto_y_esta_en_la_cadena(
    alembic_config: Config,
) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 31
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_el_esquema_y_las_columnas(base: str) -> None:
    assert consultar(base, "SELECT 1 FROM pg_namespace WHERE nspname = 'classes'")
    assert columnas(base, TABLA) == COLUMNAS


def test_indice_por_is_active(base: str) -> None:
    filas = consultar(
        base,
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = 'classes' AND tablename = 'class_slots'",
    )
    assert any(f["indexdef"].endswith("(is_active)") for f in filas)


def test_una_franja_valida_entra(base: str) -> None:
    assert resultados(
        base, [[_paso()], [_paso(w=[0, 1, 2, 3, 4, 5, 6], d=240, c=100, n=None)]]
    ) == [
        ("", None),
        ("", None),
    ]


def test_check_de_dias(base: str) -> None:
    malos = [[], [7], [-1], [0, 1, 2, 3, 4, 5, 6, 6]]
    salidas = resultados(base, [[_paso(w=w)] for w in malos])
    assert salidas == [(CHECK_VIOLATION, "ck_class_slots_weekdays")] * len(malos)


def test_check_de_duracion_cupo_y_nombre(base: str) -> None:
    casos = [
        (_paso(d=14), "ck_class_slots_duration_min"),
        (_paso(d=241), "ck_class_slots_duration_min"),
        (_paso(c=0), "ck_class_slots_capacity"),
        (_paso(c=101), "ck_class_slots_capacity"),
        (_paso(n=""), "ck_class_slots_name_length"),
        (_paso(n="x" * 41), "ck_class_slots_name_length"),
    ]
    salidas = resultados(base, [[paso] for paso, _ in casos])
    assert salidas == [(CHECK_VIOLATION, nombre) for _, nombre in casos]


def test_delete_y_truncate_estan_prohibidos(base: str) -> None:
    paso = _paso()
    salidas = resultados(
        base,
        [
            [paso, ("DELETE FROM classes.class_slots", [])],
            [paso, ("TRUNCATE classes.class_slots", [])],
        ],
    )
    assert [s for s, _ in salidas] == [INMUTABLE, INMUTABLE]


def test_los_dos_triggers_estan_en_always(base: str) -> None:
    filas = consultar(
        base,
        "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
        "WHERE tgrelid = 'classes.class_slots'::regclass AND NOT tgisinternal",
    )
    assert {f["tgname"]: f["estado"] for f in filas} == dict.fromkeys(TRIGGERS, "A")
    definicion = consultar(
        base,
        "SELECT prosecdef, proconfig FROM pg_proc "
        "WHERE oid = 'classes.forbid_mutation()'::regprocedure",
    )[0]
    assert definicion["prosecdef"] is False
    assert list(definicion["proconfig"]) == ["search_path=pg_catalog"]


def test_la_limpieza_deja_los_triggers_en_always(base: str) -> None:
    _ejecutar(base, LIMPIAR_CLASS_SLOTS)
    filas = consultar(
        base,
        "SELECT tgenabled::text AS estado FROM pg_trigger WHERE tgname = ANY($1::text[])",
        list(TRIGGERS),
    )
    assert [f["estado"] for f in filas] == ["A", "A"]


def test_ciclo_head_base_head(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, "base")
        assert not existe(base, TABLA)
        assert consultar(base, "SELECT 1 FROM pg_namespace WHERE nspname = 'classes'") == []
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)


def test_downgrade_a_0025_quita_tabla_triggers_funcion_y_esquema(
    alembic_config: Config, base: str
) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert not existe(base, TABLA)
        assert (
            consultar(
                base,
                "SELECT 1 FROM pg_proc WHERE oid::regprocedure::text = 'classes.forbid_mutation()'",
            )
            == []
        )
        assert consultar(base, "SELECT 1 FROM pg_namespace WHERE nspname = 'classes'") == []
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)
