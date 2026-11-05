"""Si una migración falla al arrancar, el api no acepta tráfico (US-020, T4 y T8).

S5-B3 (S5-D14, M-4; Rojo): una prueba por rama del arranque ante el custodio de llaves.
`sealed` o `unreachable` degradan (sin keyring, con `gc.freeze()` y seguridad configurada);
`unwrap_failed`, `key_missing` y `forbidden` abortan sin envolver DEK nuevas; sin KEK local aborta.
"""

from __future__ import annotations

import gc
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import main as main_module
from app.core.config import Settings
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.keyring import current_keyring
from app.core.security import StartupError
from app.main import create_app
from tests.core._cripto_apoyo import base_con_llaves, contar_llaves, proveedor_ctl
from tests.factories.fake_provider import ProveedorControlable, inyectar_proveedor
from tests.factories.triggers import disable_user_sql, rearm_always_sql

__all__ = ["base_con_llaves", "proveedor_ctl"]

Fabrica = async_sessionmaker[AsyncSession]

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


# S5-B3 (S5-D14, M-4): una prueba por rama del arranque ante el custod ---
# Rojo B3. Cada rama abre el `lifespan` real sobre `db_test` con llaves confirmadas.

SELLADO_AL_ARRANCAR = "crypto sealed at startup"


async def _abrir_lifespan(settings: Settings) -> None:
    app = create_app(settings, run_migrations_on_startup=False)
    async with app.router.lifespan_context(app):
        pass


@pytest.mark.parametrize("razon", ["sealed", "unreachable"])
async def test_sellado_o_inalcanzable_arranca_degradado_sin_keyring(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    razon: str,
) -> None:
    proveedor_ctl.estado = razon  # type: ignore[assignment]
    inyectar_proveedor(monkeypatch, proveedor_ctl)
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    caplog.set_level(logging.INFO)
    async with app.router.lifespan_context(app):
        with pytest.raises(CryptoUnavailable):
            current_keyring()
    avisos = [r for r in caplog.records if SELLADO_AL_ARRANCAR in r.getMessage()]
    assert len(avisos) == 1, [r.getMessage() for r in caplog.records]
    assert settings_prueba.DATABASE_URL.get_secret_value() not in caplog.text
    assert "http://" not in avisos[0].getMessage()


async def test_el_arranque_degradado_tambien_congela_con_gc_freeze(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proveedor_ctl.estado = "sealed"
    inyectar_proveedor(monkeypatch, proveedor_ctl)
    congelaciones: list[str] = []
    monkeypatch.setattr(gc, "freeze", lambda: congelaciones.append("freeze"))
    await _abrir_lifespan(settings_prueba)
    assert congelaciones == ["freeze"]


async def test_el_arranque_degradado_sigue_con_seguridad_y_cargador_de_principal(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sellado no es fatal: el JWT queda configurado y el cargador de principal existe (login)."""
    from app.core.security import get_principal_loader

    proveedor_ctl.estado = "sealed"
    inyectar_proveedor(monkeypatch, proveedor_ctl)
    llamadas: list[str] = []
    real = main_module.configure_security
    monkeypatch.setattr(
        main_module, "configure_security", lambda s: (llamadas.append("jwt"), real(s))[1]
    )
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    async with app.router.lifespan_context(app):
        assert llamadas == ["jwt"]
        assert get_principal_loader() is not None


@pytest.mark.parametrize(
    "error",
    [
        CryptoError("unwrap_failed", "la envoltura no abre"),
        CryptoError("key_missing", "la llave del proveedor no existe"),
        CryptoUnavailable("forbidden"),
    ],
    ids=["unwrap_failed", "key_missing", "forbidden"],
)
async def test_unwrap_failed_key_missing_o_forbidden_abortan_y_no_crean_llaves(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: CryptoError,
) -> None:
    """M-4: falta una llave (la de índice del teléfono) y el proveedor no abre las demás; el
    arranque aborta y `ensure_keys` no envuelve ninguna DEK nueva con una KEK ajena."""
    async with base_con_llaves() as sesion, sesion.begin():
        await sesion.execute(text(disable_user_sql("crypto.crypto_keys")))
        await sesion.execute(
            text("DELETE FROM crypto.crypto_keys WHERE purpose = 'index' AND data_class = :c"),
            {"c": "member.phone"},
        )
        await sesion.execute(text(rearm_always_sql("crypto.crypto_keys")))
    antes = await contar_llaves(base_con_llaves)
    proveedor_ctl.error = error
    inyectar_proveedor(monkeypatch, proveedor_ctl)
    caplog.set_level(logging.INFO)
    with pytest.raises(CryptoError) as aborto:
        await _abrir_lifespan(settings_prueba)
    assert aborto.value.code == error.code
    assert proveedor_ctl.wrap_calls == 0, "ensure_keys creó llaves con un proveedor que no abre"
    assert await contar_llaves(base_con_llaves) == antes
    assert SELLADO_AL_ARRANCAR not in caplog.text


async def test_sin_kek_local_el_arranque_aborta(
    base_con_llaves: Fabrica,
    settings_prueba: Settings,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ajustes = settings_prueba.model_copy(update={"CRYPTO_LOCAL_KEK_PATH": tmp_path / "no_hay.bin"})
    caplog.set_level(logging.INFO)
    with pytest.raises((CryptoError, StartupError)) as aborto:
        await _abrir_lifespan(ajustes)
    if isinstance(aborto.value, CryptoError):
        assert aborto.value.code == "kek_missing"
    else:
        assert "CRYPTO_LOCAL_KEK_PATH" in str(aborto.value)
    assert SELLADO_AL_ARRANCAR not in caplog.text
