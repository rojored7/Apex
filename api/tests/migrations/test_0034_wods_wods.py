"""`0034_wods_wods` (S8-A3, US-166; S8-D7). Rojo A3.

Padre `0033_wods_benchmarks`. Crea `wods.wods` (fecha única, CHECK de tipo de marca, cap y largos,
FK al benchmark) y dos triggers `ENABLE ALWAYS` sobre `wods.forbid_mutation()` (de `0032`). La
revisión «está en la cadena de head» (E1), no «es head».
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_BENCHMARKS, LIMPIAR_WODS
from tests.migrations._apoyo_notificaciones import (
    CHECK_VIOLATION,
    columnas,
    consultar,
    existe,
    resultados,
)
from tests.migrations.test_0023_attachments import _ejecutar

REVISION = "0034_wods_wods"
PADRE = "0033_wods_benchmarks"
TABLA = "wods.wods"
INMUTABLE = "P0001"
UNICO = "23505"
FK_VIOLATION = "23503"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
TRIGGERS = ("wods_forbid_delete", "wods_forbid_truncate")

COLUMNAS = {
    "id": ("uuid", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
    "created_by": ("uuid", "NO"),
    "date": ("date", "NO"),
    "title": ("text", "NO"),
    "score_type": ("text", "NO"),
    "time_cap_s": ("integer", "YES"),
    "benchmark_id": ("uuid", "YES"),
    "description": ("text", "NO"),
}

INSERTAR = (
    "INSERT INTO wods.wods (id, created_by, date, title, score_type, time_cap_s, benchmark_id, "
    "description) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)"
)


def _paso(**cambios: Any) -> tuple[str, list[Any]]:
    v: dict[str, Any] = {
        "d": "2026-10-22", "t": "Fran", "s": "time", "c": 600, "b": None, "x": "",
    }  # fmt: skip
    v.update(cambios)
    return INSERTAR, [
        uuid4(),
        SYSTEM_USER_ID,
        date.fromisoformat(v["d"]),
        v["t"],
        v["s"],
        v["c"],
        v["b"],
        v["x"],
    ]


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
            _ejecutar(migrated_database, LIMPIAR_WODS)
            _ejecutar(migrated_database, LIMPIAR_BENCHMARKS)


def test_cuelga_de_0033_y_esta_en_la_cadena(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_las_columnas(base: str) -> None:
    assert columnas(base, TABLA) == COLUMNAS


def test_date_unico(base: str) -> None:
    salidas = resultados(
        base,
        [[_paso()], [_paso(), _paso(t="Otro")], [_paso(), _paso(d="2026-10-23", t="Otro")]],
    )
    assert salidas[0] == ("", None)
    assert salidas[1][0] == UNICO and salidas[1][1] == "uq_wods_date"
    assert salidas[2] == ("", None)


def test_un_wod_valido_por_tipo_de_marca(base: str) -> None:
    casos = [
        _paso(d="2026-10-01", s="time", c=600),
        _paso(d="2026-10-02", s="rounds_reps", c=14_400),
        _paso(d="2026-10-03", s="reps", c=None),
        _paso(d="2026-10-04", s="load", c=None),
        _paso(d="2026-10-05", s="none", c=None),
        _paso(d="2026-10-06", s="time", c=1),
    ]
    assert resultados(base, [[c] for c in casos]) == [("", None)] * 6


def test_check_de_tipo_cap_y_largos(base: str) -> None:
    casos = [
        (_paso(s="otro", c=None), "ck_wods_score_type"),
        (_paso(t=""), "ck_wods_title_length"),
        (_paso(t="x" * 81), "ck_wods_title_length"),
        (_paso(x="x" * 2001), "ck_wods_description_length"),
        (_paso(c=0), "ck_wods_time_cap"),
        (_paso(c=-1), "ck_wods_time_cap"),
        (_paso(c=14_401), "ck_wods_time_cap"),
        (_paso(s="reps", c=600), "ck_wods_time_cap"),
        (_paso(s="load", c=600), "ck_wods_time_cap"),
        (_paso(s="none", c=600), "ck_wods_time_cap"),
    ]
    salidas = resultados(base, [[paso] for paso, _ in casos])
    assert salidas == [(CHECK_VIOLATION, nombre) for _, nombre in casos]
    ok = resultados(base, [[_paso(t="x" * 80, x="x" * 2000)]])
    assert ok == [("", None)]


def test_fk_del_benchmark(base: str) -> None:
    salidas = resultados(base, [[_paso(b=uuid4())]])
    assert salidas[0] == (FK_VIOLATION, "fk_wods_benchmark_id")


def test_delete_y_truncate_prohibidos(base: str) -> None:
    paso = _paso()
    salidas = resultados(
        base,
        [[paso, ("DELETE FROM wods.wods", [])], [paso, ("TRUNCATE wods.wods", [])]],
    )
    # En head, `wod_movements` apunta a `wods`: PostgreSQL rechaza el TRUNCATE (0A000) antes del
    # trigger; el trigger de TRUNCATE existe y está en `A` (prueba de abajo).
    assert salidas[0][0] == INMUTABLE and salidas[1][0] in {INMUTABLE, "0A000"}


def test_los_dos_triggers_estan_en_always(base: str) -> None:
    filas = consultar(
        base,
        "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
        "WHERE tgrelid = 'wods.wods'::regclass AND NOT tgisinternal",
    )
    assert {f["tgname"]: f["estado"] for f in filas} == dict.fromkeys(TRIGGERS, "A")


def test_la_limpieza_deja_los_triggers_en_always(base: str) -> None:
    _ejecutar(base, LIMPIAR_WODS)
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
        assert existe(base, "wods.benchmarks")
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)
