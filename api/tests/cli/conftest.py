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


# Respaldo de la KEK (S4B-B3a; S4B-D58, S4B-D62, S4B-D89) -----------------------------------------
# `kek_de_prueba`: KEK, llave de firma y par JWT reales de `init-keys` en una carpeta propia de la
# prueba (no las de la sesión). `settings_kek` apunta el `Settings` a ellas y a un `BACKUP_DIR`
# vacío; `entorno_kek` además deja el `age` falso como binario y hace que `archive` vea esos mismos
# ajustes. `llaves_en_base` crea las DEK de la base envueltas con ESA KEK (commit real).

from app.cli_ops.keys import KeyPaths, init_keys_files, key_paths_in  # noqa: E402
from app.core.context import SYSTEM_USER_ID, actor_scope  # noqa: E402
from app.core.crypto import archive, oplog  # noqa: E402
from app.core.crypto.bootstrap import ensure_keys  # noqa: E402
from app.core.crypto.local_provider import LocalFileProvider  # noqa: E402
from tests.crypto.conftest import age_falso  # noqa: E402,F401


@pytest.fixture
def kek_de_prueba(tmp_path: Path) -> KeyPaths:
    rutas = key_paths_in(tmp_path / "keys-cli")
    rutas.kek.parent.mkdir()
    init_keys_files(rutas)
    return rutas


@pytest.fixture
def settings_kek(settings_prueba: Settings, kek_de_prueba: KeyPaths, tmp_path: Path) -> Settings:
    respaldos = tmp_path / "backups"
    respaldos.mkdir()
    return settings_prueba.model_copy(
        update={
            "CRYPTO_LOCAL_KEK_PATH": kek_de_prueba.kek,
            "CRYPTO_LOCAL_SIGNING_KEY_PATH": kek_de_prueba.signing_key,
            "BACKUP_DIR": respaldos,
        }
    )


@pytest.fixture
def ajustes_kek(settings_kek: Settings, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """`settings_kek` visible también para `archive` (sin lanzar `age`)."""
    monkeypatch.setattr(archive, "get_settings", lambda: settings_kek)
    return settings_kek


@pytest.fixture
def entorno_kek(ajustes_kek: Settings, age_falso: Path) -> Settings:  # noqa: F811
    """`ajustes_kek` con el `age` falso como binario (en Windows se omite, ver `age_falso`)."""
    return ajustes_kek


@pytest.fixture
async def llaves_en_base(
    limpiar_demo: async_sessionmaker[AsyncSession], kek_de_prueba: KeyPaths
) -> async_sessionmaker[AsyncSession]:
    proveedor = LocalFileProvider(kek_de_prueba.kek, kek_de_prueba.signing_key)
    async with limpiar_demo() as sesion:
        with actor_scope(SYSTEM_USER_ID):
            await ensure_keys(sesion, proveedor)
            await sesion.commit()
    oplog.reset_buffer()
    configure_keyring(None)
    return limpiar_demo


# Rotación de llave y retiro (S4B-B3b): fixtures compartidas con tests/crypto
from tests.crypto._rotacion import (  # noqa: E402,F401
    candado_rotacion_tomado,
    manifiesto_reciente,
    rotacion_lista,
)
