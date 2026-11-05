"""Puerta de Telegram por `channels.telegram.enabled` (S5-V11c; S5-D265d). # Rojo V11c

Contrato que fija el Rojo:
- `alerts_telegram.set_enabled_gate(gate)` registra una puerta async `() -> bool` (con `None` la
  quita) y `get_enabled_gate()` la devuelve. Con la puerta en `False` el sink NO llama a `httpx` y
  suma uno a `sink.skipped`; con `True`, o sin puerta registrada (compatibilidad), envía.
- `settings.service.telegram_enabled_gate(session_factory, ttl_s=30)`: lee
  `channels.telegram.enabled` en una sesión propia (sin fila = apagado) y cachea el valor 30 s
  con el reloj (`FrozenClock` en las pruebas).
- `main.py` (lifespan) y `worker/runtime.py` (`worker_runtime`) registran la puerta; `core` nunca
  importa `app.modules` (la composición es de esas raíces).
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import alerts, alerts_telegram
from app.core.alerts_telegram import TelegramAlertSink, get_enabled_gate, set_enabled_gate
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.main import create_app
from app.modules.settings import service as settings_service
from app.worker import runtime
from tests.core._canales_apoyo import CHAT_ID, TOKEN_BOT, TelegramFalso, instalar_telegram
from tests.notifications._apoyo_avisos import ajustar_canales

FRONT = "https://gym.ejemplo.test"


@pytest.fixture(autouse=True)
def aislar() -> Iterator[None]:
    foto = list(alerts._sinks)
    alerts._sinks[:] = []
    set_enabled_gate(None)
    try:
        yield
    finally:
        alerts._sinks[:] = foto
        set_enabled_gate(None)


@pytest.fixture
def telegram_transport(monkeypatch: pytest.MonkeyPatch) -> TelegramFalso:
    return instalar_telegram(monkeypatch)


def _sink() -> TelegramAlertSink:
    return TelegramAlertSink(SecretStr(TOKEN_BOT), CHAT_ID, timeout_s=10.0, front_base_url=FRONT)


def _puerta(valor: bool) -> Any:
    async def puerta() -> bool:
        return valor

    return puerta


# El sink ---------------------------------------------------------------------------------------


async def test_con_la_puerta_en_false_no_llama_a_httpx_y_cuenta_skipped(
    telegram_transport: TelegramFalso,
) -> None:
    set_enabled_gate(_puerta(False))
    sink = _sink()

    sink.send("crypto_sealed", {})
    await sink.flush()

    assert telegram_transport.peticiones == [] and telegram_transport.clientes == []
    assert sink.skipped == 1 and sink.dropped == 0


async def test_con_la_puerta_en_true_envia_y_no_cuenta_skipped(
    telegram_transport: TelegramFalso,
) -> None:
    set_enabled_gate(_puerta(True))
    sink = _sink()

    sink.send("crypto_sealed", {})
    await sink.flush()

    assert len(telegram_transport.peticiones) == 1
    assert sink.skipped == 0


async def test_sin_puerta_registrada_el_sink_envia(telegram_transport: TelegramFalso) -> None:
    assert get_enabled_gate() is None
    sink = _sink()

    sink.send("crypto_sealed", {})
    await sink.flush()

    assert len(telegram_transport.peticiones) == 1 and sink.skipped == 0


async def test_quitar_la_puerta_con_none_restablece_el_envio(
    telegram_transport: TelegramFalso,
) -> None:
    set_enabled_gate(_puerta(False))
    set_enabled_gate(None)
    sink = _sink()

    sink.send("crypto_sealed", {})
    await sink.flush()

    assert len(telegram_transport.peticiones) == 1


async def test_una_puerta_que_falla_no_rompe_a_quien_alerta(
    telegram_transport: TelegramFalso,
) -> None:
    async def rota() -> bool:
        raise RuntimeError("base caída")

    set_enabled_gate(rota)
    sink = _sink()

    sink.send("crypto_sealed", {})
    await sink.flush()  # no propaga

    assert sink.skipped + len(telegram_transport.peticiones) == 1


def test_core_no_importa_modulos_para_la_puerta() -> None:
    fuente = inspect.getsource(alerts_telegram)
    assert "app.modules" not in fuente


# La puerta de settings -------------------------------------------------------------------------


def _fabrica(session: AsyncSession) -> Any:
    @asynccontextmanager
    async def abrir() -> AsyncIterator[AsyncSession]:
        yield session

    return abrir


@pytest.mark.usefixtures("reloj")
async def test_sin_fila_de_channels_la_puerta_dice_apagado(session: AsyncSession) -> None:
    puerta = settings_service.telegram_enabled_gate(_fabrica(session))

    assert await puerta() is False


@pytest.mark.usefixtures("reloj")
async def test_con_telegram_encendido_la_puerta_dice_encendido(session: AsyncSession) -> None:
    await ajustar_canales(session, telegram=True)
    puerta = settings_service.telegram_enabled_gate(_fabrica(session))

    assert await puerta() is True


async def test_la_puerta_cachea_30_segundos_con_el_reloj(
    session: AsyncSession, reloj: FrozenClock
) -> None:
    await ajustar_canales(session, telegram=True)
    puerta = settings_service.telegram_enabled_gate(_fabrica(session))
    assert await puerta() is True

    await ajustar_canales(session, telegram=False)
    reloj.set(reloj.now_utc() + timedelta(seconds=29))
    dentro = await puerta()
    reloj.set(reloj.now_utc() + timedelta(seconds=2))
    fuera = await puerta()

    assert dentro is True, "dentro de los 30 s se sirve el valor en caché"
    assert fuera is False, "pasados los 30 s se vuelve a leer"


async def test_con_la_base_caida_la_puerta_abre_y_cachea_el_fallo_un_ttl(
    reloj: FrozenClock, caplog: pytest.LogCaptureFixture
) -> None:
    llamadas = 0

    @asynccontextmanager
    async def caida() -> AsyncIterator[AsyncSession]:
        nonlocal llamadas
        llamadas += 1
        raise RuntimeError("base caída")
        yield  # pragma: no cover

    puerta = settings_service.telegram_enabled_gate(caida)  # type: ignore[arg-type]

    with caplog.at_level("WARNING", logger="app.settings"):
        primera = await puerta()
        segunda = await puerta()

    assert primera is True and segunda is True
    assert llamadas == 1
    assert len([r for r in caplog.records if "telegram" in r.getMessage()]) == 1
    reloj.set(reloj.now_utc() + timedelta(seconds=31))
    await puerta()
    assert llamadas == 2


# Cableado --------------------------------------------------------------------------------------


async def test_el_lifespan_de_main_registra_la_puerta(settings_prueba: Settings) -> None:
    app = create_app(settings_prueba, run_migrations_on_startup=False)

    async with app.router.lifespan_context(app):
        assert get_enabled_gate() is not None


async def test_worker_runtime_registra_la_puerta(settings_prueba: Settings) -> None:
    async with runtime.worker_runtime(settings_prueba):
        assert get_enabled_gate() is not None
