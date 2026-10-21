"""Entorno de Alembic, async y multiesquema (US-012, T7).

- La URL sale de `sqlalchemy.url` si se fijó (pruebas, `-x`), y si no, de
  `Settings.DATABASE_URL`.
- `include_schemas=True` e `include_name` limitado a `APP_SCHEMAS`.
- Los `models` de cada módulo se importan aquí (no en `core/`) para que
  `target_metadata` los conozca; cada historia agrega su línea.
- Si `config.attributes["connection"]` trae una conexión sync (desde
  `create_app()` con `run_sync`, US-020), se usa directo; si no, se abre un engine
  async propio.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import APP_SCHEMAS, Base

# Models de cada módulo (se agregan en su historia):
# from app.modules.members import models as _members

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    # Prioridad: `-x url=...` (CLI en el host), `sqlalchemy.url` (pruebas), Settings.
    x_url = context.get_x_argument(as_dictionary=True).get("url")
    if x_url:
        return x_url
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    from app.core.config import get_settings

    return get_settings().DATABASE_URL.get_secret_value()


def include_name(name: str | None, type_: str, parent_names: dict[str, Any]) -> bool:
    if type_ == "schema":
        return name in APP_SCHEMAS
    return True


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_name=include_name,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conexion = config.attributes.get("connection")
    if conexion is not None:
        do_run_migrations(conexion)
        return
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
