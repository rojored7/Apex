"""`0036_results_wod_results` (S8-B1, US-169; S8-D10, S8-D35, S8-D41). Rojo B1.

Padre `0035_wods_wod_movements`. Crea el esquema `results` y `results.wod_results`: cargas en
gramos enteros, CHECK de forma (M-5), FK compuesta de la corrección y los cuatro índices.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_WOD_RESULTS
from tests.migrations._apoyo_notificaciones import (
    CHECK_VIOLATION,
    columnas,
    consultar,
    existe,
    resultados,
)
from tests.migrations.test_0023_attachments import _ejecutar

REVISION = "0036_results_wod_results"
PADRE = "0035_wods_wod_movements"
TABLA = "results.wod_results"
UNICO = "23505"
FK_VIOLATION = "23503"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
AHORA = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)

COLUMNAS = {
    "id": ("uuid", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
    "created_by": ("uuid", "NO"),
    "wod_id": ("uuid", "NO"),
    "member_id": ("uuid", "NO"),
    "session_id": ("uuid", "YES"),
    "wod_date": ("date", "NO"),
    "benchmark_id": ("uuid", "YES"),
    "level": ("text", "NO"),
    "seconds": ("integer", "YES"),
    "rounds": ("integer", "YES"),
    "reps": ("integer", "YES"),
    "load_g": ("integer", "YES"),
    "capped": ("boolean", "NO"),
    "scaled_movement_ids": ("ARRAY", "NO"),
    "status": ("text", "NO"),
    "recorded_by": ("uuid", "NO"),
    "validated_by": ("uuid", "YES"),
    "validated_at": ("timestamp with time zone", "YES"),
    "supersedes_id": ("uuid", "YES"),
    "is_current": ("boolean", "NO"),
    "source": ("text", "NO"),
}

WOD = uuid4()
OTRO_WOD = uuid4()
SOCIO = uuid4()
OTRO_SOCIO = uuid4()
COLS = (
    "id, created_by, wod_id, member_id, wod_date, level, seconds, reps, load_g, capped, "
    "scaled_movement_ids, status, recorded_by, validated_by, validated_at, supersedes_id, "
    "is_current, source"
)
INSERTAR = f"INSERT INTO results.wod_results ({COLS}) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::uuid[], $12, $13, $14, $15, $16, $17, $18)"  # noqa: S608,E501


def fila(**cambios: Any) -> tuple[str, list[Any]]:
    v: dict[str, Any] = {
        "id": uuid4(), "wod": WOD, "socio": SOCIO, "level": "rx", "seconds": 300, "reps": None,
        "load": None, "capped": False, "ids": [], "status": "validated", "vby": SYSTEM_USER_ID,
        "vat": AHORA, "sup": None, "current": True, "source": "desk",
    }  # fmt: skip
    v.update(cambios)
    return INSERTAR, [
        v["id"], SYSTEM_USER_ID, v["wod"], v["socio"], date(2026, 10, 21), v["level"], v["seconds"],
        v["reps"], v["load"], v["capped"], v["ids"], v["status"], SYSTEM_USER_ID, v["vby"],
        v["vat"], v["sup"], v["current"], v["source"],
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
            _ejecutar(migrated_database, LIMPIAR_WOD_RESULTS)


def _correr(base: str, *escenarios: list[tuple[str, list[Any]]]) -> list[tuple[str, str | None]]:
    return resultados(base, list(escenarios))


def test_cuelga_de_0035_y_esta_en_la_cadena(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_las_columnas(base: str) -> None:
    assert columnas(base, TABLA) == COLUMNAS


def test_check_validated_iff_validated_by_y_at(base: str) -> None:
    salidas = _correr(
        base,
        [fila(status="validated", vby=None, vat=None)],
        [fila(status="validated", vat=None)],
        [fila(status="pending")],
        [fila(status="pending", vby=None, vat=None)],
        [fila()],
    )
    nombre = "ck_wod_results_validated_pair"
    assert salidas == [
        (CHECK_VIOLATION, nombre), (CHECK_VIOLATION, nombre), (CHECK_VIOLATION, nombre),
        ("", None), ("", None),
    ]  # fmt: skip


def test_supersedes_distinto_de_id(base: str) -> None:
    propio = uuid4()
    salidas = _correr(base, [fila(id=propio, sup=propio)])
    assert salidas == [(CHECK_VIOLATION, "ck_wod_results_supersedes_not_self")]


def test_fk_compuesta_mismo_socio_y_wod(base: str) -> None:
    a = uuid4()
    primero = fila(id=a)
    apagar = ("UPDATE results.wod_results SET is_current = false WHERE id = $1", [a])
    salidas = _correr(
        base,
        [primero, apagar, fila(sup=a, socio=OTRO_SOCIO)],
        [primero, apagar, fila(sup=a, wod=OTRO_WOD)],
        [primero, apagar, fila(sup=a)],
        [fila(sup=uuid4())],
    )
    assert salidas == [
        (FK_VIOLATION, "fk_wod_results_supersedes"),
        (FK_VIOLATION, "fk_wod_results_supersedes"),
        ("", None),
        (FK_VIOLATION, "fk_wod_results_supersedes"),
    ]


def test_unico_parcial_vigente(base: str) -> None:
    salidas = _correr(
        base,
        [fila(), fila()],
        [fila(), fila(socio=OTRO_SOCIO)],
        [fila(), fila(wod=OTRO_WOD)],
    )
    assert salidas == [(UNICO, "uq_wod_results_current"), ("", None), ("", None)]


def test_un_resultado_se_corrige_una_vez(base: str) -> None:
    a, b = uuid4(), uuid4()
    apagar_a = ("UPDATE results.wod_results SET is_current = false WHERE id = $1", [a])
    apagar_b = ("UPDATE results.wod_results SET is_current = false WHERE id = $1", [b])
    salidas = _correr(
        base,
        [fila(id=a), apagar_a, fila(id=b, sup=a), apagar_b, fila(sup=a)],
        [fila(id=a), apagar_a, fila(id=b, sup=a), apagar_b, fila(sup=b)],
    )
    assert salidas == [(UNICO, "uq_wod_results_supersedes"), ("", None)]


def test_scaled_ids_solo_con_scaled_y_tope_30(base: str) -> None:
    treinta = [uuid4() for _ in range(30)]
    salidas = _correr(
        base,
        [fila(level="rx", ids=[uuid4()])],
        [fila(level="scaled", ids=[uuid4()])],
        [fila(level="scaled", ids=treinta)],
        [fila(level="scaled", ids=[*treinta, uuid4()])],
        [fila(level="rx", ids=[])],
    )
    assert salidas == [
        (CHECK_VIOLATION, "ck_wod_results_scaled_ids_level"),
        ("", None),
        ("", None),
        (CHECK_VIOLATION, "ck_wod_results_scaled_ids_max"),
        ("", None),
    ]


def test_rangos_cargas_en_gramos_y_forma_de_la_marca(base: str) -> None:
    casos = [
        (fila(seconds=0), "ck_wod_results_seconds"),
        (fila(seconds=86_401), "ck_wod_results_seconds"),
        (fila(seconds=None, reps=100_001), "ck_wod_results_reps"),
        (fila(seconds=None, load=-1), "ck_wod_results_load_g"),
        (fila(seconds=None, load=1_000_001), "ck_wod_results_load_g"),
        (fila(level="otro"), "ck_wod_results_level"),
        (fila(source="web"), "ck_wod_results_source"),
        (fila(capped=True, seconds=600, reps=None), "ck_wod_results_capped_shape"),
    ]
    assert _correr(base, *[[paso] for paso, _ in casos]) == [
        (CHECK_VIOLATION, nombre) for _, nombre in casos
    ]
    ok = _correr(
        base,
        [fila(seconds=None, load=0)],
        [fila(seconds=None, load=1_000_000)],
        [fila(capped=True, seconds=600, reps=40)],
    )
    assert ok == [("", None)] * 3


def test_los_cuatro_indices(base: str) -> None:
    filas = consultar(
        base,
        "SELECT indexname FROM pg_indexes "
        "WHERE schemaname = 'results' AND tablename = 'wod_results'",
    )
    nombres = {r["indexname"] for r in filas}
    assert {
        "uq_wod_results_current", "ix_wod_results_leaderboard", "uq_wod_results_supersedes",
        "ix_wod_results_member_date",
    } <= nombres  # fmt: skip


def test_ciclo_downgrade_upgrade(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert not existe(base, TABLA)
        assert existe(base, "wods.wod_movements")
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)
