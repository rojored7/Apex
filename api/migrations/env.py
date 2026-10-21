"""Entorno de Alembic.

Versión mínima (S0-W0-4, CRITICA-2 N-2) para que la imagen pueda ejecutar
`alembic heads` desde ya. US-012 la completa: engine async desde `Settings`,
`target_metadata = Base.metadata` y los esquemas por módulo.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
