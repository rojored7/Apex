"""Candado, tarea en segundo plano y plazos de la verificación (S4A-B3; S4A-D13, S4A-D44 = H-2).

Datos con commit real (`fabrica_confirmada`): la tarea 202 abre su propia sesión y debe ver la
cadena. El engine global del api es `motor_del_api` (`DB_IDLE_IN_TX_TIMEOUT_MS = 2000`, E10). Para
alargar una corrida se baja `VERIFY_BATCH_SIZE` a 5 y se reemplaza `_pause_between_batches` (el
`asyncio.sleep(0)` entre lotes de `core/audit_verify.py`) por una espera de 1 s: 30 filas son 6
lotes y unos 5 s, más que los 2 s de `idle_in_transaction_session_timeout`.

Contrato fijado:
- `verify` lanza `VerificationRunning` si otra conexión tiene `4_270_003` (antes de leer nada);
- por encima de `SYNC_VERIFY_MAX_ROWS` devuelve `Started(last)`, la tarea queda en
  `_BACKGROUND_TASKS` hasta terminar, deja la fila y suelta el candado (también si falla o vence,
  sin dejar fila y registrando solo el tipo en `error_type`);
- la conexión del candado es `AUTOCOMMIT` y se invalida al soltarlo, aunque el `unlock` falle
  (`release_verify_lock` nunca lanza);
- `cancel_background_verifications()` cancela y espera; el `shutdown` del lifespan la llama.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app import main
from app.core import audit_verify
from app.core.audit_verify import AuditVerification
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.audit import verify as verify_mod
from app.modules.audit.exceptions import VerificationRunning
from tests.audit._apoyo import EspiaDeConexiones, candado_libre
from tests.audit.conftest import audit_service
from tests.factories.audit_chain import make_audit_chain

Fabrica = async_sessionmaker[AsyncSession]
POR = SYSTEM_USER_ID
DOCUMENTO = "1020304417"

pytestmark = pytest.mark.usefixtures("motor_del_api")


async def _cadena(fabrica: Fabrica, n: int = 30) -> int:
    async with fabrica() as sesion:
        return await make_audit_chain(sesion, n)


async def _verify(fabrica: Fabrica, by: UUID = POR) -> verify_mod.Finished | verify_mod.Started:
    with actor_scope(by):
        async with fabrica() as sesion, sesion.begin():
            return await audit_service.verify(sesion, by=by)


async def _filas(fabrica: Fabrica) -> list[AuditVerification]:
    async with fabrica() as sesion:
        return list(await sesion.scalars(select(AuditVerification)))


async def _esperar_tareas(limite_s: float = 30) -> list[Any]:
    tareas = list(verify_mod._BACKGROUND_TASKS)
    assert len(tareas) == 1, tareas
    return await asyncio.wait_for(asyncio.gather(*tareas, return_exceptions=True), limite_s)


def _corrida_larga(monkeypatch: pytest.MonkeyPatch, espera_s: float = 1.0) -> None:
    monkeypatch.setattr(audit_verify, "VERIFY_BATCH_SIZE", 5)

    async def pausa() -> None:
        await asyncio.sleep(espera_s)

    monkeypatch.setattr(audit_verify, "_pause_between_batches", pausa)


def _tipos_registrados(caplog: pytest.LogCaptureFixture) -> set[str]:
    return {str(getattr(r, "error_type", "")) for r in caplog.records} - {""}


# Candado ----------------------------------------------------------------------------------------


@pytest.mark.usefixtures("candado_tomado")
async def test_con_el_candado_tomado_verify_lanza_verification_running(
    fabrica_confirmada: Fabrica,
) -> None:
    await _cadena(fabrica_confirmada, 5)

    with pytest.raises(VerificationRunning) as excinfo:
        await _verify(fabrica_confirmada)

    assert (excinfo.value.status, excinfo.value.code) == (409, "verification_running")
    assert await _filas(fabrica_confirmada) == []


async def test_sincrona_la_conexion_del_candado_es_autocommit_e_invalidada(
    fabrica_confirmada: Fabrica, espia_de_conexiones: EspiaDeConexiones, settings_prueba: Settings
) -> None:
    await _cadena(fabrica_confirmada, 5)

    salida = await _verify(fabrica_confirmada)

    assert isinstance(salida, verify_mod.Finished)
    assert salida.result.ok is True
    assert espia_de_conexiones.autocommit_invalidadas(), espia_de_conexiones
    assert await candado_libre(settings_prueba.DATABASE_URL.get_secret_value())


# Segundo plano -----------------------------------------------------------------------------------


@pytest.mark.usefixtures("umbral_bajo")
async def test_con_el_umbral_bajo_devuelve_started_y_la_tarea_deja_la_fila(
    fabrica_confirmada: Fabrica, settings_prueba: Settings
) -> None:
    await _cadena(fabrica_confirmada, 30)

    salida = await _verify(fabrica_confirmada)

    assert isinstance(salida, verify_mod.Started)
    assert salida.last is None
    resultados = await _esperar_tareas()
    assert resultados == [None]
    [fila] = await _filas(fabrica_confirmada)
    assert (fila.ok, fila.source, fila.triggered_by) == (True, "api", POR)
    assert verify_mod._BACKGROUND_TASKS == set()
    assert await candado_libre(settings_prueba.DATABASE_URL.get_secret_value())


@pytest.mark.usefixtures("umbral_bajo")
async def test_si_la_tarea_falla_no_deja_fila_suelta_el_candado_y_registra_solo_el_tipo(
    fabrica_confirmada: Fabrica,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(audit_verify, "VERIFY_BATCH_SIZE", 5)

    async def falla() -> None:
        raise RuntimeError(f"documento {DOCUMENTO} en el mensaje")

    monkeypatch.setattr(audit_verify, "_pause_between_batches", falla)
    await _cadena(fabrica_confirmada, 30)
    caplog.set_level(logging.INFO)

    salida = await _verify(fabrica_confirmada)
    await _esperar_tareas()

    assert isinstance(salida, verify_mod.Started)
    assert await _filas(fabrica_confirmada) == []
    assert await candado_libre(settings_prueba.DATABASE_URL.get_secret_value())
    assert "RuntimeError" in _tipos_registrados(caplog)
    assert DOCUMENTO not in caplog.text
    assert all(r.exc_info is None for r in caplog.records if r.name.startswith("app"))
    assert verify_mod._BACKGROUND_TASKS == set()


@pytest.mark.usefixtures("umbral_bajo")
async def test_h2_el_candado_sigue_tomado_toda_la_corrida_aunque_pase_el_idle_timeout(
    fabrica_confirmada: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H-2: la conexión del candado pasa más de 2 s sin transacción abierta; si estuviera "idle in
    transaction" PostgreSQL la cortaría y otro `verify` obtendría el candado."""
    _corrida_larga(monkeypatch)
    url = settings_prueba.DATABASE_URL.get_secret_value()
    await _cadena(fabrica_confirmada, 30)

    salida = await _verify(fabrica_confirmada)
    assert isinstance(salida, verify_mod.Started)
    [tarea] = list(verify_mod._BACKGROUND_TASKS)
    comprobaciones = 0
    while not tarea.done():
        with pytest.raises(VerificationRunning):
            await _verify(fabrica_confirmada)
        assert await candado_libre(url) is False
        comprobaciones += 1
        await asyncio.sleep(0.5)

    assert comprobaciones >= 6, comprobaciones  # más de 3 s con el candado tomado
    assert tarea.exception() is None
    [fila] = await _filas(fabrica_confirmada)
    assert fila.ok is True
    assert await candado_libre(url)


