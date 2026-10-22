"""La migración 0001 crea los nueve esquemas y btree_gist, y toda la cadena baja limpia hasta
la base vacía y vuelve a head (US-012, T10; cada sprint agrega migraciones)."""

from __future__ import annotations

import asyncio

import asyncpg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.db import APP_SCHEMAS

ESQUEMAS_SQL = "SELECT nspname FROM pg_namespace WHERE nspname = ANY($1::text[]) ORDER BY nspname"


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


def _head(alembic_config: Config) -> str:
    head = ScriptDirectory.from_config(alembic_config).get_current_head()
    assert head is not None
    return head


def test_upgrade_head_crea_esquemas_extension_y_version(
    alembic_config: Config, migrated_database: str
) -> None:
    esquemas, gist, version = _estado(migrated_database)
    assert esquemas == sorted(APP_SCHEMAS)
    assert gist is True
    assert version == _head(alembic_config)


def test_downgrade_a_base_vacia_y_vuelta_a_head(
    alembic_config: Config, migrated_database: str
) -> None:
    command.downgrade(alembic_config, "base")
    esquemas, gist, version = _estado(migrated_database)
    assert esquemas == []
    assert gist is False
    assert version is None

    command.upgrade(alembic_config, "head")
    esquemas, gist, version = _estado(migrated_database)
    assert esquemas == sorted(APP_SCHEMAS)
    assert gist is True
    assert version == _head(alembic_config)


def test_single_head(alembic_config: Config) -> None:
    """Una sola cabeza en la cadena (condición 5 del impacto del Sprint 2; S2-B1)."""
    heads = ScriptDirectory.from_config(alembic_config).get_heads()
    assert len(heads) == 1, heads
