"""`GET /health` y `GET /api/v1/health` (US-020, T6 y T9; N-16)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core import health
from app.core.clock import FrozenClock, reset_clock, set_clock
from app.core.config import Settings, load_settings
from app.core.db import dispose_engine, get_engine
from app.core.health import (
    HEALTH_CACHE_TTL_S,
    CheckResult,
    HealthOut,
    clear_health_cache,
    clear_health_checks,
    register_health_check,
)
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
    async def informativa() -> CheckResult:
        return "down"

    async def openbao() -> CheckResult:
        return "down"

    register_health_check("informativa", informativa, critical=False)
    async with _cliente(settings_prueba) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["informativa"] == "down"
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


async def test_la_version_de_health_es_la_de_app_version(settings_prueba: Settings) -> None:
    """S4B-D13: `build.args.GIT_SHA` -> `APP_VERSION` del contenedor -> `/health.version`."""
    con_version = settings_prueba.model_copy(update={"APP_VERSION": "v0.1.0"})
    async with _cliente(con_version) as c:
        r1 = await c.get("/health")
        r2 = await c.get("/api/v1/health")
    assert r1.json()["version"] == r2.json()["version"] == "v0.1.0"
    assert "-dirty" not in r1.text, "S4B-D67: nunca -dirty en la versión pública"


# S4B-B2 (S4B-D26, S4B-D60, S4B-D91): allowed, healthy, caché y cuerpo colapsado ------------------

PUBLICOS = frozenset({"ok", "attention", "unknown"})
T0 = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def reloj() -> Iterator[FrozenClock]:
    reloj = FrozenClock(T0)
    token = set_clock(reloj)
    try:
        yield reloj
    finally:
        reset_clock(token)


class Contador:
    """Un check que cuenta cuántas veces se ejecutó y devuelve un valor fijo."""

    def __init__(self, valor: str = "ok", demora_s: float = 0.0) -> None:
        self.valor, self.demora_s, self.llamadas = valor, demora_s, 0

    async def __call__(self) -> str:
        self.llamadas += 1
        if self.demora_s:
            await asyncio.sleep(self.demora_s)
        return self.valor


def _registrar_backup(fn: Contador) -> None:
    register_health_check("backup", fn, critical=False, allowed=PUBLICOS, healthy={"ok"})


async def test_las_constantes_de_la_cache_son_las_del_plan() -> None:
    assert HEALTH_CACHE_TTL_S == {"db": 2.0, "backup": 30.0, "migrations": 30.0}


async def test_health_out_backup_por_defecto_es_unknown() -> None:
    assert HealthOut.model_fields["backup"].default == "unknown"
    salida = HealthOut.model_validate({"status": "ok", "db": "ok", "version": "x"})
    assert salida.model_dump()["backup"] == "unknown"


async def test_el_cuerpo_trae_backup_unknown_sin_comprobacion_registrada(
    settings_prueba: Settings,
) -> None:
    async with _cliente(settings_prueba) as c:
        clear_health_checks()
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["backup"] == "unknown"


async def test_create_app_registra_backup_informativo_con_los_tres_valores(
    settings_prueba: Settings,
) -> None:
    _cliente(settings_prueba)
    registrada = health._checks["backup"]
    assert registrada.critical is False
    assert registrada.allowed == PUBLICOS
    assert registrada.healthy == frozenset({"ok"})


@pytest.mark.parametrize("ajeno", ["down", "stale", "missing", "corrupt", "undecryptable", "x"])
async def test_un_valor_ajeno_a_allowed_se_degrada_a_unknown_sin_500(
    ajeno: str, settings_prueba: Settings
) -> None:
    async with _cliente(settings_prueba) as c:
        _registrar_backup(Contador(ajeno))
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["backup"] == "unknown"
    assert f'"{ajeno}"' not in r.text


async def test_un_valor_permitido_pasa_tal_cual(settings_prueba: Settings) -> None:
    async with _cliente(settings_prueba) as c:
        _registrar_backup(Contador("attention"))
        r = await c.get("/health")
    assert (r.status_code, r.json()["backup"], r.json()["status"]) == (200, "attention", "ok")


async def test_una_critica_fuera_de_healthy_baja_a_503(settings_prueba: Settings) -> None:
    async with _cliente(settings_prueba) as c:
        register_health_check(
            "migraciones",
            Contador("mismatch"),
            critical=True,
            allowed={"ok", "mismatch", "unknown"},
            healthy={"ok"},
        )
        r = await c.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["migraciones"] == "mismatch"


async def test_una_critica_dentro_de_healthy_mantiene_el_200(settings_prueba: Settings) -> None:
    async with _cliente(settings_prueba) as c:
        register_health_check(
            "migraciones",
            Contador("ahead"),
            critical=True,
            allowed={"ok", "ahead", "unknown"},
            healthy={"ok", "ahead"},
        )
        r = await c.get("/health")
    assert (r.status_code, r.json()["status"]) == (200, "ok")


async def test_una_informativa_en_attention_no_baja_el_200(settings_prueba: Settings) -> None:
    async with _cliente(settings_prueba) as c:
        _registrar_backup(Contador("attention"))
        r = await c.get("/health")
    assert (r.status_code, r.json()["status"]) == (200, "ok")


async def test_dos_peticiones_seguidas_ejecutan_el_check_una_vez(
    settings_prueba: Settings, reloj: FrozenClock
) -> None:
    contador = Contador()
    async with _cliente(settings_prueba) as c:
        _registrar_backup(contador)
        await c.get("/health")
        await c.get("/api/v1/health")
    assert contador.llamadas == 1


async def test_a_los_29_segundos_sigue_cacheado_y_a_los_31_se_vuelve_a_ejecutar(
    settings_prueba: Settings, reloj: FrozenClock
) -> None:
    contador = Contador()
    async with _cliente(settings_prueba) as c:
        _registrar_backup(contador)
        await c.get("/health")
        reloj.set(T0 + timedelta(seconds=29))
        await c.get("/health")
        assert contador.llamadas == 1
        reloj.set(T0 + timedelta(seconds=31))
        await c.get("/health")
        assert contador.llamadas == 2
        await c.get("/health")
        assert contador.llamadas == 2


async def test_peticiones_concurrentes_ejecutan_el_check_una_sola_vez(
    settings_prueba: Settings, reloj: FrozenClock
) -> None:
    contador = Contador(demora_s=0.05)
    async with _cliente(settings_prueba) as c:
        _registrar_backup(contador)
        respuestas = await asyncio.gather(*(c.get("/health") for _ in range(8)))
    assert contador.llamadas == 1
    assert {r.json()["backup"] for r in respuestas} == {"ok"}


async def test_clear_health_cache_reinicia_la_cache(
    settings_prueba: Settings, reloj: FrozenClock
) -> None:
    contador = Contador()
    async with _cliente(settings_prueba) as c:
        _registrar_backup(contador)
        await c.get("/health")
        clear_health_cache()
        await c.get("/health")
    assert contador.llamadas == 2


async def test_un_check_sin_ttl_no_se_cachea(settings_prueba: Settings, reloj: FrozenClock) -> None:
    contador = Contador()
    async with _cliente(settings_prueba) as c:
        register_health_check("sin_ttl", contador, critical=False)
        await c.get("/health")
        await c.get("/health")
    assert contador.llamadas == 2


async def test_el_check_db_se_cachea_2_segundos(
    settings_prueba: Settings, reloj: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = get_engine
    llamadas = 0

    def contado() -> AsyncEngine:
        nonlocal llamadas
        llamadas += 1
        return real()

    async with _cliente(settings_prueba) as c:
        monkeypatch.setattr(health, "get_engine", contado)
        await c.get("/health")
        await c.get("/health")
        assert llamadas == 1
        reloj.set(T0 + timedelta(seconds=3))
        await c.get("/health")
        assert llamadas == 2


async def test_una_comprobacion_que_lanza_es_unknown_y_el_cuerpo_no_filtra_nada(
    settings_prueba: Settings,
) -> None:
    async def rota() -> str:
        raise RuntimeError("ruta /data/backups/apex-20261021-070000-db.dump.age")

    async with _cliente(settings_prueba) as c:
        register_health_check("backup", rota, critical=False, allowed=PUBLICOS, healthy={"ok"})
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["backup"] == "unknown"
    assert "/data/backups" not in r.text
    assert "apex-2026" not in r.text
