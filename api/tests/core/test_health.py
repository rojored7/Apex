"""`GET /health` y `GET /api/v1/health` (US-020, T6 y T9; N-16)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, load_settings
from app.core.db import dispose_engine
from app.core.health import CheckResult, clear_health_checks, register_health_check
from app.main import create_app


@pytest.fixture(autouse=True)
async def _limpio() -> AsyncIterator[None]:
    clear_health_checks()
    yield
    clear_health_checks()
    await dispose_engine()


def _cliente(settings: Settings) -> AsyncClient:
    app = create_app(settings, run_migrations_on_startup=False)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://pruebas")


async def test_health_en_raiz_y_bajo_api_v1(settings_prueba: Settings) -> None:
    async with _cliente(settings_prueba) as c:
        r1 = await c.get("/health")
        r2 = await c.get("/api/v1/health")
    for r in (r1, r2):
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["db"] == "ok"
        assert r.json()["version"] == "dev"
        assert "DATABASE_URL" not in r.text
        assert "apex-test" not in r.text
        assert "kek" not in r.text.lower()


async def test_base_caida_da_503_en_menos_de_3_segundos(
    settings_prueba: Settings, tmp_path: object
) -> None:
    env = tmp_path / ".env"  # type: ignore[operator]
    env.write_text(
        "DATABASE_URL=postgresql+asyncpg://apex:x@127.0.0.1:1/apex\n"
        "JWT_PRIVATE_KEY_PATH=/k.pem\nCRYPTO_PROVIDER=local\nCRYPTO_LOCAL_KEK_PATH=/kek\n"
        'UPLOADS_DIR=/data\nCORS_ORIGINS=["http://localhost"]\n'
        "COOKIE_SECURE=true\n",  # sin ENV es producción: M-9 (E3)
        encoding="utf-8",
    )
    caida = load_settings(env_file=env)
    inicio = time.perf_counter()
    async with _cliente(caida) as c:
        r = await c.get("/health")
    assert time.perf_counter() - inicio < 3
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["db"] == "down"


async def test_comprobacion_informativa_no_baja_el_200_y_la_critica_si(
    settings_prueba: Settings,
) -> None:
    async def backup() -> CheckResult:
        return "down"

    async def openbao() -> CheckResult:
        return "down"

    register_health_check("backup", backup, critical=False)
    async with _cliente(settings_prueba) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["backup"] == "down"
    assert r.json()["status"] == "ok"

    register_health_check("openbao", openbao, critical=True)
    async with _cliente(settings_prueba) as c:
        r = await c.get("/health")
    assert r.status_code == 503
    assert r.json()["openbao"] == "down"
    assert r.json()["status"] == "degraded"


async def test_docs_apagados_en_produccion(settings_prueba: Settings, tmp_path: object) -> None:
    env = tmp_path / ".env"  # type: ignore[operator]
    env.write_text(
        f"DATABASE_URL={settings_prueba.DATABASE_URL.get_secret_value()}\n"
        "JWT_PRIVATE_KEY_PATH=/k.pem\nCRYPTO_PROVIDER=local\nCRYPTO_LOCAL_KEK_PATH=/kek\n"
        'UPLOADS_DIR=/data\nCORS_ORIGINS=["http://localhost"]\nENV=production\n'
        "COOKIE_SECURE=true\n",  # M-9 (E3)
        encoding="utf-8",
    )
    produccion = load_settings(env_file=env)
    async with _cliente(produccion) as c:
        assert (await c.get("/docs")).status_code == 404
        assert (await c.get("/openapi.json")).status_code == 404
        assert (await c.get("/health")).status_code == 200
    async with _cliente(settings_prueba) as c:
        assert (await c.get("/docs")).status_code == 200
