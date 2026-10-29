"""Fixture `apex_roles` (S4B-W0-3, S4B-D101): una base propia con los roles de aplicación reales.

Los roles son del clúster, no de la base: la fixture arranca con un estado limpio (borra la base
`apex_roles` si quedó de una corrida cortada y corre `infra/db/revoke.sql`, idempotente), crea la
base con `asyncpg` en autocommit, la migra a `head` y ejecuta `roles.sql` y `grants.sql` REALES
con `docker exec -i apex-db_test-1 psql -v ON_ERROR_STOP=1 -U apex -d apex_roles -f -` (así
`\\getenv` y `\\gexec` se prueban con el mismo `psql` 16 que usará `dbsetup`). El teardown hace
`DROP OWNED BY` de los tres roles en `apex_roles`, borra la base y corre `revoke.sql`.

Solo toca `db_test` (contenedor `apex-db_test-1`, o el de `APEX_DB_TEST_CONTAINER`): ningún
comando de esta fixture apunta a `apex-db-1`; lo vigila `test_db_roles_confined.py` (architecture).
Mientras `infra/db/{roles,grants,revoke}.sql` no existan la fixture falla con ese motivo (Rojo).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg
import pytest
from alembic import command

from tests.conftest import alembic_config_for

RAIZ = Path(__file__).resolve().parents[3]
INFRA_DB = RAIZ / "infra" / "db"
CONTENEDOR = os.environ.get("APEX_DB_TEST_CONTAINER", "apex-db_test-1")
BASE_ROLES = "apex_roles"
ROLES: tuple[str, ...] = ("apex_api", "apex_worker", "apex_backup")
# Contraseñas de prueba fijas (>= 24 caracteres, distintas entre sí, sin `cambiar-esto`): no son
# secretos, solo existen en `db_test`.
CLAVES: dict[str, str] = {
    "apex_api": "api-prueba-0123456789-abcdef",
    "apex_worker": "worker-prueba-0123456789-abc",
    "apex_backup": "backup-prueba-0123456789-ab",
}
VARIABLES_CLAVE: dict[str, str] = {
    "apex_api": "APEX_API_DB_PASSWORD",
    "apex_worker": "APEX_WORKER_DB_PASSWORD",
    "apex_backup": "APEX_BACKUP_DB_PASSWORD",
}
ARCHIVOS_NECESARIOS = ("roles.sql", "grants.sql", "revoke.sql")


@dataclass(frozen=True)
class RolesDb:
    """La base `apex_roles` ya migrada y con roles y grants aplicados."""

    nombre: str
    host: str
    port: int
    propietario: str
    clave_propietario: str

    def dsn(self, rol: str | None = None) -> str:
        """DSN de `asyncpg` hacia `apex_roles`, como `rol` o como propietario."""
        if rol is None:
            return (
                f"postgresql://{self.propietario}:{self.clave_propietario}"
                f"@{self.host}:{self.port}/{self.nombre}"
            )
        return f"postgresql://{rol}:{CLAVES[rol]}@{self.host}:{self.port}/{self.nombre}"


def entorno_de_claves(claves: dict[str, str] | None = None) -> dict[str, str]:
    efectivas = claves or CLAVES
    return {VARIABLES_CLAVE[rol]: efectivas[rol] for rol in ROLES}


def psql_en_db_test(
    base: str,
    sql: str,
    *,
    entorno: dict[str, str] | None = None,
    usuario: str = "apex",
) -> subprocess.CompletedProcess[str]:
    """`psql -v ON_ERROR_STOP=1 -f -` dentro de `db_test`, con `sql` por stdin."""
    orden = ["docker", "exec", "-i"]
    for nombre, valor in (entorno or {}).items():
        orden += ["-e", f"{nombre}={valor}"]
    orden += [
        CONTENEDOR,
        "psql",
        "-X",
        "-q",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        usuario,
        "-d",
        base,
        "-f",
        "-",
    ]
    return subprocess.run(  # noqa: S603
        orden, input=sql, capture_output=True, text=True, timeout=120, check=False
    )


def aplicar_archivo(base: str, nombre: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Ejecuta `infra/db/<nombre>` con `psql` real; las contraseñas entran por `-e`."""
    ruta = INFRA_DB / nombre
    entorno = kwargs.get("entorno")
    resultado = psql_en_db_test(
        base,
        ruta.read_text(encoding="utf-8"),
        entorno=entorno if isinstance(entorno, dict) else entorno_de_claves(),
    )
    return resultado


