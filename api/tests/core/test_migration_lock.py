"""Dos procesos nunca migran a la vez: lock asesor en env.py (US-020, T5 y T7)."""

from __future__ import annotations

import asyncio
import threading
import time

import asyncpg

from app.core.config import Settings
from app.main import MIGRATION_LOCK_KEY, run_migrations


def _asyncpg_url(settings: Settings) -> str:
    return settings.DATABASE_URL.get_secret_value().replace("postgresql+asyncpg://", "postgresql://", 1)


def _en_hilo(settings: Settings, errores: list[BaseException]) -> threading.Thread:
    def correr() -> None:
        try:
            run_migrations(settings)
        except BaseException as exc:  # noqa: BLE001
            errores.append(exc)

    hilo = threading.Thread(target=correr, daemon=True)
    hilo.start()
    return hilo


def test_dos_migraciones_simultaneas_terminan_sin_error(settings_prueba: Settings) -> None:
    errores: list[BaseException] = []
    hilos = [_en_hilo(settings_prueba, errores), _en_hilo(settings_prueba, errores)]
    for hilo in hilos:
        hilo.join(timeout=60)
        assert not hilo.is_alive()
    assert errores == []

    async def version() -> list[str]:
        conexion = await asyncpg.connect(_asyncpg_url(settings_prueba))
        try:
            return [r["version_num"] for r in await conexion.fetch("SELECT version_num FROM alembic_version")]
        finally:
            await conexion.close()

    assert asyncio.run(version()) == ["0001_core_schemas"]


def test_la_migracion_espera_al_lock_asesor(settings_prueba: Settings) -> None:
    async def con_lock_tomado() -> None:
        conexion = await asyncpg.connect(_asyncpg_url(settings_prueba))
        try:
            await conexion.execute("SELECT pg_advisory_lock($1)", MIGRATION_LOCK_KEY)
            errores: list[BaseException] = []
            hilo = _en_hilo(settings_prueba, errores)
            await asyncio.sleep(1.5)
            assert hilo.is_alive(), "la migración no esperó al lock asesor"
            esperando = await conexion.fetchval(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"
            )
            assert esperando >= 1
            await conexion.execute("SELECT pg_advisory_unlock($1)", MIGRATION_LOCK_KEY)
            inicio = time.perf_counter()
            while hilo.is_alive() and time.perf_counter() - inicio < 30:
                await asyncio.sleep(0.2)
            assert not hilo.is_alive()
            assert errores == []
        finally:
            await conexion.close()

    asyncio.run(con_lock_tomado())