class ConexionQueFallaAlLiberar:
    """La conexión real del candado, salvo que toda sentencia nueva falla (el `unlock`)."""

    def __init__(self, real: AsyncConnection) -> None:
        self._real = real

    async def _falla(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("el unlock falló")

    execute = scalar = exec_driver_sql = _falla

    def __getattr__(self, nombre: str) -> Any:
        return getattr(self._real, nombre)


def _adquirir_con_unlock_roto(original: Callable[[], Any]) -> Callable[[], Any]:
    async def adquirir() -> Any:
        conn = await original()
        return None if conn is None else ConexionQueFallaAlLiberar(conn)

    return adquirir


async def test_si_el_unlock_falla_la_conexion_se_invalida_y_el_candado_queda_libre(
    fabrica_confirmada: Fabrica,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    espia_de_conexiones: EspiaDeConexiones,
) -> None:
    monkeypatch.setattr(
        verify_mod, "acquire_verify_lock", _adquirir_con_unlock_roto(verify_mod.acquire_verify_lock)
    )
    await _cadena(fabrica_confirmada, 5)

    salida = await _verify(fabrica_confirmada)

    assert isinstance(salida, verify_mod.Finished) and salida.result.ok is True
    assert espia_de_conexiones.invalidadas, "la conexión del candado debe invalidarse"
    assert await candado_libre(settings_prueba.DATABASE_URL.get_secret_value())


async def test_release_verify_lock_nunca_lanza_e_invalida(
    settings_prueba: Settings, espia_de_conexiones: EspiaDeConexiones
) -> None:
    conn = await audit_service.acquire_verify_lock()
    assert conn is not None
    assert await candado_libre(settings_prueba.DATABASE_URL.get_secret_value()) is False

    await audit_service.release_verify_lock(ConexionQueFallaAlLiberar(conn))  # type: ignore[arg-type]

    assert espia_de_conexiones.autocommit_invalidadas()
    assert await candado_libre(settings_prueba.DATABASE_URL.get_secret_value())


@pytest.mark.usefixtures("candado_tomado")
async def test_acquire_verify_lock_devuelve_none_si_otro_lo_tiene() -> None:
    assert await audit_service.acquire_verify_lock() is None


# Plazo y cancelación -----------------------------------------------------------------------------


@pytest.mark.usefixtures("umbral_bajo", "plazo_corto")
async def test_con_plazo_corto_la_tarea_vence_sin_fila_y_suelta_el_candado(
    fabrica_confirmada: Fabrica,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _corrida_larga(monkeypatch)
    await _cadena(fabrica_confirmada, 30)
    caplog.set_level(logging.INFO)

    salida = await _verify(fabrica_confirmada)
    await _esperar_tareas()

    assert isinstance(salida, verify_mod.Started)
    assert await _filas(fabrica_confirmada) == []
    assert await candado_libre(settings_prueba.DATABASE_URL.get_secret_value())
    assert "TimeoutError" in _tipos_registrados(caplog)
    assert verify_mod._BACKGROUND_TASKS == set()


@pytest.mark.usefixtures("umbral_bajo")
async def test_cancel_background_verifications_cancela_y_suelta_el_candado(
    fabrica_confirmada: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _corrida_larga(monkeypatch)
    await _cadena(fabrica_confirmada, 30)
    salida = await _verify(fabrica_confirmada)
    assert isinstance(salida, verify_mod.Started)
    await asyncio.sleep(0.3)
    assert await candado_libre(settings_prueba.DATABASE_URL.get_secret_value()) is False

    await audit_service.cancel_background_verifications()

    assert verify_mod._BACKGROUND_TASKS == set()
    assert await _filas(fabrica_confirmada) == []
    assert await candado_libre(settings_prueba.DATABASE_URL.get_secret_value())


async def test_el_shutdown_del_lifespan_cancela_las_verificaciones(
    settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas: list[int] = []

    async def espia() -> None:
        llamadas.append(1)

    async def arranque_roto(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("arranque roto a propósito")

    monkeypatch.setattr(audit_service, "cancel_background_verifications", espia)
    monkeypatch.setattr(main, "_startup", arranque_roto)
    aplicacion: FastAPI = main.create_app(settings_prueba, run_migrations_on_startup=False)

    with pytest.raises(RuntimeError, match="arranque roto"):
        async with aplicacion.router.lifespan_context(aplicacion):
            pass

    assert llamadas == [1]


# Revisiones de B3 (security-reviewer) -----------------------------------------------------------


async def test_si_la_rama_sincrona_vence_sigue_en_segundo_plano_con_el_candado(
    fabrica_confirmada: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MEDIUM (S4A-D100): la rama síncrona tiene plazo propio (`SYNC_VERIFY_MAX_SECONDS`); si
    vence, revierte su SAVEPOINT (no deja fila a medias) y responde `Started`; la tarea termina con
    el mismo candado y lo suelta."""
    monkeypatch.setattr(verify_mod, "SYNC_VERIFY_MAX_SECONDS", 1)
    _corrida_larga(monkeypatch, espera_s=0.5)
    url = settings_prueba.DATABASE_URL.get_secret_value()
    await _cadena(fabrica_confirmada, 30)

    salida = await _verify(fabrica_confirmada)

    assert isinstance(salida, verify_mod.Started)
    assert salida.last is None
    assert await candado_libre(url) is False  # la tarea lo tiene
    assert await _esperar_tareas() == [None]
    [fila] = await _filas(fabrica_confirmada)
    assert (fila.ok, fila.source) == (True, "api")
    assert await candado_libre(url)
    assert verify_mod._BACKGROUND_TASKS == set()


async def test_una_tarea_cancelada_antes_de_empezar_suelta_e_invalida_el_candado(
    settings_prueba: Settings, espia_de_conexiones: EspiaDeConexiones
) -> None:
    """LOW (S4A-D101): cancelada antes de su primer paso, la tarea nunca corre su `finally`;
    `cancel_background_verifications` suelta e invalida su conexión."""
    url = settings_prueba.DATABASE_URL.get_secret_value()
    conn = await audit_service.acquire_verify_lock()
    assert conn is not None
    verify_mod._start_in_background(conn, POR)  # sin ceder el loop: la tarea no empezó

    await audit_service.cancel_background_verifications()

    assert verify_mod._BACKGROUND_TASKS == set()
    assert verify_mod._TASK_LOCKS == {}
    assert espia_de_conexiones.autocommit_invalidadas()
    assert await candado_libre(url)