def _exigir_archivos() -> None:
    faltan = [n for n in ARCHIVOS_NECESARIOS if not (INFRA_DB / n).is_file()]
    if faltan:
        pytest.fail(
            f"no existe infra/db/{', infra/db/'.join(faltan)} (S4B-W0-3.4, Verde de infra/db)"
        )


def _sql_en_postgres(url_admin: str, *sentencias: str) -> None:
    """Sentencias sin transacción (CREATE/DROP DATABASE) por `asyncpg` en autocommit."""

    async def correr() -> None:
        conexion = await asyncpg.connect(url_admin)
        try:
            for sentencia in sentencias:
                await conexion.execute(sentencia)
        finally:
            await conexion.close()

    asyncio.run(correr())


def _revoke_en_postgres() -> None:
    """`revoke.sql` desde la base `postgres`: deja el clúster sin los tres roles (idempotente)."""
    resultado = psql_en_db_test("postgres", (INFRA_DB / "revoke.sql").read_text(encoding="utf-8"))
    assert resultado.returncode == 0, resultado.stderr


@pytest.fixture(scope="session")
def apex_roles(test_database_url: str) -> Iterator[RolesDb]:
    if shutil.which("docker") is None:
        pytest.skip("docker no está en el PATH: `apex_roles` necesita `docker exec` sobre db_test")
    _exigir_archivos()
    partes = urlsplit(test_database_url)
    assert partes.hostname and partes.port and partes.username and partes.password
    propietario, clave = partes.username, partes.password
    admin = f"postgresql://{propietario}:{clave}@{partes.hostname}:{partes.port}/postgres"
    url_alembic = (
        f"postgresql+asyncpg://{propietario}:{clave}@{partes.hostname}:{partes.port}/{BASE_ROLES}"
    )

    # Estado limpio: sin base `apex_roles` previa y sin los roles (revoke.sql idempotente).
    _sql_en_postgres(admin, f"DROP DATABASE IF EXISTS {BASE_ROLES} WITH (FORCE)")
    _revoke_en_postgres()
    _sql_en_postgres(admin, f"CREATE DATABASE {BASE_ROLES}")
    try:
        command.upgrade(alembic_config_for(url_alembic), "head")
        for archivo in ("roles.sql", "grants.sql"):
            resultado = aplicar_archivo(BASE_ROLES, archivo)
            assert resultado.returncode == 0, f"{archivo}: {resultado.stderr}"
        yield RolesDb(
            nombre=BASE_ROLES,
            host=partes.hostname,
            port=partes.port,
            propietario=propietario,
            clave_propietario=clave,
        )
    finally:
        # DROP OWNED BY en apex_roles (solo si los roles existen), base fuera y revoke.sql.
        psql_en_db_test(
            BASE_ROLES,
            "DO $$ DECLARE r text; BEGIN FOREACH r IN ARRAY ARRAY['apex_api','apex_worker',"
            "'apex_backup'] LOOP IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN "
            "EXECUTE format('DROP OWNED BY %I', r); END IF; END LOOP; END $$",
        )
        _sql_en_postgres(admin, f"DROP DATABASE IF EXISTS {BASE_ROLES} WITH (FORCE)")
        _revoke_en_postgres()


def url_por_rol(apex: RolesDb, rol: str) -> str:
    """URL SQLAlchemy asincrónica hacia `apex_roles` con el rol de aplicación `rol` (S4B-D101)."""
    return apex.dsn(rol).replace("postgresql://", "postgresql+asyncpg://", 1)
