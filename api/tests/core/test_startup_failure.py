"""Si una migración falla al arrancar, el api no acepta tráfico (US-020, T4 y T8)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import Settings
from app.main import create_app

API_ROOT = Path(__file__).resolve().parents[2]

MIGRACION_ROTA = '''"""Migración rota de prueba."""
revision = "9999_rota"
down_revision = "__HEAD__"
branch_labels = None
depends_on = None


def upgrade() -> None:
    raise RuntimeError("migración rota a propósito")


def downgrade() -> None:
    pass
'''


@pytest.fixture
def migraciones_rotas(tmp_path: Path) -> str:
    """Copia de migrations/ con una revisión extra que falla sobre el head real."""
    carpeta = tmp_path / "migraciones"
    shutil.copytree(API_ROOT / "migrations", carpeta, ignore=shutil.ignore_patterns("__pycache__"))
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "migrations"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert head is not None
    (carpeta / "versions" / "9999_rota.py").write_text(
        MIGRACION_ROTA.replace("__HEAD__", head), encoding="utf-8"
    )
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
        # M-9 (E3): sin ENV es producción, y producción exige la cookie Secure.
        "COOKIE_SECURE": "true",
        "MIGRATE_ON_STARTUP": "true",
        "APEX_TEST_MIGRATIONS": migraciones_rotas,
    }
    resultado = subprocess.run(
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


# S4B-W0-3 (S4B-D8): MIGRATE_ON_STARTUP manda; el argumento explícito manda sobre Settings -------


class _ParadaTrasMigrar(Exception):
    """Corta el lifespan justo después del paso de migraciones (sin abrir llaves ni la base)."""


def _con_migrate(settings: Settings, tmp_path: Path, valor: str | None) -> Settings:
    """Los mismos valores de `settings_prueba` con `MIGRATE_ON_STARTUP` en el `.env`."""
    from app.core.config import load_settings

    env = tmp_path / "con_migrate.env"
    env.write_text(
        f"DATABASE_URL={settings.DATABASE_URL.get_secret_value()}\n"
        f"JWT_PRIVATE_KEY_PATH={settings.JWT_PRIVATE_KEY_PATH}\n"
        f"CRYPTO_PROVIDER=local\nCRYPTO_LOCAL_KEK_PATH={settings.CRYPTO_LOCAL_KEK_PATH}\n"
        f"UPLOADS_DIR={settings.UPLOADS_DIR}\n"
        'CORS_ORIGINS=["http://localhost"]\nENV=dev\n'
        + (f"MIGRATE_ON_STARTUP={valor}\n" if valor is not None else ""),
        encoding="utf-8",
    )
    return load_settings(env_file=env)


@pytest.fixture
def espia_de_migraciones(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    llamadas: list[str] = []

    def espia(settings: Settings, script_location: str | None = None) -> None:
        llamadas.append("run_migrations")

    def parar(settings: Settings) -> None:
        raise _ParadaTrasMigrar

    monkeypatch.setattr("app.main.run_migrations", espia)
    monkeypatch.setattr("app.main.check_secrets_or_exit", parar)
    return llamadas


async def _arrancar(app: object) -> None:
    with pytest.raises(_ParadaTrasMigrar):
        async with app.router.lifespan_context(app):  # type: ignore[attr-defined]
            pass


async def test_con_migrate_on_startup_false_create_app_sin_argumento_no_migra(
    settings_prueba: Settings, tmp_path: Path, espia_de_migraciones: list[str]
) -> None:
    app = create_app(_con_migrate(settings_prueba, tmp_path, "false"))
    await _arrancar(app)
    assert espia_de_migraciones == []


async def test_sin_la_variable_create_app_sin_argumento_no_migra(
    settings_prueba: Settings, tmp_path: Path, espia_de_migraciones: list[str]
) -> None:
    """M3: cerrado por defecto. Un api de producción al que le falte la variable no migra."""
    app = create_app(_con_migrate(settings_prueba, tmp_path, None))
    await _arrancar(app)
    assert espia_de_migraciones == []


async def test_con_migrate_on_startup_true_create_app_sin_argumento_migra(
    settings_prueba: Settings, tmp_path: Path, espia_de_migraciones: list[str]
) -> None:
    app = create_app(_con_migrate(settings_prueba, tmp_path, "true"))
    await _arrancar(app)
    assert espia_de_migraciones == ["run_migrations"]


async def test_el_argumento_explicito_true_manda_sobre_settings_false(
    settings_prueba: Settings, tmp_path: Path, espia_de_migraciones: list[str]
) -> None:
    app = create_app(
        _con_migrate(settings_prueba, tmp_path, "false"), run_migrations_on_startup=True
    )
    await _arrancar(app)
    assert espia_de_migraciones == ["run_migrations"]


async def test_el_argumento_explicito_false_manda_sobre_settings_true(
    settings_prueba: Settings, tmp_path: Path, espia_de_migraciones: list[str]
) -> None:
    app = create_app(
        _con_migrate(settings_prueba, tmp_path, "true"), run_migrations_on_startup=False
    )
    await _arrancar(app)
    assert espia_de_migraciones == []


async def test_el_argumento_none_equivale_a_no_pasarlo(
    settings_prueba: Settings, tmp_path: Path, espia_de_migraciones: list[str]
) -> None:
    app = create_app(
        _con_migrate(settings_prueba, tmp_path, "true"), run_migrations_on_startup=None
    )
    await _arrancar(app)
    assert espia_de_migraciones == ["run_migrations"]


async def test_una_migracion_rota_con_true_relanza_y_el_log_nombra_la_revision_sin_url(
    settings_prueba: Settings,
    tmp_path: Path,
    migraciones_rotas: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configuracion = _con_migrate(settings_prueba, tmp_path, "true")
    app = create_app(configuracion, migrations_script_location=migraciones_rotas)
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", migraciones_rotas)
    conocidas = {r.revision for r in ScriptDirectory.from_config(cfg).walk_revisions()}
    with caplog.at_level("ERROR", logger="app.main"):
        with pytest.raises(RuntimeError, match="migración rota"):
            async with app.router.lifespan_context(app):
                pass
    registros = [r for r in caplog.records if r.name == "app.main" and r.levelname == "ERROR"]
    assert len(registros) == 1
    revision = getattr(registros[0], "revision", None)
    # La que falló ("9999_rota") o la que quedó aplicada en la base: siempre una conocida.
    assert isinstance(revision, str) and revision in conocidas, revision
    texto = caplog.text + registros[0].getMessage() + (registros[0].exc_text or "")
    secreto = configuracion.DATABASE_URL.get_secret_value()
    assert secreto not in texto
    assert "apex-test" not in texto and "postgresql+asyncpg://" not in texto
