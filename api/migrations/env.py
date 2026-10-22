"""Entorno de Alembic, async y multiesquema (US-012, T7; US-020, T5).

- La URL sale de `-x url=...` (CLI en el host), de `sqlalchemy.url` si se fijó
  (pruebas, `create_app`) y, si no, de `Settings.DATABASE_URL`.
- `include_schemas=True` e `include_name` limitado a `APP_SCHEMAS`.
- Los `models` de cada módulo se importan aquí (no en `core/`) para que
  `target_metadata` los conozca; cada historia agrega su línea.
- Lock asesor `MIGRATION_LOCK_KEY` (`pg_advisory_lock`) tomado antes de migrar y
  liberado en `finally`: el api, el worker y el CLI nunca migran a la vez. Como el
  lock abre la transacción de la conexión, las migraciones corren en modo de
  transacción externa y se confirman con `commit()` explícito.
- Si `config.attributes["connection"]` trae una conexión sync, se usa directo; si
  no, se abre un engine async propio.
"""

from __future__ import annotations

import asyncio
import logging
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import Connection, pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import APP_SCHEMAS, MIGRATION_LOCK_KEY, Base

# Models de cada módulo (se agregan en su historia):
from app.modules.auth import models as _auth  # noqa: F401  (US-041 0004_auth, S2-B2 0005b)
from app.modules.members import models as _members  # noqa: F401  (US-069, 0006_members)
from app.modules.settings import models as _settings  # noqa: F401  (US-054, 0005_settings)

config = context.config
# Solo si nadie configuró el logging (CLI en el host): en el api ya está el JSON de US-018
# y fileConfig reemplazaría el handler raíz.
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
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
    connection.execute(text("SELECT pg_advisory_lock(:clave)"), {"clave": MIGRATION_LOCK_KEY})
    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.execute(text("SELECT pg_advisory_unlock(:clave)"), {"clave": MIGRATION_LOCK_KEY})
        connection.commit()


async def run_async_migrations() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
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
