"""`0003_crypto` sube, baja (sin borrar el esquema) y vuelve a subir (US-024 T7)."""

from __future__ import annotations

import asyncio

import asyncpg
from alembic import command
from alembic.config import Config

TABLAS = ("crypto_keys", "crypto_ops", "crypto_jobs")
FUNCIONES = ("forbid_ops_mutation", "guard_keys_update", "guard_jobs_mutation")


def _estado(url: str) -> tuple[list[str], list[str], bool]:
    async def consultar() -> tuple[list[str], list[str], bool]:
        conexion = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://", 1))
        try:
            tablas = [
                r["table_name"]
                for r in await conexion.fetch(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'crypto' ORDER BY table_name"
                )
            ]
            funciones = [
                r["proname"]
                for r in await conexion.fetch(
                    "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = 'crypto' ORDER BY p.proname"
                )
            ]
            esquema = await conexion.fetchval(
                "SELECT count(*) FROM pg_namespace WHERE nspname = 'crypto'"
            )
            return tablas, funciones, bool(esquema)
        finally:
            await conexion.close()

    return asyncio.run(consultar())


def test_ciclo_de_0003(alembic_config: Config, migrated_database: str) -> None:
    tablas, funciones, esquema = _estado(migrated_database)
    assert sorted(TABLAS) == tablas and sorted(FUNCIONES) == funciones and esquema

    command.downgrade(alembic_config, "0002_audit_log")
    tablas, funciones, esquema = _estado(migrated_database)
    assert tablas == [] and funciones == [] and esquema is True

    command.upgrade(alembic_config, "head")
    tablas, funciones, _ = _estado(migrated_database)
    assert sorted(TABLAS) == tablas and sorted(FUNCIONES) == funciones
