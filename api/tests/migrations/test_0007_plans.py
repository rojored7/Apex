"""`0007_plans` (S2-B9, US-078 y US-079; DECISIÓN 32, S2-D32; blueprint B9).

Padre `0006_members`. Tabla `plans.plans`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`) y `deleted_at`;
- `name text`, `price_cop integer`, `kind text`, `duration_days integer`, `class_count integer`
  (nula) e `is_active boolean` (default `true`), todas no nulas salvo `class_count`;
- CHECKs: `price_cop > 0`, `duration_days > 0`, `kind IN ('days','classes')`,
  `(kind = 'classes' AND class_count IS NOT NULL AND class_count > 0) OR (kind = 'days' AND
  class_count IS NULL)` y `btrim(name) <> ''`; se prueban con `INSERT` crudo (SQLSTATE). El
  `IS NOT NULL` es obligatorio: sin él, `classes` con `class_count` nulo da NULL y el CHECK lo
  acepta (caso `classes-sin-clases`);
- `uq_plans_name_alive`: único sobre `lower(btrim(name))` donde `deleted_at IS NULL` ("Mensual"
  y "mensual" chocan; un plan dado de baja libera el nombre);
- `ix_plans_active_alive (is_active) WHERE deleted_at IS NULL`.
El `downgrade` borra la tabla y deja el esquema `plans` (lo crea `0001`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REVISION = "0007_plans"
PADRE = "0006_members"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
T_BAJA = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"
UNIQUE_VIOLATION = "23505"

TIMESTAMPTZ = "timestamp with time zone"
COLUMNAS: dict[str, tuple[str, str]] = {
    "id": ("uuid", "NO"),
    "created_at": (TIMESTAMPTZ, "NO"),
    "updated_at": (TIMESTAMPTZ, "NO"),
    "created_by": ("uuid", "NO"),
    "deleted_at": (TIMESTAMPTZ, "YES"),
    "name": ("text", "NO"),
    "price_cop": ("integer", "NO"),
    "kind": ("text", "NO"),
    "duration_days": ("integer", "NO"),
    "class_count": ("integer", "YES"),
    "is_active": ("boolean", "NO"),
}
INDICES = ("uq_plans_name_alive", "ix_plans_active_alive")


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _revision_existe(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:  # alembic.util.CommandError o ResolutionError
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")


def _estado(url: str) -> dict[str, Any]:
    async def consultar() -> dict[str, Any]:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            existe = await conexion.fetchval("SELECT to_regclass('plans.plans') IS NOT NULL")
            esquema = await conexion.fetchval(
                "SELECT count(*) FROM pg_namespace WHERE nspname = 'plans'"
            )
            if not existe:
                return {"existe": False, "esquema": bool(esquema)}
            columnas = {
                r["column_name"]: (r["data_type"], r["is_nullable"], r["column_default"])
                for r in await conexion.fetch(
                    "SELECT column_name, data_type, is_nullable, column_default "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'plans' AND table_name = 'plans'"
                )
            }
            indices = {
                r["indexname"]: r["indexdef"]
                for r in await conexion.fetch(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = 'plans' AND tablename = 'plans'"
                )
            }
            return {
                "existe": True,
                "esquema": bool(esquema),
                "columnas": columnas,
                "indices": indices,
            }
        finally:
            await conexion.close()

    return asyncio.run(consultar())


def _fila(**cambios: object) -> dict[str, object]:
    """Fila mínima válida (`days`, sin clases) con un nombre distinto en cada llamada."""
    fila: dict[str, object] = {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "name": f"Plan {uuid4().hex[:8]}",
        "price_cop": 120_000,
        "kind": "days",
        "duration_days": 30,
    }
    fila.update(cambios)
    return fila


async def _insertar(conexion: asyncpg.Connection, fila: dict[str, object]) -> None:
    columnas = list(fila)
    marcas = ", ".join(f"${i}" for i in range(1, len(columnas) + 1))
    sql = f"INSERT INTO plans.plans ({', '.join(columnas)}) VALUES ({marcas})"  # noqa: S608
    await conexion.execute(sql, *[fila[c] for c in columnas])


def _codigos(url: str, lotes: Sequence[Sequence[dict[str, object]]]) -> list[str]:
    """Cada lote va en una transacción que siempre se revierte; devuelve el SQLSTATE del primer
    error de cada lote, o "" si todas sus filas entraron."""

    async def correr() -> list[str]:
        conexion = await asyncpg.connect(_dsn(url))
        salida: list[str] = []
        try:
            for lote in lotes:
                transaccion = conexion.transaction()
                await transaccion.start()
                try:
                    for fila in lote:
                        await _insertar(conexion, fila)
                except asyncpg.PostgresError as error:
                    salida.append(str(error.sqlstate))
                else:
                    salida.append("")
                finally:
                    await transaccion.rollback()
            return salida
        finally:
            await conexion.close()

    return asyncio.run(correr())


def _codigo(url: str, *filas: dict[str, object]) -> str:
    return _codigos(url, [filas])[0]


def test_la_revision_existe_cuelga_de_0006_members_y_es_head(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    assert scripts.get_heads() == [REVISION]


def test_columnas_exactas_con_tipo_y_nulabilidad(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    estado = _estado(migrated_database)
    assert estado["existe"] is True
    assert {c: v[:2] for c, v in estado["columnas"].items()} == COLUMNAS


def test_defaults_de_is_active_y_fechas(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    columnas = _estado(migrated_database)["columnas"]
    assert columnas["is_active"][2] == "true"
    assert columnas["created_at"][2] == "now()"
    assert columnas["updated_at"][2] == "now()"
    for nula in ("class_count", "deleted_at"):
        assert columnas[nula][2] is None, nula


def test_un_plan_de_dias_y_una_tiquetera_entran(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    tiquetera = _fila(kind="classes", class_count=12, duration_days=60, is_active=False)
    topes = _fila(price_cop=1_000_000_000, duration_days=3_650)
    assert _codigos(migrated_database, [[_fila()], [tiquetera], [topes]]) == ["", "", ""]


@pytest.mark.parametrize(
    "cambios",
    [
        {"price_cop": 0},
        {"price_cop": -1},
        {"duration_days": 0},
        {"duration_days": -30},
        {"kind": "weeks"},
        {"kind": "DAYS"},
        {"kind": "days", "class_count": 5},
        {"kind": "days", "class_count": 0},
        {"kind": "classes", "class_count": None},
        {"kind": "classes", "class_count": 0},
        {"kind": "classes", "class_count": -2},
        {"name": ""},
        {"name": "   "},
    ],
    ids=[
        "precio-cero",
        "precio-negativo",
        "dias-cero",
        "dias-negativo",
        "tipo",
        "tipo-mayuscula",
        "days-con-clases",
        "days-con-cero-clases",
        "classes-sin-clases",
        "classes-con-cero",
        "classes-negativo",
        "nombre-vacio",
        "nombre-blanco",
    ],
)
def test_los_checks_rechazan_por_sql_crudo(
    alembic_config: Config, migrated_database: str, cambios: dict[str, object]
) -> None:
    _revision_existe(alembic_config)
    assert _codigo(migrated_database, _fila(**cambios)) == CHECK_VIOLATION


@pytest.mark.parametrize(
    "columna", ["name", "price_cop", "kind", "duration_days", "is_active", "created_by"]
)
def test_las_obligatorias_no_admiten_nulo(
    alembic_config: Config, migrated_database: str, columna: str
) -> None:
    _revision_existe(alembic_config)
    assert _codigo(migrated_database, _fila(**{columna: None})) == NOT_NULL_VIOLATION


@pytest.mark.parametrize(
    ("primero", "segundo"),
    [
        ("Mensual", "Mensual"),
        ("Mensual", "mensual"),
        ("Mensual", "MENSUAL"),
        ("Mensual", "  mensual  "),
        ("Tiquetera 12", "tiquetera 12 "),
    ],
    ids=["igual", "minusculas", "mayusculas", "espacios", "espacio-final"],
)
def test_el_nombre_es_unico_entre_vivos_sin_distinguir_mayusculas(
    alembic_config: Config, migrated_database: str, primero: str, segundo: str
) -> None:
    _revision_existe(alembic_config)
    assert _codigo(migrated_database, _fila(name=primero), _fila(name=segundo)) == UNIQUE_VIOLATION


def test_un_plan_dado_de_baja_libera_el_nombre(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    baja = {"name": "Mensual", "deleted_at": T_BAJA}
    codigos = _codigos(
        migrated_database,
        [
            [_fila(**baja), _fila(name="mensual")],
            [_fila(**baja), _fila(**baja)],
            [_fila(name="Mensual"), _fila(name="Trimestral")],
        ],
    )
    assert codigos == ["", "", ""]


def test_indices_unico_por_nombre_normalizado_y_de_activos_vivos(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    indices = _estado(migrated_database)["indices"]
    assert set(INDICES) <= set(indices), sorted(indices)
    unico = indices["uq_plans_name_alive"]
    assert "UNIQUE" in unico
    assert "lower(btrim(name))" in unico and "deleted_at IS NULL" in unico
    activos = indices["ix_plans_active_alive"]
    assert "UNIQUE" not in activos
    assert "(is_active)" in activos and "deleted_at IS NULL" in activos


def test_ciclo_de_0007(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    command.downgrade(alembic_config, PADRE)
    assert _estado(migrated_database) == {"existe": False, "esquema": True}
    command.upgrade(alembic_config, "head")
    estado = _estado(migrated_database)
    assert estado["existe"] is True
    assert {c: v[:2] for c, v in estado["columnas"].items()} == COLUMNAS
    assert set(INDICES) <= set(estado["indices"])
