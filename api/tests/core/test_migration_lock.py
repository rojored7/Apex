"""Dos procesos nunca migran a la vez: lock asesor en env.py (US-020, T5 y T7).

Se usan procesos reales (`python -m alembic`), no hilos: el `alembic.context`
global no es seguro entre hilos del mismo proceso, y en producción la
concurrencia es entre procesos (api, worker, CLI).
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import asyncpg
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import Settings
from app.main import MIGRATION_LOCK_KEY

API_ROOT = Path(__file__).resolve().parents[2]


def _head() -> str:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "migrations"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert head is not None
    return head


def _asyncpg_url(settings: Settings) -> str:
    return settings.DATABASE_URL.get_secret_value().replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


def _alembic(settings: Settings, *args: str) -> subprocess.Popen[str]:
    url = settings.DATABASE_URL.get_secret_value()
    return subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "alembic", "-x", f"url={url}", *args],
        cwd=API_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


async def _version(settings: Settings) -> list[str]:
    conexion = await asyncpg.connect(_asyncpg_url(settings))
    try:
        filas = await conexion.fetch("SELECT version_num FROM alembic_version")
        return [fila["version_num"] for fila in filas]
    finally:
        await conexion.close()


def test_dos_migraciones_simultaneas_terminan_sin_error(settings_prueba: Settings) -> None:
    procesos = [_alembic(settings_prueba, "upgrade", "head") for _ in range(2)]
    salidas = [proceso.communicate(timeout=120)[0] for proceso in procesos]
    assert [proceso.returncode for proceso in procesos] == [0, 0], salidas
    assert asyncio.run(_version(settings_prueba)) == [_head()]


def test_la_migracion_espera_al_lock_asesor(settings_prueba: Settings) -> None:
    async def con_lock_tomado() -> None:
        conexion = await asyncpg.connect(_asyncpg_url(settings_prueba))
        try:
            await conexion.execute("SELECT pg_advisory_lock($1)", MIGRATION_LOCK_KEY)
            proceso = _alembic(settings_prueba, "upgrade", "head")
            esperando = 0
            for _ in range(60):
                await asyncio.sleep(0.5)
                esperando = await conexion.fetchval(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"
                )
                if esperando:
                    break
            assert proceso.poll() is None, "la migración no esperó al lock asesor"
            assert esperando >= 1, "ningún proceso está esperando el lock asesor"
            await conexion.execute("SELECT pg_advisory_unlock($1)", MIGRATION_LOCK_KEY)
            salida, _ = await asyncio.to_thread(proceso.communicate, None, 60)
            assert proceso.returncode == 0, salida
        finally:
            await conexion.close()

    asyncio.run(con_lock_tomado())
