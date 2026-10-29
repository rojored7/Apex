"""Fixtures del CLI (plan del Sprint 4A, sección 2, bloques B2 y B3).

- `settings_produccion`: copia de `settings_prueba` con `ENV="production"` (S4A-D53). Los pisos
  de S3-D79 ya se cumplen (los tres `DB_*_TIMEOUT_MS` de `settings_prueba` son los de por
  defecto, de 1.000 ms o más); `model_copy` no revalida, como hace el propio CLI con
  `--db-timeouts off`.
- `import_dir` y `settings_importacion` (S4B-B1): una carpeta de `tmp_path` como `IMPORT_DIR` y la
  `Settings` de prueba que la apunta (`model_copy`); `settings_importacion_produccion` es la misma
  con `ENV="production"`.
- `limpiar_demo` (S4B-B1): fábrica de sesiones con commit real para `seed --demo` e
  `import-members`; antes y después deja vacíos socios, planes, membresías, pagos, auditoría,
  `crypto_ops` y llaves (el CLI crea las suyas con `crypto_runtime`) y sin proveedor ni keyring.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.main as _app_main
from app.core.audit import AuditEntry
from app.core.config import DB_TIMEOUT_FLOOR_MS, Settings
from app.core.crypto.keyring import configure_keyring
from app.core.crypto.provider import configure_provider
from tests.audit.conftest import (  # noqa: F401  (S4A-B3: `verify-audit` usa las de la auditoría)
    candado_tomado,
    espia_de_conexiones,
    fabrica_confirmada,
)
from tests.conftest import limpiar_tras_dos_sesiones
from tests.crypto.conftest import limpiar_llaves_con_commit
from tests.factories.triggers import disable_user_sql, rearm_always_sql

_app_main.load_module_services()  # los suscriptores del bus existen antes de `restaurar_bus`


def _loggers_de_la_app() -> list[logging.Logger]:
    """El raíz y los loggers `app` y `app.*` ya creados."""
    registrados = logging.Logger.manager.loggerDict.items()
    propios = [
        logger
        for nombre, logger in registrados
        if isinstance(logger, logging.Logger) and (nombre == "app" or nombre.startswith("app."))
    ]
    return [logging.getLogger(), *propios]


@pytest.fixture(autouse=True)
def sin_handlers_sobre_flujos_cerrados() -> Iterator[None]:
    """S4A-D90 (revisión de seguridad de B2, L-2): un comando que configura el log JSON bajo
    `CliRunner` deja un `StreamHandler` sobre el stdout de la invocación, que se cierra al
    terminar; el siguiente registro falla con `--- Logging error ---`. Al salir de cada prueba se
    quitan los `StreamHandler` cuyo flujo ya está cerrado."""
    yield
    for logger in _loggers_de_la_app():
        for handler in list(logger.handlers):
            flujo = getattr(handler, "stream", None)
            if isinstance(handler, logging.StreamHandler) and getattr(flujo, "closed", False):
                logger.removeHandler(handler)


@pytest.fixture
def settings_produccion(settings_prueba: Settings) -> Settings:
    produccion = settings_prueba.model_copy(update={"ENV": "production"})
    for nombre in ("DB_LOCK_TIMEOUT_MS", "DB_STATEMENT_TIMEOUT_MS", "DB_IDLE_IN_TX_TIMEOUT_MS"):
        assert getattr(produccion, nombre) >= DB_TIMEOUT_FLOOR_MS, nombre
    return produccion


@pytest.fixture
def import_dir(tmp_path: Path) -> Path:
    carpeta = tmp_path / "importar"
    carpeta.mkdir()
    return carpeta


@pytest.fixture
def settings_importacion(settings_prueba: Settings, import_dir: Path) -> Settings:
    return settings_prueba.model_copy(update={"IMPORT_DIR": import_dir})


@pytest.fixture
def settings_importacion_produccion(settings_produccion: Settings, import_dir: Path) -> Settings:
    return settings_produccion.model_copy(update={"IMPORT_DIR": import_dir})


async def _vaciar(engine: AsyncEngine, ultima_seq: int) -> None:
    await limpiar_tras_dos_sesiones(engine, ultima_seq)
    await limpiar_llaves_con_commit(engine)
    async with engine.begin() as conexion:
        await conexion.execute(text(disable_user_sql("crypto.crypto_ops")))
        await conexion.execute(text("DELETE FROM crypto.crypto_ops"))
        await conexion.execute(text(rearm_always_sql("crypto.crypto_ops")))


@pytest.fixture
async def limpiar_demo(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    configure_keyring(None)
    configure_provider(None)
    await _vaciar(engine, 0)  # base vacía de socios, planes y llaves antes de empezar
    async with engine.connect() as conexion:
        ultima = int(await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0))) or 0)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        configure_keyring(None)
        configure_provider(None)
        await _vaciar(engine, ultima)
