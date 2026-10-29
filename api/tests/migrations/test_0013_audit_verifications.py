"""`0013_audit_verifications` (S4A-B3, US-104; S4A-D38, S4A-D43).

Padre `0012_worker_job_runs`; es head. Crea `audit.verifications`:
- `id uuid` PK; `started_at`, `finished_at timestamptz NOT NULL`; `through_seq bigint NOT NULL`
  (CHECK >= 0); `through_hash char(64) NOT NULL` (CHECK `^[0-9a-f]{64}$`, H-1); `rows_checked
  bigint NOT NULL` (CHECK >= 0); `ok boolean NOT NULL`; `broken_at_seq bigint NULL`;
  `triggered_by uuid NOT NULL`; `source text NOT NULL` (CHECK en `api`, `cli`); `created_at`,
  `updated_at`, `created_by`; CHECK de coherencia (`ok` sin `broken_at_seq`, no `ok` con él) y
  `started_at <= finished_at`;
- índice `ix_verifications_finished_at (finished_at DESC)`;
- triggers `verifications_forbid_mutation` (antes de UPDATE o DELETE, por fila) y
  `verifications_forbid_truncate` (antes de TRUNCATE) sobre la función EXISTENTE
  `audit.forbid_mutation()` de `0002`, con `ENABLE ALWAYS` (`tgenabled = 'A'`, S3-D49): siguen
  disparando con `session_replication_role = replica`.
`downgrade`: triggers, índice y tabla; conserva `audit.forbid_mutation()` (la usa `audit_log`).
Cada CHECK se prueba con SQL crudo (asyncpg): 23514. La inmutabilidad, con el SQLSTATE de la
función (`P0001`). Las filas insertadas se borran al terminar (`LIMPIAR_VERIFICATIONS`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_VERIFICATIONS

REVISION = "0013_audit_verifications"
PADRE = "0012_worker_job_runs"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
INICIO = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
FIN = INICIO + timedelta(seconds=2)
HASH = "0123456789abcdef" * 4
CHECK_VIOLATION = "23514"
INMUTABLE = "P0001"  # `audit.forbid_mutation()` (0002): RAISE ... USING ERRCODE = 'P0001'
TRIGGERS = ("verifications_forbid_mutation", "verifications_forbid_truncate")

COLUMNAS = {
    "id": ("uuid", "NO"),
    "started_at": ("timestamp with time zone", "NO"),
    "finished_at": ("timestamp with time zone", "NO"),
    "through_seq": ("bigint", "NO"),
    "through_hash": ("character", "NO"),
    "rows_checked": ("bigint", "NO"),
    "ok": ("boolean", "NO"),
    "broken_at_seq": ("bigint", "YES"),
    "triggered_by": ("uuid", "NO"),
    "source": ("text", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
    "created_by": ("uuid", "NO"),
}


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


def _consultar(url: str, sql: str, *args: Any) -> list[asyncpg.Record]:
    async def correr() -> list[asyncpg.Record]:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            return list(await conexion.fetch(sql, *args))
        finally:
            await conexion.close()

    return asyncio.run(correr())


def _ejecutar(url: str, *sentencias: str) -> None:
    async def correr() -> None:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            for sql in sentencias:
                await conexion.execute(sql)
        finally:
            await conexion.close()

    asyncio.run(correr())


def _insertar(url: str, **cambios: Any) -> UUID:
    valores: dict[str, Any] = {
        "id": uuid4(),
        "started_at": INICIO,
        "finished_at": FIN,
        "through_seq": 10,
        "through_hash": HASH,
        "rows_checked": 10,
        "ok": True,
        "broken_at_seq": None,
        "triggered_by": SYSTEM_USER_ID,
        "source": "api",
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)

    async def correr() -> None:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            await conexion.execute(
                "INSERT INTO audit.verifications (id, started_at, finished_at, through_seq, "
                "through_hash, rows_checked, ok, broken_at_seq, triggered_by, source, created_by) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)",
                *valores.values(),
            )
        finally:
            await conexion.close()

    asyncio.run(correr())
    return UUID(str(valores["id"]))


def _sqlstate(funcion: Any, *args: Any, **kwargs: Any) -> str | None:
    try:
        funcion(*args, **kwargs)
    except asyncpg.PostgresError as error:
        return str(error.sqlstate)
    return None


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> Iterator[str]:
    """La base migrada con `0013`; borra las verificaciones que la prueba deje."""
    _revision_existe(alembic_config)
    try:
        yield migrated_database
    finally:
        _ejecutar(migrated_database, LIMPIAR_VERIFICATIONS)


# Revisión ---------------------------------------------------------------------------------------


def test_la_revision_existe_cuelga_de_0012_y_es_head(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    assert scripts.get_heads() == [REVISION]


# Forma ------------------------------------------------------------------------------------------


def test_columnas_tipos_y_nulabilidad(base: str) -> None:
    filas = _consultar(
        base,
        "SELECT column_name, data_type, is_nullable, character_maximum_length AS largo "
        "FROM information_schema.columns "
        "WHERE table_schema = 'audit' AND table_name = 'verifications'",
    )
    assert {f["column_name"]: (f["data_type"], f["is_nullable"]) for f in filas} == COLUMNAS
    assert {f["column_name"]: f["largo"] for f in filas}["through_hash"] == 64


def test_indices(base: str) -> None:
    filas = _consultar(
        base,
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE schemaname = 'audit' AND tablename = 'verifications'",
    )
    indices = {f["indexname"]: f["indexdef"] for f in filas}
    assert set(indices) == {"pk_verifications", "ix_verifications_finished_at"}
    assert "UNIQUE" not in indices["ix_verifications_finished_at"]
    assert indices["ix_verifications_finished_at"].endswith("(finished_at DESC)")


def test_una_fila_valida_entra(base: str) -> None:
    assert _sqlstate(_insertar, base) is None
    assert _sqlstate(_insertar, base, ok=False, broken_at_seq=7, source="cli") is None
    assert _sqlstate(_insertar, base, through_seq=0, rows_checked=0, through_hash="0" * 64) is None
    assert _sqlstate(_insertar, base, started_at=FIN, finished_at=FIN) is None


# CHECKs (23514) ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cambios",
    [
        {"through_seq": -1},
        {"rows_checked": -1},
        {"source": "worker"},
        {"source": "API"},
        {"ok": True, "broken_at_seq": 5},
        {"ok": False, "broken_at_seq": None},
        {"started_at": FIN, "finished_at": INICIO},
        {"through_hash": "A" * 64},
        {"through_hash": "g" * 64},
        {"through_hash": "0" * 63 + " "},
    ],
    ids=[
        "through_seq_negativo",
        "rows_checked_negativo",
        "source_ajeno",
        "source_en_mayusculas",
        "ok_con_broken",
        "rota_sin_broken",
        "termina_antes_de_empezar",
        "hash_en_mayusculas",
        "hash_no_hexadecimal",
        "hash_con_espacio",
    ],
)
def test_cada_check_rechaza(base: str, cambios: dict[str, Any]) -> None:
    assert _sqlstate(_insertar, base, **cambios) == CHECK_VIOLATION


def test_through_hash_de_63_caracteres_se_rechaza(base: str) -> None:
    """`char(64)` rellena con espacios: 63 hexadecimales no cumplen el patrón (23514)."""
    assert _sqlstate(_insertar, base, through_hash="a" * 63) == CHECK_VIOLATION


# Inmutabilidad ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sentencia",
    [
        "UPDATE audit.verifications SET ok = false, broken_at_seq = 1",
        "DELETE FROM audit.verifications",
        "TRUNCATE audit.verifications",
    ],
    ids=["update", "delete", "truncate"],
)
def test_update_delete_y_truncate_se_rechazan(base: str, sentencia: str) -> None:
    _insertar(base)
    assert _sqlstate(_ejecutar, base, sentencia) == INMUTABLE
    assert len(_consultar(base, "SELECT id FROM audit.verifications")) == 1


@pytest.mark.parametrize(
    "sentencia",
    [
        "UPDATE audit.verifications SET ok = false, broken_at_seq = 1",
        "DELETE FROM audit.verifications",
    ],
    ids=["update", "delete"],
)
def test_bajo_replica_los_triggers_siguen_disparando(base: str, sentencia: str) -> None:
    _insertar(base)
    estado = _sqlstate(_ejecutar, base, "SET session_replication_role = replica", sentencia)
    assert estado == INMUTABLE
    assert len(_consultar(base, "SELECT id FROM audit.verifications")) == 1


def test_triggers_en_always_sobre_audit_forbid_mutation(base: str) -> None:
    filas = _consultar(
        base,
        "SELECT t.tgname, t.tgenabled::text AS estado, "
        "t.tgfoid = 'audit.forbid_mutation()'::regprocedure AS misma_funcion "
        "FROM pg_trigger t WHERE t.tgrelid = 'audit.verifications'::regclass "
        "AND NOT t.tgisinternal",
    )
    assert {f["tgname"]: (f["estado"], f["misma_funcion"]) for f in filas} == dict.fromkeys(
        TRIGGERS, ("A", True)
    )


# Ciclo ------------------------------------------------------------------------------------------


def _tabla_existe(url: str) -> bool:
    return bool(
        _consultar(url, "SELECT to_regclass('audit.verifications') IS NOT NULL AS hay")[0]["hay"]
    )


def _funcion_existe(url: str) -> bool:
    filas = _consultar(
        url,
        "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'audit' AND p.proname = 'forbid_mutation'",
    )
    return bool(filas)


def test_downgrade_quita_tabla_indice_y_triggers_y_conserva_la_funcion(
    alembic_config: Config, base: str
) -> None:
    assert _tabla_existe(base)
    try:
        command.downgrade(alembic_config, PADRE)
        assert not _tabla_existe(base)
        assert _funcion_existe(base)
        indices = _consultar(
            base,
            "SELECT indexname FROM pg_indexes WHERE indexname = 'ix_verifications_finished_at'",
        )
        assert indices == []
        triggers = _consultar(
            base, "SELECT tgname FROM pg_trigger WHERE tgname = ANY($1::text[])", list(TRIGGERS)
        )
        assert triggers == []
        # La cadena sigue protegida por la misma función.
        protegidos = _consultar(
            base,
            "SELECT tgname FROM pg_trigger WHERE tgrelid = 'audit.audit_log'::regclass "
            "AND NOT tgisinternal",
        )
        assert {f["tgname"] for f in protegidos} == {
            "audit_log_forbid_mutation",
            "audit_log_forbid_truncate",
        }
    finally:
        command.upgrade(alembic_config, "head")
    assert _tabla_existe(base)
