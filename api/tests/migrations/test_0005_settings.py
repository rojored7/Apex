"""`0005_settings`: tabla, CHECKs, índice único, sin FK ni filas, y ciclo (US-054 T1; B1.4).

Los nombres de las restricciones siguen `NAMING_CONVENTION` de `core/db.py`, igual que el
modelo `SettingsSection`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
from alembic import command
from alembic.config import Config

COLUMNAS = {
    "id": ("uuid", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
    "created_by": ("uuid", "NO"),
    "key": ("text", "NO"),
    "value": ("jsonb", "NO"),
    "version": ("integer", "NO"),
    "updated_by": ("uuid", "YES"),
}
CLAVES = ("gym", "hours", "payment_methods", "channels", "classes", "memberships", "tv", "privacy")


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _estado(url: str) -> dict[str, Any]:
    async def consultar() -> dict[str, Any]:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            existe = await conexion.fetchval(
                "SELECT to_regclass('settings.settings_sections') IS NOT NULL"
            )
            if not existe:
                return {"existe": False}
            columnas = {
                r["column_name"]: (r["data_type"], r["is_nullable"])
                for r in await conexion.fetch(
                    "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'settings' AND table_name = 'settings_sections'"
                )
            }
            default_version = await conexion.fetchval(
                "SELECT column_default FROM information_schema.columns WHERE table_schema = "
                "'settings' AND table_name = 'settings_sections' AND column_name = 'version'"
            )
            restricciones = {
                r["conname"]: r["contype"]
                for r in await conexion.fetch(
                    "SELECT conname, contype::text AS contype FROM pg_constraint "
                    "WHERE conrelid = 'settings.settings_sections'::regclass"
                )
            }
            indices = {
                r["indexname"]: r["indexdef"]
                for r in await conexion.fetch(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = 'settings' AND tablename = 'settings_sections'"
                )
            }
            filas = await conexion.fetchval("SELECT count(*) FROM settings.settings_sections")
            return {
                "existe": True,
                "columnas": columnas,
                "default_version": default_version,
                "restricciones": restricciones,
                "indices": indices,
                "filas": filas,
            }
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


INSERT = (
    "INSERT INTO settings.settings_sections (id, key, value, version, created_by) "
    "VALUES (gen_random_uuid(), '{key}', '{{}}'::jsonb, {version}, gen_random_uuid())"
)


def test_tabla_columnas_restricciones_e_indice(migrated_database: str) -> None:
    estado = _estado(migrated_database)
    assert estado["existe"] is True
    assert estado["columnas"] == COLUMNAS
    assert estado["default_version"] == "0"
    assert estado["restricciones"] == {
        "pk_settings_sections": "p",
        "ck_settings_sections_key_valid": "c",
        "ck_settings_sections_version_non_negative": "c",
    }  # sin FK hacia auth.users (S7)
    assert (
        "CREATE UNIQUE INDEX uq_settings_sections_key"
        in estado["indices"]["uq_settings_sections_key"]
    )
    assert estado["filas"] == 0  # sin filas sembradas: los defaults viven en el esquema


def test_los_checks_rechazan_clave_invalida_y_version_negativa(migrated_database: str) -> None:
    for clave in CLAVES:
        assert _rechaza(migrated_database, INSERT.format(key=clave, version=0)) == ""
    assert "key_valid" in _rechaza(migrated_database, INSERT.format(key="otra", version=0))
    assert "version_non_negative" in _rechaza(
        migrated_database, INSERT.format(key="gym", version=-1)
    )


def test_la_clave_es_unica(migrated_database: str) -> None:
    dos = f"{INSERT.format(key='gym', version=0)}; {INSERT.format(key='gym', version=0)}"
    assert "uq_settings_sections_key" in _rechaza(migrated_database, dos)


def test_ciclo_de_0005(alembic_config: Config, migrated_database: str) -> None:
    assert _estado(migrated_database)["existe"] is True
    command.downgrade(alembic_config, "0004_auth")
    assert _estado(migrated_database)["existe"] is False
    command.upgrade(alembic_config, "head")
    assert _estado(migrated_database)["columnas"] == COLUMNAS
