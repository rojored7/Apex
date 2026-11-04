"""`infra/db/reown.sql` (S5-D146): pasar un servidor existente a `apex_owner` NOSUPERUSER.

`REASSIGN OWNED BY apex TO apex_owner` no sirve porque `apex` es el superusuario de arranque.
La prueba migra una base propia como `apex` (el propietario superusuario de hoy), crea `apex_owner`
con el script real de initdb, devuelve la base a `apex`, aplica `reown.sql` y comprueba dueños,
triggers, `alembic` y la vuelta atrás. Solo toca `db_test`.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit

import asyncpg
import pytest
from alembic import command

from tests.conftest import alembic_config_for
from tests.migrations.conftest import (
    CONTENEDOR,
    INFRA_DB,
    aplicar_archivo,
    psql_en_db_test,
)

BASE = "apex_reown"
OWNER = "apex_owner"
CLAVE = "reown-prueba-0123456789-abcd"  # solo vive en db_test
ESQUEMAS_APP = (
    "audit",
    "auth",
    "crypto",
    "members",
    "memberships",
    "payments",
    "plans",
    "settings",
    "worker",
)
SQL_TRIGGERS = (
    "SELECT tgrelid::regclass::text AS t, tgname, tgenabled FROM pg_trigger "
    "WHERE NOT tgisinternal ORDER BY 1, 2"
)
SQL_EXTENSION_AJENA = (
    "SELECT p.proname FROM pg_proc p JOIN pg_depend d ON d.objid = p.oid AND "
    "d.classid = 'pg_proc'::regclass AND d.deptype = 'e' JOIN pg_extension e ON "
    "e.oid = d.refobjid WHERE e.extname = 'btree_gist' AND p.proowner::regrole::text = $1 "
    "LIMIT 1"
)


def _correr(admin: str, *sentencias: str) -> None:
    async def hacer() -> None:
        conexion = await asyncpg.connect(admin)
        try:
            for sentencia in sentencias:
                await conexion.execute(sentencia)
        finally:
            await conexion.close()

    asyncio.run(hacer())


def _filas(dsn: str, sql: str, *args: Any) -> list[Any]:
    async def hacer() -> list[Any]:
        conexion = await asyncpg.connect(dsn)
        try:
            return list(await conexion.fetch(sql, *args))
        finally:
            await conexion.close()

    return asyncio.run(hacer())


@pytest.fixture(scope="module")
def base_migrada(test_database_url: str) -> Iterator[str]:
    """`apex_reown` migrada a head como `apex`, con `apex_owner` creado; DSN del superusuario."""
    if shutil.which("docker") is None:
        pytest.skip("docker no está en el PATH")
    partes = urlsplit(test_database_url)
    assert partes.hostname and partes.port and partes.username and partes.password
    cred = f"{partes.username}:{partes.password}@{partes.hostname}:{partes.port}"
    admin = f"postgresql://{cred}/postgres"
    _correr(admin, f"DROP DATABASE IF EXISTS {BASE} WITH (FORCE)")
    _correr(admin, f"CREATE DATABASE {BASE}")
    try:
        command.upgrade(alembic_config_for(f"postgresql+asyncpg://{cred}/{BASE}"), "head")
        orden = ["docker", "exec", "-i", "-e", f"APEX_OWNER_DB_PASSWORD={CLAVE}"]
        orden += ["-e", f"POSTGRES_DB={BASE}", CONTENEDOR, "bash", "-s"]
        crear = subprocess.run(  # noqa: S603
            orden,
            input=(INFRA_DB / "initdb" / "10-apex-owner.sh")
            .read_bytes()
            .replace(bytes([13, 10]), bytes([10])),
            capture_output=True,
            timeout=120,
            check=False,
        )
        assert crear.returncode == 0, crear.stderr[:300].decode("utf-8", "replace")
        # Como en un servidor existente: la base sigue siendo del superusuario.
        _correr(admin, f"ALTER DATABASE {BASE} OWNER TO {partes.username}")
        yield f"postgresql://{cred}/{BASE}"
    finally:
        _correr(admin, f"DROP DATABASE IF EXISTS {BASE} WITH (FORCE)")
        _correr(admin, f"DROP ROLE IF EXISTS {OWNER}")


def _duenios(dsn: str) -> dict[str, Any]:
    esquemas = _filas(
        dsn,
        "SELECT nspname, nspowner::regrole::text AS d FROM pg_namespace "
        "WHERE nspname = ANY($1::text[])",
        list(ESQUEMAS_APP),
    )
    ajenos = _filas(
        dsn,
        "SELECT n.nspname || '.' || c.relname AS o FROM pg_class c JOIN pg_namespace n "
        "ON n.oid = c.relnamespace WHERE (n.nspname = ANY($1::text[]) OR "
        "(n.nspname = 'public' AND c.relname = 'alembic_version')) AND c.relkind IN "
        "('r','p','v','m','S') AND c.relowner::regrole::text <> $2 AND NOT EXISTS "
        "(SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.classid = "
        "'pg_class'::regclass AND (d.deptype = 'e' OR (c.relkind = 'S' AND d.deptype IN "
        "('a','i')))) ORDER BY 1",
        list(ESQUEMAS_APP),
        OWNER,
    )
    funciones = _filas(
        dsn,
        "SELECT p.oid::regprocedure::text AS f FROM pg_proc p JOIN pg_namespace n ON "
        "n.oid = p.pronamespace WHERE n.nspname = ANY($1::text[]) AND "
        "p.proowner::regrole::text <> $2",
        list(ESQUEMAS_APP),
        OWNER,
    )
    base = _filas(
        dsn,
        "SELECT datdba::regrole::text AS d FROM pg_database WHERE datname = current_database()",
    )
    return {
        "esquemas": {f["nspname"]: f["d"] for f in esquemas},
        "no_dueno": [f["o"] for f in ajenos],
        "funciones_ajenas": [f["f"] for f in funciones],
        "base": base[0]["d"],
    }


def test_reown_pasa_todo_a_apex_owner_sin_tocar_triggers_ni_extension(base_migrada: str) -> None:
    triggers_antes = [tuple(f) for f in _filas(base_migrada, SQL_TRIGGERS)]
    assert triggers_antes, "la base migrada debe tener triggers (WORM)"
    assert _duenios(base_migrada)["base"] != OWNER

    sql = (INFRA_DB / "reown.sql").read_text(encoding="utf-8")
    primera = psql_en_db_test(BASE, sql)
    assert primera.returncode == 0, primera.stderr
    segunda = psql_en_db_test(BASE, sql)
    assert segunda.returncode == 0, f"no es idempotente: {segunda.stderr}"
    assert "0 objetos" in segunda.stderr, segunda.stderr

    d = _duenios(base_migrada)
    assert d["esquemas"] == {e: OWNER for e in ESQUEMAS_APP}
    assert d["no_dueno"] == [], d["no_dueno"]
    assert d["funciones_ajenas"] == [], d["funciones_ajenas"]
    assert d["base"] == OWNER
    triggers_despues = [tuple(f) for f in _filas(base_migrada, SQL_TRIGGERS)]
    assert triggers_despues == triggers_antes
    assert {t[2] for t in triggers_despues} == {b"A"}  # tgenabled intacto (siempre activos)
    assert _filas(base_migrada, SQL_EXTENSION_AJENA, OWNER) == [], "btree_gist no se toca"


def test_alembic_sigue_en_head_tambien_como_apex_owner(
    base_migrada: str, test_database_url: str
) -> None:
    partes = urlsplit(test_database_url)
    url = f"postgresql+asyncpg://{OWNER}:{CLAVE}@{partes.hostname}:{partes.port}/{BASE}"
    # `upgrade head` como apex_owner sobre la base ya reasignada: no falla y no cambia nada.
    command.upgrade(alembic_config_for(url), "head")
    version = _filas(base_migrada, "SELECT version_num FROM public.alembic_version")
    assert len(version) == 1 and version[0]["version_num"]


def test_vuelta_atras_y_grants_se_vuelven_a_aplicar(base_migrada: str) -> None:
    atras = psql_en_db_test(BASE, f"REASSIGN OWNED BY {OWNER} TO apex;")
    assert atras.returncode == 0, atras.stderr
    d = _duenios(base_migrada)
    assert set(d["esquemas"].values()) == {"apex"}
    assert d["base"] == "apex"
    # De nuevo hacia adelante y con roles.sql + grants.sql reales encima (lo que hace dbsetup).
    adelante = psql_en_db_test(BASE, (INFRA_DB / "reown.sql").read_text(encoding="utf-8"))
    assert adelante.returncode == 0, adelante.stderr
    for archivo in ("roles.sql", "grants.sql"):
        resultado = aplicar_archivo(BASE, archivo)
        assert resultado.returncode == 0, f"{archivo}: {resultado.stderr}"
    assert _duenios(base_migrada)["esquemas"] == {e: OWNER for e in ESQUEMAS_APP}


def test_reown_exige_apex_owner_y_superusuario() -> None:
    texto = (INFRA_DB / "reown.sql").read_text(encoding="utf-8")
    assert "apex_owner no existe" in texto
    assert "debe correr como superusuario" in texto
