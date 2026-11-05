"""Rendimiento de `GET /health` con la caché caliente (S5-D261). Marcada `perf`: no es gate.

Con la caché caliente, 200 peticiones secuenciales y 20 concurrentes responden 200 con p95 por
debajo de `P95_MAX_S`, y la base se consulta una sola vez en toda la ráfaga (el reloj congelado
no deja caducar el TTL de 2 s). Sin `sleep` real.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.core import health
from app.core.clock import FrozenClock, reset_clock, set_clock
from app.core.config import Settings
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.provider import configure_provider
from app.core.db import dispose_engine
from app.core.health import CheckResult, clear_health_cache, clear_health_checks
from app.main import create_app

pytestmark = pytest.mark.perf

P95_MAX_S = 0.050
SECUENCIALES = 200
CONCURRENTES = 20


@pytest.fixture(autouse=True)
async def _limpio(proveedor_local: LocalFileProvider) -> AsyncIterator[None]:
    clear_health_checks()
    configure_provider(proveedor_local)
    configure_keyring(Keyring())
    yield
    clear_health_checks()
    configure_keyring(None)
    configure_provider(None)
    await dispose_engine()


@pytest.fixture
def reloj() -> Iterator[FrozenClock]:
    congelado = FrozenClock(datetime(2026, 11, 5, 15, 0, tzinfo=UTC))
    token = set_clock(congelado)
    clear_health_cache()
    yield congelado
    clear_health_cache()
    reset_clock(token)


def _p95(muestras: list[float]) -> float:
    ordenadas = sorted(muestras)
    return ordenadas[math.ceil(0.95 * len(ordenadas)) - 1]


async def _medir(cliente: AsyncClient) -> tuple[float, Response]:
    inicio = time.perf_counter()
    respuesta = await cliente.get("/health")
    return time.perf_counter() - inicio, respuesta


async def test_health_con_cache_caliente_p95_bajo_y_una_sola_consulta_a_la_base(
    settings_prueba: Settings, reloj: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    llamadas = 0
    original = health.check_db

    async def espia() -> CheckResult:
        nonlocal llamadas
        llamadas += 1
        return await original()

    monkeypatch.setattr(health, "check_db", espia)
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://pruebas") as c:
        assert (await c.get("/health")).status_code == 200  # calienta la caché

        # Act
        secuenciales = [await _medir(c) for _ in range(SECUENCIALES)]
        concurrentes = await asyncio.gather(*(_medir(c) for _ in range(CONCURRENTES)))

    # Assert
    assert all(r.status_code == 200 for _, r in secuenciales + list(concurrentes))
    assert len(secuenciales) == SECUENCIALES and len(concurrentes) == CONCURRENTES
    assert _p95([t for t, _ in secuenciales]) < P95_MAX_S
    assert _p95([t for t, _ in concurrentes]) < P95_MAX_S
    assert llamadas == 1  # una vez por TTL: el reloj congelado no lo deja caducar
