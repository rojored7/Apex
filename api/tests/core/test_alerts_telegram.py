"""`core/alerts_telegram.py` (S5-B4; S5-D29, S5-D58, M-8). Rojo B4.

Con `instalar_telegram` (`httpx.MockTransport` en lugar del cliente real): `render_message` pura,
en español, solo enteros y nombres de job, sin nombres de personas y con el enlace a `/avisos/hoy`
solo en `notify_summary`; el POST a `{api_base}/bot{token}/sendMessage` sin `parse_mode`; `send`
síncrono que agenda una tarea y `flush` que espera las pendientes; la tarea atrapa todo y registra
solo el tipo de la excepción (la URL lleva el token); `register_from_settings` pide token y chat.
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.core import alerts, alerts_telegram
from app.core.alerts import alert
from app.core.alerts_telegram import (
    TelegramAlertSink,
    flush,
    register_from_settings,
    render_message,
)
from app.core.clock import FrozenClock, reset_clock, set_clock
from tests.core._canales_apoyo import (
    CHAT_ID,
    TOKEN_BOT,
    TelegramFalso,
    instalar_telegram,
    settings_canales,
)

FRONT = "https://gym.ejemplo.test"
RESUMEN = {"generados": 12, "enviados": 9, "fallidos": 2, "omitidos": 1, "pendientes": 3}


@pytest.fixture(autouse=True)
def sinks_aislados() -> Iterator[None]:
    foto = list(alerts._sinks)
    alerts._sinks[:] = []
    try:
        yield
    finally:
        alerts._sinks[:] = foto


@pytest.fixture
def telegram_transport(monkeypatch: pytest.MonkeyPatch) -> TelegramFalso:
    return instalar_telegram(monkeypatch)


def _sink(**cambios: Any) -> TelegramAlertSink:
    base: dict[str, Any] = {"timeout_s": 10.0, "front_base_url": FRONT}
    return TelegramAlertSink(SecretStr(TOKEN_BOT), CHAT_ID, **{**base, **cambios})


def _cuerpo(peticion: httpx.Request) -> dict[str, Any]:
    cuerpo = json.loads(peticion.content)
    assert isinstance(cuerpo, dict)
    return cuerpo


# render_message --------------------------------------------------------------------------------

CASOS: list[tuple[str, dict[str, object], tuple[str, ...]]] = [
    (
        "job_failed",
        {"job": "expirations", "result": "error", "attempts": 3, "run_date": "2026-11-05"},
        ("expirations",),
    ),
    ("backup_unhealthy", {}, ("respaldo",)),
    ("crypto_sealed", {}, ("custodio", "sellad")),
    ("crypto_recovered", {}, ("recuper",)),
    ("notify_summary", RESUMEN, ("aviso",)),
]


@pytest.mark.parametrize(("codigo", "contexto", "palabras"), CASOS, ids=[c[0] for c in CASOS])
def test_render_message_esta_en_espanol_y_dice_de_que_se_trata(
    codigo: str, contexto: dict[str, object], palabras: tuple[str, ...]
) -> None:
    texto = render_message(codigo, contexto, FRONT)

    assert isinstance(texto, str) and 0 < len(texto) <= 4096
    assert any(p in texto.casefold() for p in palabras), texto


def test_render_message_distingue_los_cinco_codigos() -> None:
    textos = {c: render_message(c, ctx, FRONT) for c, ctx, _ in CASOS}

    assert len(set(textos.values())) == len(CASOS)


def test_job_failed_lleva_el_job_y_los_intentos_en_enteros() -> None:
    texto = render_message("job_failed", {"job": "expirations", "attempts": 3}, FRONT)

    assert "expirations" in texto and "3" in texto


def test_notify_summary_lleva_los_cinco_conteos_y_el_enlace_a_avisos_hoy() -> None:
    texto = render_message("notify_summary", RESUMEN, FRONT)

    for conteo in RESUMEN.values():
        assert str(conteo) in texto
    assert f"{FRONT}/avisos/hoy" in texto


def test_el_enlace_no_duplica_la_barra_si_la_base_termina_en_barra() -> None:
    texto = render_message("notify_summary", RESUMEN, FRONT + "/")

    assert f"{FRONT}/avisos/hoy" in texto
    assert "//avisos" not in texto


@pytest.mark.parametrize(
    "codigo", ["job_failed", "backup_unhealthy", "crypto_sealed", "crypto_recovered"]
)
def test_solo_el_resumen_lleva_enlace(codigo: str) -> None:
    contexto = dict(CASOS[0][1]) if codigo == "job_failed" else {}

    assert "/avisos/hoy" not in render_message(codigo, contexto, FRONT)


def test_render_message_nunca_escribe_nombres_ni_claves_ajenas() -> None:
    sucio = {
        **RESUMEN,
        "nombre": "Laura Gómez",
        "documento": "1020304417",
        "email": "laura@correo.test",
    }

    texto = render_message("notify_summary", sucio, FRONT)

    for dato in ("Laura", "Gómez", "1020304417", "laura@correo.test"):
        assert dato not in texto


def test_render_message_es_pura() -> None:
    primero = render_message("notify_summary", RESUMEN, FRONT)

    assert render_message("notify_summary", RESUMEN, FRONT) == primero
    assert RESUMEN == {
        "generados": 12,
        "enviados": 9,
        "fallidos": 2,
        "omitidos": 1,
        "pendientes": 3,
    }


# Envío -----------------------------------------------------------------------------------------


async def test_send_agenda_la_tarea_y_flush_la_espera(telegram_transport: TelegramFalso) -> None:
    sink = _sink()

    sink.send("crypto_sealed", {})
    assert telegram_transport.peticiones == [], "send es síncrono: no espera a la red"
    await sink.flush()

    [peticion] = telegram_transport.peticiones
    assert peticion.method == "POST"
    assert peticion.url.path == f"/bot{TOKEN_BOT}/sendMessage"
    assert (peticion.url.scheme, peticion.url.host) == ("https", "api.telegram.org")
    cuerpo = _cuerpo(peticion)
    assert cuerpo["chat_id"] == CHAT_ID
    assert cuerpo["text"] == render_message("crypto_sealed", {}, FRONT)


async def test_el_cuerpo_no_trae_parse_mode(telegram_transport: TelegramFalso) -> None:
    sink = _sink()

    sink.send("notify_summary", RESUMEN)
    await sink.flush()

    cuerpo = _cuerpo(telegram_transport.peticiones[0])
    assert "parse_mode" not in cuerpo
    assert set(cuerpo) <= {"chat_id", "text", "disable_web_page_preview"}


async def test_usa_la_base_configurada_y_el_timeout(telegram_transport: TelegramFalso) -> None:
    sink = _sink(timeout_s=4.5, api_base="http://telegram-fake:8081")

    sink.send("crypto_recovered", {})
    await sink.flush()

    peticion = telegram_transport.peticiones[0]
    assert (peticion.url.scheme, peticion.url.host, peticion.url.port) == (
        "http",
        "telegram-fake",
        8081,
    )
    assert peticion.url.path == f"/bot{TOKEN_BOT}/sendMessage"
    [cliente] = telegram_transport.clientes
    assert cliente.get("timeout") == 4.5
    assert cliente.get("follow_redirects", False) is False


async def test_flush_espera_a_las_pendientes_y_sin_pendientes_vuelve_al_instante(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    liberar = asyncio.Event()

    async def lento(peticion: httpx.Request) -> httpx.Response:
        await liberar.wait()
        return httpx.Response(200, json={"ok": True})

    falso = instalar_telegram(monkeypatch, lento)
    sink = _sink()
    await asyncio.wait_for(sink.flush(), timeout=1)

    sink.send("crypto_sealed", {})
    espera = asyncio.create_task(sink.flush())
    await asyncio.sleep(0.05)
    assert not espera.done(), "flush debe esperar al envío pendiente"
    liberar.set()
    await asyncio.wait_for(espera, timeout=1)

    assert len(falso.peticiones) == 1


# La tarea atrapa todo (M-8) ---------------------------------------------------------------------


def _salida(registros: list[logging.LogRecord]) -> str:
    return " ".join(r.getMessage() + " " + str(vars(r)) for r in registros)


@pytest.mark.parametrize(
    "fallo",
    [
        httpx.ConnectError(
            f"All connection attempts failed: https://api.telegram.org/bot{TOKEN_BOT}/sendMessage"
        ),
        httpx.ReadTimeout(f"timeout en bot{TOKEN_BOT}"),
        RuntimeError(f"token {TOKEN_BOT} en el mensaje"),
    ],
    ids=["connect", "timeout", "runtime"],
)
async def test_un_fallo_de_red_no_propaga_y_el_log_lleva_solo_el_tipo(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, fallo: Exception
) -> None:
    caplog.set_level(logging.DEBUG)

    def roto(peticion: httpx.Request) -> httpx.Response:
        raise fallo

    instalar_telegram(monkeypatch, roto)
    sink = _sink()

    sink.send("job_failed", {"job": "expirations"})
    await sink.flush()

    texto = _salida(caplog.records)
    assert type(fallo).__name__ in texto, "el log debe decir el tipo de la excepción"
    assert TOKEN_BOT not in texto and "AAH-token" not in texto and "123456" not in texto
    assert "api.telegram.org/bot" not in texto
    assert all(r.exc_info is None and r.exc_text is None for r in caplog.records)


async def test_una_respuesta_de_error_con_el_token_en_el_cuerpo_no_llega_al_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    def error_401(peticion: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"Unauthorized: bot{TOKEN_BOT}")

    instalar_telegram(monkeypatch, error_401)
    sink = _sink()

    sink.send("crypto_sealed", {})
    await sink.flush()

    assert TOKEN_BOT not in _salida(caplog.records)
    assert "AAH-token" not in _salida(caplog.records)


async def test_una_tarea_fallida_que_nadie_espera_no_deja_task_exception_never_retrieved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sin_recoger: list[dict[str, Any]] = []
    asyncio.get_running_loop().set_exception_handler(lambda _bucle, ctx: sin_recoger.append(ctx))

    def roto(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"bot{TOKEN_BOT}")

    instalar_telegram(monkeypatch, roto)
    sink = _sink()

    sink.send("crypto_sealed", {})
    await asyncio.sleep(0.05)
    del sink
    gc.collect()
    await asyncio.sleep(0)

    assert sin_recoger == []


# Registro -------------------------------------------------------------------------------------


def _sinks_de_telegram() -> list[TelegramAlertSink]:
    return [s for s in alerts._sinks if isinstance(s, TelegramAlertSink)]


def test_register_from_settings_registra_con_token_y_chat() -> None:
    config = settings_canales(TELEGRAM_BOT_TOKEN=TOKEN_BOT, TELEGRAM_CHAT_ID=CHAT_ID)

    assert register_from_settings(config) is True
    assert len(_sinks_de_telegram()) == 1


@pytest.mark.parametrize(
    "datos",
    [{}, {"TELEGRAM_BOT_TOKEN": TOKEN_BOT}, {"TELEGRAM_CHAT_ID": CHAT_ID}],
    ids=["ninguno", "solo_token", "solo_chat"],
)
def test_register_from_settings_no_registra_sin_token_o_sin_chat(datos: dict[str, str]) -> None:
    assert register_from_settings(settings_canales(**datos)) is False
    assert _sinks_de_telegram() == []


async def test_el_sink_registrado_usa_la_base_el_timeout_y_el_front_de_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    falso = instalar_telegram(monkeypatch)
    config = settings_canales(
        TELEGRAM_BOT_TOKEN=TOKEN_BOT,
        TELEGRAM_CHAT_ID=CHAT_ID,
        TELEGRAM_API_BASE="http://telegram-fake:8081",
        NOTIFY_NET_TIMEOUT_S=6,
    )
    assert register_from_settings(config) is True

    alert("notify_summary", **RESUMEN)
    await flush()

    [peticion] = falso.peticiones
    assert peticion.url.host == "telegram-fake" and peticion.url.port == 8081
    assert f"{FRONT}/avisos/hoy" in _cuerpo(peticion)["text"]
    assert falso.clientes[0].get("timeout") == 6


async def test_flush_del_modulo_sin_sink_registrado_no_hace_nada() -> None:
    await asyncio.wait_for(alerts_telegram.flush(), timeout=1)


async def test_alert_llega_al_sink_sin_bloquear_a_quien_alerta(
    telegram_transport: TelegramFalso,
) -> None:
    alerts.register_sink(_sink())

    alert("job_failed", job="expirations", result="error", attempts=3)
    assert telegram_transport.peticiones == []
    await flush()

    assert len(telegram_transport.peticiones) == 1


# Cola acotada y deduplicación (revisión de seguridad, MEDIUM 1; S5-D206) ----------------------


@pytest.fixture
def reloj() -> Iterator[FrozenClock]:
    reloj = FrozenClock(datetime(2026, 11, 5, 15, 0, tzinfo=UTC))
    token = set_clock(reloj)
    try:
        yield reloj
    finally:
        reset_clock(token)


async def test_la_alerta_21_con_la_cola_llena_se_descarta_con_una_linea_fija(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, reloj: FrozenClock
) -> None:
    caplog.set_level(logging.DEBUG)
    liberar = asyncio.Event()

    async def lento(peticion: httpx.Request) -> httpx.Response:
        await liberar.wait()
        return httpx.Response(200, json={"ok": True})

    falso = instalar_telegram(monkeypatch, lento)
    sink = _sink()
    assert alerts_telegram.MAX_PENDING == 20

    for n in range(21):
        sink.send("job_failed", {"job": f"job{n}", "attempts": 3})
    liberar.set()
    await sink.flush()

    assert len(falso.peticiones) == 20
    assert sink.dropped == 1
    lineas = [r.getMessage() for r in caplog.records if "cola llena" in r.getMessage()]
    assert lineas == ["alerta de telegram descartada: cola llena"]
    assert "job20" not in _salida(caplog.records)


async def test_la_misma_alerta_dos_veces_en_10_segundos_crea_una_sola_tarea(
    telegram_transport: TelegramFalso, reloj: FrozenClock
) -> None:
    sink = _sink()

    sink.send("crypto_sealed", {})
    reloj.set(reloj.now_utc() + timedelta(seconds=10))
    sink.send("crypto_sealed", {})
    await sink.flush()

    assert len(telegram_transport.peticiones) == 1


async def test_pasada_la_ventana_de_60_segundos_la_alerta_vuelve_a_salir(
    telegram_transport: TelegramFalso, reloj: FrozenClock
) -> None:
    sink = _sink()

    sink.send("crypto_sealed", {})
    reloj.set(reloj.now_utc() + timedelta(seconds=61))
    sink.send("crypto_sealed", {})
    await sink.flush()

    assert len(telegram_transport.peticiones) == 2


async def test_codigos_distintos_o_jobs_distintos_no_se_deduplican(
    telegram_transport: TelegramFalso, reloj: FrozenClock
) -> None:
    sink = _sink()

    sink.send("crypto_sealed", {})
    sink.send("crypto_recovered", {})
    sink.send("job_failed", {"job": "expirations"})
    sink.send("job_failed", {"job": "notify"})
    await sink.flush()

    assert len(telegram_transport.peticiones) == 4


async def test_flush_espera_solo_las_tareas_vivas_tras_descartar(
    telegram_transport: TelegramFalso, reloj: FrozenClock
) -> None:
    sink = _sink()
    sink.send("crypto_sealed", {})
    sink.send("crypto_sealed", {})  # deduplicada

    await asyncio.wait_for(sink.flush(), timeout=1)

    assert len(telegram_transport.peticiones) == 1
    await asyncio.wait_for(sink.flush(), timeout=1)


async def test_el_cliente_no_hereda_el_proxy_del_entorno(
    telegram_transport: TelegramFalso,
) -> None:
    sink = _sink()

    sink.send("crypto_sealed", {})
    await sink.flush()

    [cliente] = telegram_transport.clientes
    assert cliente.get("trust_env") is False


def test_register_from_settings_reemplaza_sin_tocar_la_lista_privada() -> None:
    config = settings_canales(TELEGRAM_BOT_TOKEN=TOKEN_BOT, TELEGRAM_CHAT_ID=CHAT_ID)

    register_from_settings(config)
    register_from_settings(config)

    assert len(_sinks_de_telegram()) == 1
    fuente = Path(alerts_telegram.__file__).read_text(encoding="utf-8")
    assert "_sinks" not in fuente
