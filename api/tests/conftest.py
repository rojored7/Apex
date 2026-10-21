"""Infraestructura de pruebas del api (US-012, T8).

- `test_database_url`: `TEST_DATABASE_URL` (servicio `db_test`). Falla, no se salta,
  si no está definida (CRITICA-2 N-1).
- `migrated_database`: corre `alembic upgrade head` una vez por corrida.
- `engine`: engine async por prueba.
- `session`: una conexión en transacción externa y un savepoint por prueba; todo se
  revierte al terminar, así dos pruebas nunca ven las filas de la otra.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.cli import init_keys_files, key_paths_in
from app.core.audit import install_audit_listeners
from app.core.config import Settings, load_settings
from app.core.crypto.oplog import install_oplog_listeners
from app.core.crypto.types import install_crypto_type_listeners

API_ROOT = Path(__file__).resolve().parents[1]

# US-016: los listeners de auditoría viven en la clase Session; en el api los instala
# create_app y aquí se instalan una vez para toda la suite.
install_audit_listeners()
install_oplog_listeners()  # US-029: igual que create_app
install_crypto_type_listeners()  # US-028: igual que create_app


def alembic_config_for(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.fail(
            "TEST_DATABASE_URL no está definida: las pruebas exigen el PostgreSQL 16 de prueba "
            "(db_test de infra/compose.dev.yml); no se saltan."
        )
    assert url.startswith("postgresql+asyncpg://"), url
    return url


@pytest.fixture(scope="session")
def claves_prueba(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Directorio con KEK, llave de firma y par JWT creados por `init-keys` (US-023)."""
    directorio = tmp_path_factory.mktemp("keys")
    init_keys_files(key_paths_in(directorio))
    return directorio


@pytest.fixture
def settings_prueba(tmp_path: Path, test_database_url: str, claves_prueba: Path) -> Settings:
    """`Settings` completa apuntando a `db_test` y a llaves reales, sin tocar el `.env` real."""
    rutas = key_paths_in(claves_prueba)
    env = tmp_path / ".env"
    env.write_text(
        f"DATABASE_URL={test_database_url}\n"
        f"JWT_PRIVATE_KEY_PATH={rutas.jwt_private}\n"
        "CRYPTO_PROVIDER=local\n"
        f"CRYPTO_LOCAL_KEK_PATH={rutas.kek}\n"
        f"CRYPTO_LOCAL_SIGNING_KEY_PATH={rutas.signing_key}\n"
        "UPLOADS_DIR=/data/uploads\n"
        'CORS_ORIGINS=["http://localhost"]\n'
        "LOG_LEVEL=INFO\n"
        "ENV=dev\n",
        encoding="utf-8",
    )
    return load_settings(env_file=env)


@pytest.fixture(scope="session")
def alembic_config(test_database_url: str) -> Config:
    return alembic_config_for(test_database_url)


@pytest.fixture(scope="session")
def migrated_database(alembic_config: Config, test_database_url: str) -> str:
    command.upgrade(alembic_config, "head")
    return test_database_url


@pytest.fixture
async def engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    motor = create_async_engine(migrated_database, hide_parameters=True, echo=False)
    try:
        yield motor
    finally:
        await motor.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conexion:
        transaccion = await conexion.begin()
        fabrica = async_sessionmaker(
            bind=conexion, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with fabrica() as sesion:
            yield sesion
        await transaccion.rollback()
