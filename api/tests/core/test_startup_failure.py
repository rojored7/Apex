"""Si una migración falla al arrancar, el api no acepta tráfico (US-020, T4 y T8)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import Settings
from app.main import create_app

API_ROOT = Path(__file__).resolve().parents[2]

MIGRACION_ROTA = '''"""Migración rota de prueba."""
revision = "9999_rota"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    raise RuntimeError("migración rota a propósito")


def downgrade() -> None:
    pass
'''


@pytest.fixture
def migraciones_rotas(tmp_path: Path) -> str:
    carpeta = tmp_path / "migraciones"
    (carpeta / "versions").mkdir(parents=True)
    (carpeta / "env.py").write_text((API_ROOT / "migrations" / "env.py").read_text(encoding="utf-8"), encoding="utf-8")
    (carpeta / "script.py.mako").write_text("", encoding="utf-8")
    (carpeta / "versions" / "9999_rota.py").write_text(MIGRACION_ROTA, encoding="utf-8")
    return str(carpeta)


async def test_el_lifespan_relanza_el_error_de_migracion(
    settings_prueba: Settings, migraciones_rotas: str
) -> None:
    app = create_app(settings_prueba, migrations_script_location=migraciones_rotas)
    with pytest.raises(RuntimeError, match="migración rota"):
        async with app.router.lifespan_context(app):
            pass


def test_uvicorn_termina_con_codigo_distinto_de_cero(
    settings_prueba: Settings, migraciones_rotas: str
) -> None:
    entorno = {
        **os.environ,
        "DATABASE_URL": settings_prueba.DATABASE_URL.get_secret_value(),
        "JWT_PRIVATE_KEY_PATH": "/run/apex/keys/jwt_ed25519.pem",
        "CRYPTO_PROVIDER": "local",
        "CRYPTO_LOCAL_KEK_PATH": "/run/apex/keys/kek.bin",
        "UPLOADS_DIR": "/data/uploads",
        "CORS_ORIGINS": '["http://localhost"]',
        "APEX_TEST_MIGRATIONS": migraciones_rotas,
    }
    resultado = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tests.core._app_rota:crear",
            "--factory",
            "--port",
            "0",
            "--log-level",
            "warning",
        ],
        cwd=API_ROOT,
        env=entorno,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert resultado.returncode != 0, resultado.stdout + resultado.stderr
    assert "migración rota" in resultado.stdout + resultado.stderr
