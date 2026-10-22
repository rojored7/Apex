"""`0005b_auth_security` (S2-B2; S2-D9, H-3, L-4, M-8 y L-10).

Padre `0005_settings`. Cuatro columnas nuevas y un CHECK:
- `auth.users.must_change_password boolean NOT NULL DEFAULT false` (M-8);
- `auth.users.failed_login_count integer NOT NULL DEFAULT 0` con
  `ck_users_failed_login_count_non_negative` (L-10);
- `auth.users.tokens_valid_after timestamptz NULL` (H-3);
- `auth.refresh_tokens.family_started_at timestamptz NOT NULL DEFAULT now()` (L-4).
El `downgrade` quita el CHECK y las cuatro columnas; `0004_auth` no se toca.
"""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REVISION = "0005b_auth_security"
PADRE = "0005_settings"
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"

COLUMNAS_NUEVAS = {
    ("users", "must_change_password"): ("boolean", "NO", "false"),
    ("users", "failed_login_count"): ("integer", "NO", "0"),
    ("users", "tokens_valid_after"): ("timestamp with time zone", "YES", None),
    ("refresh_tokens", "family_started_at"): ("timestamp with time zone", "NO", "now()"),
}
CHECK = "ck_users_failed_login_count_non_negative"


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
            columnas = {
                (r["table_name"], r["column_name"]): (
                    r["data_type"],
                    r["is_nullable"],
                    r["column_default"],
                )
                for r in await conexion.fetch(
                    "SELECT table_name, column_name, data_type, is_nullable, column_default "
                    "FROM information_schema.columns WHERE table_schema = 'auth' "
                    "AND table_name IN ('users', 'refresh_tokens')"
                )
            }
            checks = {
                r["conname"]: r["contype"]
                for r in await conexion.fetch(
                    "SELECT conname, contype::text AS contype FROM pg_constraint "
                    "WHERE conrelid = 'auth.users'::regclass"
                )
            }
            return {"columnas": columnas, "checks": checks}
        finally:
            await conexion.close()

    return asyncio.run(consultar())


def _rechaza(url: str, sql: str) -> str:
    """Corre `sql` en una transacción que siempre se revierte; devuelve el error (o "")."""

    async def correr() -> str:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            transaccion = conexion.transaction()
            await transaccion.start()
            try:
                await conexion.execute(sql)
            except asyncpg.PostgresError as error:
                return str(error)
            finally:
                await transaccion.rollback()
            return ""
        finally:
            await conexion.close()

    return asyncio.run(correr())


def test_la_revision_existe_cuelga_de_0005_settings_y_es_head(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    assert scripts.get_heads() == [REVISION]


def test_columnas_nuevas_con_tipo_nulabilidad_y_default(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    columnas = _estado(migrated_database)["columnas"]
    for clave, (tipo, nula, default) in COLUMNAS_NUEVAS.items():
        assert clave in columnas, clave
        assert columnas[clave][0] == tipo and columnas[clave][1] == nula, clave
        assert columnas[clave][2] == default, (clave, columnas[clave][2])


def test_el_check_rechaza_un_contador_negativo(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    assert _estado(migrated_database)["checks"].get(CHECK) == "c"
    error = _rechaza(
        migrated_database,
        "UPDATE auth.users SET failed_login_count = -1 "
        "WHERE id = '00000000-0000-0000-0000-000000000001'",
    )
    assert CHECK in error
    assert (
        _rechaza(
            migrated_database,
            "UPDATE auth.users SET failed_login_count = 0 "
            "WHERE id = '00000000-0000-0000-0000-000000000001'",
        )
        == ""
    )


def test_las_filas_existentes_toman_los_defaults(
    alembic_config: Config, migrated_database: str
) -> None:
    """El usuario técnico (de `0004_auth`) queda sin cambio forzado y con el contador en 0."""
    _revision_existe(alembic_config)

    async def leer() -> Any:
        conexion = await asyncpg.connect(_dsn(migrated_database))
        try:
            return await conexion.fetchrow(
                "SELECT must_change_password, failed_login_count, tokens_valid_after "
                "FROM auth.users WHERE id = $1::uuid",
                SYSTEM_USER_ID,
            )
        finally:
            await conexion.close()

    fila = asyncio.run(leer())
    assert fila["must_change_password"] is False
    assert fila["failed_login_count"] == 0
    assert fila["tokens_valid_after"] is None


def test_ciclo_de_0005b(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    command.downgrade(alembic_config, PADRE)
    estado = _estado(migrated_database)
    assert not set(COLUMNAS_NUEVAS) & set(estado["columnas"])
    assert CHECK not in estado["checks"]
    assert ("users", "last_login_at") in estado["columnas"]  # 0004 intacta
    command.upgrade(alembic_config, "head")
    estado = _estado(migrated_database)
    assert set(COLUMNAS_NUEVAS) <= set(estado["columnas"])
    assert estado["checks"].get(CHECK) == "c"
