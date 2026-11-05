"""`migrations` en `/health` (S4B-B4; S4B-D27, S4B-D60, S4B-D91). Base propia `apex_health_mig`.

- en `head` -> 200 con `migrations: "ok"`; tras `downgrade -1` o con una revisión desconocida en
  `alembic_version` -> 503 `degraded` con `"mismatch"` (el cuerpo no distingue detrás de delante);
- base caída -> `degraded` con `unknown`; `/health` y `/api/v1/health` iguales;
- el cuerpo no trae ninguna revisión; la caché de 30 s solo cambia al vencer o con
  `clear_health_cache()`;
- `create_app` registra el check crítico y configura `head`/`known` sin necesitar el lifespan;
- el lifespan con una migración rota relanza y el log nombra la revisión sin URL ni contraseña.
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from httpx import ASGITransport, AsyncClient

from app.core import health
from app.core.clock import FrozenClock
from app.core.config import load_settings
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.provider import configure_provider
from app.core.db import dispose_engine
from app.core.health import clear_health_cache, clear_health_checks
from app.core.migrations_status import migrations_health
from app.main import create_app
from tests.conftest import API_ROOT, T0
from tests.core._health_mig import HealthMig, apex_health_mig

__all__ = ["apex_health_mig"]

CLAVES_DEL_CUERPO = {"status", "db", "version", "backup", "migrations", "crypto"}


@pytest.fixture(autouse=True)
async def _limpio(proveedor_local: LocalFileProvider) -> AsyncIterator[None]:
    # S5-B3: `crypto` es una comprobación crítica de `create_app`; estas pruebas miden
    # `migrations`, así que el proceso tiene un custodio sano (proveedor y keyring vacío).
    clear_health_checks()
    configure_provider(proveedor_local)
    configure_keyring(Keyring())
    yield
    clear_health_checks()
    configure_keyring(None)
    configure_provider(None)
    await dispose_engine()


def _cliente(mig: HealthMig) -> AsyncClient:
    app = create_app(mig.settings, run_migrations_on_startup=False)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://pruebas")


async def test_en_head_responde_200_con_migrations_ok(apex_health_mig: HealthMig) -> None:
    async with _cliente(apex_health_mig) as c:
        r = await c.get("/health")
    assert r.status_code == 200, r.text
    assert r.json()["migrations"] == "ok"
    assert r.json()["status"] == "ok"


async def test_tras_downgrade_menos_uno_responde_503_degraded_con_mismatch(
    apex_health_mig: HealthMig,
) -> None:
    await apex_health_mig.downgrade("-1")
    async with _cliente(apex_health_mig) as c:
        r = await c.get("/health")
    assert r.status_code == 503, r.text
    assert r.json()["status"] == "degraded"
    assert r.json()["migrations"] == "mismatch"
    assert r.json()["db"] == "ok"


async def test_una_revision_desconocida_en_alembic_version_responde_503_mismatch(
    apex_health_mig: HealthMig,
) -> None:
    await apex_health_mig.set_revision("9999_desconocida")
    async with _cliente(apex_health_mig) as c:
        r = await c.get("/health")
    assert r.status_code == 503, r.text
    assert r.json()["status"] == "degraded"
    assert r.json()["migrations"] == "mismatch"
    assert "9999_desconocida" not in r.text


async def test_con_la_base_caida_es_degraded_y_migrations_unknown(
    apex_health_mig: HealthMig, tmp_path: Path
) -> None:
    env = tmp_path / "caida.env"
    env.write_text(
        "DATABASE_URL=postgresql+asyncpg://apex:x@127.0.0.1:1/apex\n"
        "JWT_PRIVATE_KEY_PATH=/k.pem\nCRYPTO_PROVIDER=local\nCRYPTO_LOCAL_KEK_PATH=/kek\n"
        'UPLOADS_DIR=/data\nCORS_ORIGINS=["http://localhost"]\nENV=dev\n',
        encoding="utf-8",
    )
    app = create_app(load_settings(env_file=env), run_migrations_on_startup=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://p") as c:
        r = await c.get("/health")
    assert "migrations" in health._checks, "main.py no registra el check migrations"
    assert r.status_code == 503
    assert (r.json()["status"], r.json()["db"], r.json()["migrations"]) == (
        "degraded",
        "down",
        "unknown",
    )


@pytest.mark.parametrize("estado", ["head", "mismatch"])
async def test_health_y_api_v1_health_son_iguales(apex_health_mig: HealthMig, estado: str) -> None:
    if estado == "mismatch":
        await apex_health_mig.downgrade("-1")
    async with _cliente(apex_health_mig) as c:
        r1 = await c.get("/health")
        r2 = await c.get("/api/v1/health")
    esperado = 200 if estado == "head" else 503
    assert r1.status_code == r2.status_code == esperado
    assert r1.json() == r2.json()
    assert r1.json()["migrations"] == ("ok" if estado == "head" else "mismatch")


@pytest.mark.parametrize("estado", ["head", "atras", "desconocida"])
async def test_el_cuerpo_no_trae_la_revision(apex_health_mig: HealthMig, estado: str) -> None:
    if estado == "atras":
        await apex_health_mig.downgrade("-1")
    elif estado == "desconocida":
        await apex_health_mig.set_revision("9999_desconocida")
    async with _cliente(apex_health_mig) as c:
        r = await c.get("/health")
    assert r.json()["migrations"] in {"ok", "mismatch"}
    assert set(r.json()) == CLAVES_DEL_CUERPO
    for revision in (apex_health_mig.head, apex_health_mig.anterior, "9999_desconocida"):
        assert revision not in r.text


async def test_la_cache_de_30_segundos_solo_cambia_al_vencer_el_ttl(
    apex_health_mig: HealthMig, reloj: FrozenClock
) -> None:
    async with _cliente(apex_health_mig) as c:
        assert (await c.get("/health")).json()["migrations"] == "ok"
        await apex_health_mig.downgrade("-1")
        reloj.set(T0 + timedelta(seconds=29))
        r = await c.get("/health")
        assert (r.status_code, r.json()["migrations"]) == (200, "ok")
        reloj.set(T0 + timedelta(seconds=31))
        r = await c.get("/health")
    assert (r.status_code, r.json()["migrations"]) == (503, "mismatch")


async def test_clear_health_cache_hace_visible_el_cambio_de_inmediato(
    apex_health_mig: HealthMig, reloj: FrozenClock
) -> None:
    async with _cliente(apex_health_mig) as c:
        assert (await c.get("/health")).json()["migrations"] == "ok"
        await apex_health_mig.downgrade("-1")
        assert (await c.get("/health")).json()["migrations"] == "ok"
        clear_health_cache()
        r = await c.get("/health")
    assert (r.status_code, r.json()["migrations"]) == (503, "mismatch")


async def test_create_app_registra_migrations_como_critico_con_los_tres_valores(
    apex_health_mig: HealthMig,
) -> None:
    _cliente(apex_health_mig)
    registrada = health._checks.get("migrations")
    assert registrada is not None, "main.py no registra el check migrations"
    assert registrada.critical is True
    assert registrada.allowed == frozenset({"ok", "mismatch", "unknown"})
    assert registrada.healthy == frozenset({"ok"})


async def test_create_app_configura_head_y_known_y_migrations_health_lo_usa(
    apex_health_mig: HealthMig,
) -> None:
    _cliente(apex_health_mig)  # create_app configura head/known y el engine, sin lifespan
    assert await migrations_health() == "ok"
    await apex_health_mig.downgrade("-1")
    assert await migrations_health() == "mismatch"
    await apex_health_mig.upgrade("head")
    await apex_health_mig.set_revision("9999_desconocida")
    assert await migrations_health() == "mismatch"


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


async def test_el_lifespan_con_migracion_rota_relanza_y_el_log_nombra_la_revision_sin_secretos(
    apex_health_mig: HealthMig, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    carpeta = tmp_path / "migraciones"
    shutil.copytree(API_ROOT / "migrations", carpeta, ignore=shutil.ignore_patterns("__pycache__"))
    (carpeta / "versions" / "9999_rota.py").write_text(
        MIGRACION_ROTA.replace("__HEAD__", apex_health_mig.head), encoding="utf-8"
    )
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(carpeta))
    conocidas = {r.revision for r in ScriptDirectory.from_config(cfg).walk_revisions()}
    app = create_app(
        apex_health_mig.settings,
        run_migrations_on_startup=True,
        migrations_script_location=str(carpeta),
    )
    with caplog.at_level("ERROR", logger="app.main"):
        with pytest.raises(RuntimeError, match="migración rota"):
            async with app.router.lifespan_context(app):
                pass
    registros = [r for r in caplog.records if r.name == "app.main" and r.levelname == "ERROR"]
    assert len(registros) == 1
    assert getattr(registros[0], "revision", None) in conocidas
    texto = caplog.text + registros[0].getMessage() + (registros[0].exc_text or "")
    assert apex_health_mig.settings.DATABASE_URL.get_secret_value() not in texto
    assert "apex-test" not in texto and "postgresql+asyncpg://" not in texto
