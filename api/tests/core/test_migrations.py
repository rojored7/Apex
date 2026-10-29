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


def test_alembic_con_solo_database_url_en_el_entorno(
    migrated_database: str, alembic_config: Config
) -> None:
    """Servicio `migrate` (S4B-D8, S4B-D56): el contenedor solo trae `DATABASE_URL` del propietario.
    `migrations/env.py` la toma del entorno sin pasar por `Settings` (exige llaves y KEK)."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    api_root = Path(__file__).resolve().parents[2]
    entorno = {
        clave: os.environ[clave]
        for clave in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE")
        if clave in os.environ
    }
    entorno["DATABASE_URL"] = migrated_database
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=api_root,
        env=entorno,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    salida = resultado.stdout + resultado.stderr
    assert resultado.returncode == 0, salida
    assert _head(alembic_config) in salida
    assert "ConfigError" not in salida
