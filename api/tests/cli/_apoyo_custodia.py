"""Apoyo de las pruebas CLI de S5-B2 (`migrate-provider`, `rotate-kek`, `retire-local-kek`).

`tests/cli/conftest.py` reexporta las fixtures. Contrato común de los tres comandos:
- los proveedores salen SOLO de `app.core.crypto.provider.get_provider_named` / `make_resolver`
  por atributo de módulo (la fixture `custodia` lo parchea: `openbao` es el `OpenBaoProvider` sobre
  `FakeTransit` y `local` el real, con la KEK copiada a `tmp_path/keys/kek.bin`);
- `--manifest RUTA` (como `retire-key`) apunta el `latest.json`, que debe quedar bajo `BACKUP_DIR`;
- exigencias de H-1, en este orden y con textos fijos que NO traen texto del proveedor: un
  `verify-kek-backup` `ok` de una persona de menos de 24 h (`SIN_VERIFY`) y un manifiesto firmado,
  `verify: ok`, de menos de 24 h con `openbao_snapshot` verificado y presente en disco
  (`SIN_MANIFIESTO`); todo rechazo sale con 2;
- confirmación escrita por stdin (`MIGRAR`, `RECORTAR`, `RETIRAR`) o `--yes` donde se indica;
- `ENV=production` sin `--as`: 2 (`--as <correo> es obligatorio con ENV=production`).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from click.testing import Result
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cli import app
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID
from app.core.crypto import provider as provider_mod
from tests.cli._apoyo import correr
from tests.conftest import CLAVE_PRUEBA
from tests.crypto._migracion import Entorno, manifiesto_con_snapshot
from tests.crypto._rotacion import LLAVE_RETIRO, verify_reciente
from tests.factories.users import make_user

SIN_VERIFY = "no hay un verify-kek-backup ok de una persona en las últimas 24 h"
SIN_MANIFIESTO = (
    "no hay un latest.json reciente con firma e instantánea de OpenBao verificada en "
    "/data/backups (verify: ok)"
)
SIN_SNAPSHOT_POSTERIOR = "el respaldo con instantánea de OpenBao es anterior a la rotación"
TRIM_NO_LISTO = "aún hay llaves sin re-envolver con la última versión de la KEK"
QUEDAN_LOCAL = "quedan llaves envueltas con la KEK local; ejecute migrate-provider antes"
SIN_AS_EN_PRODUCCION = "--as <correo> es obligatorio con ENV=production"

VERIFY_MALOS: dict[str, dict[str, Any] | None] = {
    "sin ninguna fila": None,
    "de hace 25 horas": {"edad": timedelta(hours=25)},
    "del usuario técnico": {"actor": SYSTEM_USER_ID},
    "con resultado error": {"resultado": "error"},
}

MANIFIESTOS_MALOS: dict[str, dict[str, Any]] = {
    "sin instantánea de OpenBao": {"snapshot": False},
    "con instantánea no verificada": {"snapshot_verified": False},
    "con el archivo de la instantánea borrado": {"tamper": "snapshot_missing"},
    "con el sha256 de la instantánea cambiado": {"tamper": "snapshot_sha256"},
    "con firma mala": {"tamper": "signature"},
    "con verify distinto de ok": {"verify": "failed"},
    "de hace 25 horas": {"antiguedad": timedelta(hours=25)},
}


@pytest.fixture
def settings_custodia(settings_prueba: Settings, tmp_path: Path) -> Settings:
    """`BACKUP_DIR` y la llave pública de prueba; la KEK local es una COPIA en `tmp_path/keys`
    (el retiro borra esa copia, nunca la KEK de la sesión de pruebas)."""
    carpeta = tmp_path / "keys"
    carpeta.mkdir()
    for origen in (
        settings_prueba.CRYPTO_LOCAL_KEK_PATH,
        settings_prueba.CRYPTO_LOCAL_SIGNING_KEY_PATH,
    ):
        assert origen is not None
        copia = carpeta / origen.name
        shutil.copyfile(origen, copia)
        copia.chmod(0o600)
    assert settings_prueba.CRYPTO_LOCAL_KEK_PATH is not None
    return settings_prueba.model_copy(
        update={
            "BACKUP_DIR": tmp_path,
            "BACKUP_SIGN_PUBKEY": LLAVE_RETIRO.pubkey,
            "CRYPTO_LOCAL_KEK_PATH": carpeta / settings_prueba.CRYPTO_LOCAL_KEK_PATH.name,
            "CRYPTO_LOCAL_SIGNING_KEY_PATH": carpeta
            / (settings_prueba.CRYPTO_LOCAL_SIGNING_KEY_PATH.name),
        }
    )


@pytest.fixture
def custodia(
    migracion_lista: Entorno, settings_custodia: Settings, monkeypatch: pytest.MonkeyPatch
) -> Entorno:
    """El entorno de custodia con `get_provider_named` parchado (`openbao` = Transit falso)."""
    original: Callable[[Settings, str], Any] = provider_mod.get_provider_named

    def falso(settings: Settings, nombre: str) -> Any:
        if nombre == "openbao":
            return migracion_lista.openbao  # se lee al pedir: una prueba puede cambiarlo
        return original(settings, nombre)

    monkeypatch.setattr(provider_mod, "get_provider_named", falso)
    return migracion_lista


@pytest.fixture
async def admin_custodia(
    limpiar_demo: async_sessionmaker[AsyncSession], argon2_rapido: None
) -> Any:
    async with limpiar_demo() as sesion:
        return await make_user(sesion, role="admin", password=CLAVE_PRUEBA)


async def con_verify(entorno: Entorno, admin: Any, **cambios: Any) -> None:
    async with entorno.fabrica() as sesion:
        await verify_reciente(sesion, cambios.pop("actor", admin.id), **cambios)


def manifiesto_bueno(tmp_path: Path, **cambios: Any) -> Path:
    return manifiesto_con_snapshot(tmp_path / "respaldos-b2", **cambios)


def ejecutar(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    comando: str,
    *args: str,
    entrada: str | None = None,
    env: Any = "dev",
    previo: tuple[str, ...] = (),
) -> Result:
    return correr(
        app,
        [*previo, comando, *args],
        env,
        base=settings,
        monkeypatch=monkeypatch,
        entrada=entrada,
    )


# S5-D188 a D190 ---------------------------------------------------------------------------------

TRIM_CAMBIO = "la KEK o las envolturas cambiaron desde la comprobación; repita la comprobación"
BASE_OCUPADA = "la base está ocupada; repita el comando"
OTRA_OPERACION = "hay otra operación de llaves en curso; repita el comando más tarde"
UNLINK_FALLO = "no se pudo borrar el archivo de la KEK local; repita el comando"


def base_ocupada(*_args: Any, **_kwargs: Any) -> Any:
    """Sustituto de `migration._una_llave`: la base agota `lock_timeout` (SQLSTATE 55P03)."""
    from sqlalchemy.exc import DBAPIError

    async def _falla() -> bool:
        orig = type("Orig", (Exception,), {"sqlstate": "55P03"})()
        raise DBAPIError("SELECT 1", {}, orig)

    return _falla()


@pytest.fixture
async def candado_kek_tomado(engine: Any) -> Any:
    """`pg_try_advisory_lock(hashtext('apex:rotate:kek'))` tomado en otra conexión."""
    from sqlalchemy import text

    clave = {"c": "apex:rotate:kek"}
    async with engine.connect() as conexion:
        assert await conexion.scalar(text("SELECT pg_try_advisory_lock(hashtext(:c))"), clave)
        try:
            yield
        finally:
            await conexion.execute(text("SELECT pg_advisory_unlock(hashtext(:c))"), clave)
