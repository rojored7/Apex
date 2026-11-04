"""`export-kek` y `verify-kek-backup` con el `age` real bajo un pseudoterminal (S4B-B3a, S4B-D58,
S4B-D89, S4B-D103).

Solo Linux con `age`: se saltan en el host Windows (se cuentan por archivo en el cuaderno) y la CI
exige cero saltos. El CLI corre como subproceso (`python -m app.cli`) con un `.env` propio de la
prueba en su directorio de trabajo, para que `age` abra `/dev/tty` del pseudoterminal.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from app.cli_ops.keys import KeyPaths
from app.core.config import Settings
from app.core.crypto import archive
from tests.cli._apoyo import correr_con_pty
from tests.conftest import CLAVE_PRUEBA
from tests.factories.users import make_user

pytestmark = [
    pytest.mark.skipif(
        sys.platform == "win32" or shutil.which(archive.AGE_BINARY) is None,
        reason="age real y pty solo en Linux",
    ),
    pytest.mark.usefixtures("reloj", "limpiar_demo"),
]

FRASE = "una-frase-de-prueba-larga-y-unica-5512"


@pytest.fixture
async def admin(limpiar_demo: Any, argon2_rapido: None) -> Any:
    async with limpiar_demo() as sesion:
        return await make_user(sesion, role="admin", password=CLAVE_PRUEBA)


def _carpeta_con_env(tmp_path: Path, settings: Settings, rutas: KeyPaths) -> Path:
    carpeta = tmp_path / "cwd"
    carpeta.mkdir()
    (carpeta / ".env").write_text(
        f"DATABASE_URL={settings.DATABASE_URL.get_secret_value()}\n"
        f"JWT_PRIVATE_KEY_PATH={rutas.jwt_private}\n"
        "CRYPTO_PROVIDER=local\n"
        f"CRYPTO_LOCAL_KEK_PATH={rutas.kek}\n"
        f"CRYPTO_LOCAL_SIGNING_KEY_PATH={rutas.signing_key}\n"
        f"BACKUP_DIR={settings.BACKUP_DIR}\n"
        "UPLOADS_DIR=/data/uploads\n"
        'CORS_ORIGINS=["http://localhost"]\n'
        "LOG_LEVEL=INFO\nENV=dev\nMIGRATE_ON_STARTUP=false\n",
        encoding="utf-8",
    )
    return carpeta


def _cli(*args: str) -> list[str]:
    return [sys.executable, "-m", "app.cli", *args]


async def test_export_kek_con_age_real_y_verify_kek_backup_ida_y_vuelta(
    settings_kek: Settings,
    kek_de_prueba: KeyPaths,
    llaves_en_base: Any,
    admin: Any,
    tmp_path: Path,
) -> None:
    cwd = _carpeta_con_env(tmp_path, settings_kek, kek_de_prueba)
    destino = tmp_path / "salidas" / "kek.age"
    destino.parent.mkdir()

    exportar, _ = correr_con_pty(
        _cli("export-kek", "--out", str(destino), "--as", admin.email), FRASE, cwd=cwd
    )
    verificar, transcripcion = correr_con_pty(
        _cli("verify-kek-backup", str(destino), "--as", admin.email), FRASE, cwd=cwd
    )

    assert exportar == 0 and destino.exists()
    assert kek_de_prueba.kek.read_bytes() not in destino.read_bytes()
    assert verificar == 0, transcripcion
    assert "verify-kek-backup: total=8 failed=0" in transcripcion


async def test_verify_kek_backup_con_la_frase_equivocada_sale_2(
    settings_kek: Settings,
    kek_de_prueba: KeyPaths,
    llaves_en_base: Any,
    admin: Any,
    tmp_path: Path,
) -> None:
    cwd = _carpeta_con_env(tmp_path, settings_kek, kek_de_prueba)
    destino = tmp_path / "salidas" / "kek.age"
    destino.parent.mkdir()
    correr_con_pty(_cli("export-kek", "--out", str(destino), "--as", admin.email), FRASE, cwd=cwd)

    codigo, transcripcion = correr_con_pty(
        _cli("verify-kek-backup", str(destino), "--as", admin.email), "otra-frase", cwd=cwd
    )

    assert codigo == 2, transcripcion
    assert "no se pudo abrir el respaldo" in transcripcion
