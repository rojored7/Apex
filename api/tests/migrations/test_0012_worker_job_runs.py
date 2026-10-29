"""`0012_worker_job_runs` (S4A-B1, US-113; S4A-D3, S4A-D38).

Padre `0011_payments_immutability`; desde S4A-B3 `0013_audit_verifications` cuelga de ella (está en
la cadena de head, ya no es head). Crea `worker.job_runs`:
- `id uuid` PK; `job_name text NOT NULL` con CHECK `^[a-z][a-z0-9_]{1,62}$` (2 a 63 caracteres,
  minúscula inicial); `run_date date NOT NULL`; `started_at timestamptz NOT NULL`; `finished_at
  timestamptz NULL`; `result text NOT NULL` con CHECK en `running`, `ok`, `error` y los de backup
  de US-115 (`ok_unverified`, `stale`, `missing`, `corrupt`, `undecryptable`); `error text NULL`;
  `details jsonb NOT NULL DEFAULT '{}'`; `created_at`, `updated_at`, `created_by uuid NOT NULL`;
  CHECK `finished_at IS NULL OR finished_at >= started_at`;
- índice único `uq_job_runs_name_date (job_name, run_date)` e índice `ix_job_runs_name_started
  (job_name, started_at DESC)`; sin triggers.
`downgrade`: los dos índices y la tabla, nunca el esquema `worker` (de `0001`).
Cada CHECK se prueba con SQL crudo (asyncpg): 23514 y 23505. Las filas que se insertan se borran
al terminar (`LIMPIAR_JOB_RUNS`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_JOB_RUNS

REVISION = "0012_worker_job_runs"
PADRE = "0011_payments_immutability"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
INICIO = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
DIA = date(2026, 10, 21)
CHECK_VIOLATION = "23514"
UNIQUE_VIOLATION = "23505"

COLUMNAS = {
    "id": ("uuid", "NO"),
    "job_name": ("text", "NO"),
    "run_date": ("date", "NO"),
    "started_at": ("timestamp with time zone", "NO"),
    "finished_at": ("timestamp with time zone", "YES"),
    "result": ("text", "NO"),
    "error": ("text", "YES"),
    "details": ("jsonb", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
    "created_by": ("uuid", "NO"),
}
RESULTADOS = (
    "running",
    "ok",
    "error",
    "ok_unverified",
    "stale",
    "missing",
    "corrupt",
    "undecryptable",
)


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


def _ejecutar(url: str, sql: str, *args: Any) -> None:
    async def correr() -> None:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            await conexion.execute(sql, *args)
        finally:
            await conexion.close()

    asyncio.run(correr())


def _insertar(
    url: str,
    *,
    job_name: str = "expirations",
    run_date: date = DIA,
    result: str = "ok",
    started_at: datetime = INICIO,
    finished_at: datetime | None = INICIO,
) -> None:
    _ejecutar(
        url,
        "INSERT INTO worker.job_runs (id, job_name, run_date, started_at, finished_at, result, "
        "created_by) VALUES ($1, $2, $3, $4, $5, $6, $7)",
        uuid4(),
        job_name,
        run_date,
        started_at,
        finished_at,
        result,
        SYSTEM_USER_ID,
    )


def _sqlstate_al_insertar(url: str, **valores: Any) -> str | None:
    try:
        _insertar(url, **valores)
    except asyncpg.PostgresError as error:
        return str(error.sqlstate)
    return None


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> Iterator[str]:
    """La base migrada con `0012`; borra las corridas que la prueba deje."""
    _revision_existe(alembic_config)
    try:
        yield migrated_database
    finally:
        _ejecutar(migrated_database, LIMPIAR_JOB_RUNS)


# Revisión ---------------------------------------------------------------------------------------


def test_la_revision_existe_cuelga_de_0011_y_esta_en_la_cadena_de_head(
    alembic_config: Config,
) -> None:
    """Desde S4A-B3 `0013_audit_verifications` cuelga de esta revisión (P-MIG paso 9, S4A-D38): ya
    no es head, pero sigue en la cadena que llega a head y es la madre directa de `0013` (la
    cabeza única la exige `test_single_head`)."""
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    cadena = {r.revision for r in scripts.walk_revisions("base", "heads")}
    assert REVISION in cadena
    assert scripts.get_heads() != [REVISION]
    hijas = [
        r.revision for r in scripts.walk_revisions("base", "heads") if r.down_revision == REVISION
    ]
    assert hijas == ["0013_audit_verifications"]


# Forma de la tabla ------------------------------------------------------------------------------


def test_columnas_tipos_y_nulabilidad(base: str) -> None:
    filas = _consultar(
        base,
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'worker' AND table_name = 'job_runs'",
    )
    assert {f["column_name"]: (f["data_type"], f["is_nullable"]) for f in filas} == COLUMNAS


def test_details_vale_objeto_vacio_por_defecto(base: str) -> None:
    _insertar(base)
    filas = _consultar(base, "SELECT details::text AS d FROM worker.job_runs")
    assert [f["d"] for f in filas] == ["{}"]


def test_sin_triggers(base: str) -> None:
    filas = _consultar(
        base,
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'worker.job_runs'::regclass "
        "AND NOT tgisinternal",
    )
    assert filas == []


def test_indices_unico_por_dia_y_por_inicio_descendente(base: str) -> None:
    filas = _consultar(
        base,
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE schemaname = 'worker' AND tablename = 'job_runs'",
    )
    indices = {f["indexname"]: f["indexdef"] for f in filas}
    assert set(indices) == {"pk_job_runs", "uq_job_runs_name_date", "ix_job_runs_name_started"}
    assert "CREATE UNIQUE INDEX" in indices["uq_job_runs_name_date"]
    assert indices["uq_job_runs_name_date"].endswith("(job_name, run_date)")
    assert "UNIQUE" not in indices["ix_job_runs_name_started"]
    assert indices["ix_job_runs_name_started"].endswith("(job_name, started_at DESC)")


# CHECKs (23514) ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "job_name",
    ["Expirations", "e", "a" * 64, "1expirations", "_expirations", "expira-tions", "expira tions"],
    ids=[
        "mayuscula",
        "un_caracter",
        "64_caracteres",
        "digito_inicial",
        "guion_bajo_inicial",
        "guion",
        "espacio",
    ],
)
def test_check_de_forma_de_job_name_rechaza(base: str, job_name: str) -> None:
    assert _sqlstate_al_insertar(base, job_name=job_name) == CHECK_VIOLATION


@pytest.mark.parametrize(
    "job_name", ["ab", "a" * 63, "expirations", "expirations_sim", "sign_audit2"]
)
def test_check_de_forma_de_job_name_acepta(base: str, job_name: str) -> None:
    assert _sqlstate_al_insertar(base, job_name=job_name) is None


@pytest.mark.parametrize("result", ["pending", "OK", "", "failed"])
def test_check_de_result_rechaza_lo_que_no_esta_en_la_lista(base: str, result: str) -> None:
    assert _sqlstate_al_insertar(base, result=result) == CHECK_VIOLATION


def test_check_de_result_acepta_los_ocho_valores(base: str) -> None:
    for indice, result in enumerate(RESULTADOS):
        fin = None if result == "running" else INICIO
        estado = _sqlstate_al_insertar(
            base, result=result, run_date=DIA + timedelta(days=indice), finished_at=fin
        )
        assert estado is None, result


def test_check_finished_at_no_antes_de_started_at(base: str) -> None:
    antes = INICIO - timedelta(seconds=1)
    assert _sqlstate_al_insertar(base, finished_at=antes) == CHECK_VIOLATION
    assert _sqlstate_al_insertar(base, finished_at=INICIO, run_date=DIA) is None
    assert (
        _sqlstate_al_insertar(base, finished_at=None, result="running", run_date=DIA + timedelta(1))
        is None
    )


# Unicidad (23505) -------------------------------------------------------------------------------


def test_un_job_una_fila_por_dia(base: str) -> None:
    assert _sqlstate_al_insertar(base) is None
    assert _sqlstate_al_insertar(base) == UNIQUE_VIOLATION
    assert _sqlstate_al_insertar(base, run_date=DIA + timedelta(days=1)) is None
    assert _sqlstate_al_insertar(base, job_name="expirations_sim") is None


# Ciclo ------------------------------------------------------------------------------------------


def _tablas_de_worker(url: str) -> list[str]:
    filas = _consultar(
        url,
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'worker'",
    )
    return sorted(f["table_name"] for f in filas)


def _esquema_worker_existe(url: str) -> bool:
    return bool(_consultar(url, "SELECT 1 FROM pg_namespace WHERE nspname = 'worker'"))


def test_downgrade_deja_el_esquema_worker_vacio_y_upgrade_lo_restaura(
    alembic_config: Config, base: str
) -> None:
    assert "job_runs" in _tablas_de_worker(base)
    try:
        command.downgrade(alembic_config, PADRE)
        assert _esquema_worker_existe(base)
        assert "job_runs" not in _tablas_de_worker(base)
        indices = _consultar(
            base, "SELECT indexname FROM pg_indexes WHERE indexname LIKE '%job_runs%'"
        )
        assert indices == []
    finally:
        command.upgrade(alembic_config, "head")
    assert "job_runs" in _tablas_de_worker(base)
