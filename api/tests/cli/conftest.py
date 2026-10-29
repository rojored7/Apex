"""Fixtures del CLI (plan del Sprint 4A, sección 2, bloques B2 y B3).

- `settings_produccion`: copia de `settings_prueba` con `ENV="production"` (S4A-D53). Los pisos
  de S3-D79 ya se cumplen (los tres `DB_*_TIMEOUT_MS` de `settings_prueba` son los de por
  defecto, de 1.000 ms o más); `model_copy` no revalida, como hace el propio CLI con
  `--db-timeouts off`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from app.core.config import DB_TIMEOUT_FLOOR_MS, Settings


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
