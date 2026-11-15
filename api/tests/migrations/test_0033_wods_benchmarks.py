"""`0033_wods_benchmarks` (S8-A2, US-166; S8-D6). Rojo A2.

Padre `0032_wods_movements`; id de 19 caracteres. Crea `wods.benchmarks` (CHECK de `score_type` y
largos), el índice único sobre `name_norm` y dos triggers `ENABLE ALWAYS` que reutilizan
`wods.forbid_mutation()` (la función es de `0032`: `downgrade` de `0033` no la borra). La revisión
«está en la cadena de head» (E1), no «es head».
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_BENCHMARKS
from tests.migrations._apoyo_notificaciones import (
    CHECK_VIOLATION,
    columnas,
    consultar,
    existe,
    resultados,
)
from tests.migrations.test_0023_attachments import _ejecutar

REVISION = "0033_wods_benchmarks"
PADRE = "0032_wods_movements"
TABLA = "wods.benchmarks"
INMUTABLE = "P0001"
UNICO = "23505"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
TRIGGERS = ("benchmarks_forbid_delete", "benchmarks_forbid_truncate")

COLUMNAS = {
    "id": ("uuid", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
    "created_by": ("uuid", "NO"),
    "name": ("text", "NO"),
    "name_norm": ("text", "NO"),
    "description": ("text", "NO"),
    "score_type": ("text", "NO"),
}

INSERTAR = (
    "INSERT INTO wods.benchmarks (id, created_by, name, name_norm, description, score_type) "
    "VALUES ($1, $2, $3, $4, $5, $6)"
)


def _paso(**cambios: Any) -> tuple[str, list[Any]]:
    v: dict[str, Any] = {"n": "Fran", "nn": "fran", "d": "21-15-9", "s": "time"}
    v.update(cambios)
    return INSERTAR, [uuid4(), SYSTEM_USER_ID, v["n"], v["nn"], v["d"], v["s"]]


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
            _ejecutar(migrated_database, LIMPIAR_BENCHMARKS)


def test_cuelga_de_0032_y_esta_en_la_cadena(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_las_columnas(base: str) -> None:
    assert columnas(base, TABLA) == COLUMNAS


def test_name_norm_unico(base: str) -> None:
    salidas = resultados(
        base,
        [[_paso()], [_paso(), _paso(n="FRAN")], [_paso(), _paso(nn="grace", n="Grace")]],
    )
    assert salidas[0] == ("", None)
    assert salidas[1][0] == UNICO and salidas[1][1] == "uq_benchmarks_name_norm"
    assert salidas[2] == ("", None)


def test_un_benchmark_valido_por_tipo_de_marca(base: str) -> None:
    casos = [_paso(nn=s, s=s) for s in ("time", "rounds_reps", "reps", "load")]
    assert resultados(base, [[c] for c in casos]) == [("", None)] * 4


def test_check_de_tipo_y_largos(base: str) -> None:
    casos = [
        (_paso(s="none"), "ck_benchmarks_score_type"),
        (_paso(n=""), "ck_benchmarks_name_length"),
        (_paso(n="x" * 61), "ck_benchmarks_name_length"),
        (_paso(nn=""), "ck_benchmarks_name_norm_length"),
        (_paso(nn="x" * 61), "ck_benchmarks_name_norm_length"),
        (_paso(d="x" * 2001), "ck_benchmarks_description_length"),
    ]
    salidas = resultados(base, [[paso] for paso, _ in casos])
    assert salidas == [(CHECK_VIOLATION, nombre) for _, nombre in casos]
    assert resultados(base, [[_paso(d="x" * 2000)], [_paso(nn="v", d="")]]) == [("", None)] * 2


def test_delete_y_truncate_prohibidos(base: str) -> None:
    paso = _paso()
    salidas = resultados(
        base,
        [
            [paso, ("DELETE FROM wods.benchmarks", [])],
            [paso, ("TRUNCATE wods.benchmarks", [])],
        ],
    )
    # Desde A3 otra tabla apunta a esta (FK): PostgreSQL rechaza el TRUNCATE (0A000) antes del
    # trigger; el trigger de TRUNCATE sigue en `A` (prueba de los triggers).
    assert salidas[0][0] == INMUTABLE and salidas[1][0] in {INMUTABLE, "0A000"}


def test_los_dos_triggers_estan_en_always(base: str) -> None:
    filas = consultar(
        base,
        "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
        "WHERE tgrelid = 'wods.benchmarks'::regclass AND NOT tgisinternal",
    )
    assert {f["tgname"]: f["estado"] for f in filas} == dict.fromkeys(TRIGGERS, "A")


def test_la_limpieza_deja_los_triggers_en_always(base: str) -> None:
    _ejecutar(base, LIMPIAR_BENCHMARKS)
    filas = consultar(
        base,
        "SELECT tgenabled::text AS estado FROM pg_trigger WHERE tgname = ANY($1::text[])",
        list(TRIGGERS),
    )
    assert [f["estado"] for f in filas] == ["A", "A"]


def test_ciclo_downgrade_upgrade_conserva_la_funcion_de_0032(
    alembic_config: Config, base: str
) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert not existe(base, TABLA)
        assert existe(base, "wods.movements")
        assert consultar(
            base,
            "SELECT 1 FROM pg_proc WHERE oid::regprocedure::text = 'wods.forbid_mutation()'",
        )
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)
