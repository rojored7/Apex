"""La migración 0001 crea los nueve esquemas y btree_gist, y baja limpia (US-012, T10)."""

from __future__ import annotations

import asyncio

import asyncpg
from alembic import command
from alembic.config import Config

from app.core.db import APP_SCHEMAS

ESQUEMAS_SQL = (
    "SELECT nspname FROM pg_namespace WHERE nspname = ANY($1::text[]) ORDER BY nspname"
)


def _asyncpg_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _estado(url: str) -> tuple[list[str], bool, str | None]:
    async def consultar() -> tuple[list[str], bool, str | None]:
        conexion = await asyncpg.connect(_asyncpg_url(url))
        try:
            esquemas = [r["nspname"] for r in await conexion.fetch(ESQUEMAS_SQL, list(APP_SCHEMAS))]
            gist = await conexion.fetchval(
                "SELECT count(*) FROM pg_extension WHERE extname = 'btree_gist'"
            )
            existe_version = await conexion.fetchval(
                "SELECT to_regclass('public.alembic_version') IS NOT NULL"
            )
            version = (
                await conexion.fetchval("SELECT version_num FROM alembic_version")
                if existe_version
                else None
            )
            return esquemas, bool(gist), version
        finally:
            await conexion.close()

    return asyncio.run(consultar())


def test_upgrade_head_crea_esquemas_extension_y_version(
    alembic_config: Config, migrated_database: str
) -> None:
    esquemas, gist, version = _estado(migrated_database)
    assert esquemas == sorted(APP_SCHEMAS)
    assert gist is True
    assert version == "0001_core_schemas"


def test_downgrade_de_0001_sobre_base_vacia_y_vuelta_a_head(
    alembic_config: Config, migrated_database: str
) -> None:
    command.downgrade(alembic_config, "-1")
    esquemas, gist, version = _estado(migrated_database)
    assert esquemas == []
    assert gist is False
    assert version is None

    command.upgrade(alembic_config, "head")
    esquemas, gist, version = _estado(migrated_database)
    assert esquemas == sorted(APP_SCHEMAS)
    assert gist is True
    assert version == "0001_core_schemas"
