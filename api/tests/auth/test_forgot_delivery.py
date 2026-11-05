"""`POST /auth/forgot` con entrega en segundo plano (S5-B9, US-131; D38, D91, M-7d/e). # Rojo B9

Contrato:
- el router responde 204 como en v0.1 (tras `ratelimit.enforce` y `wait_floor`) y programa
  `BackgroundTasks.add_task(links.forgot_deliver, email, session_factory=..., settings=...)`:
  la búsqueda, el token y el correo corren DESPUÉS de la respuesta, en una sesión propia; el
  tiempo observable no depende de si la cuenta existe (H-2);
- solo una cuenta elegible (viva, activa, no bloqueada) recibe un correo de recuperación con un
  token `reset`; el envío exige SMTP configurado y `channels.email.enabled`;
- un fallo del correo o una excepción no cambian la respuesta; el enlace y el correo nunca llegan
  a un log;
- `forgot_deliver` corre con un semáforo de 4 y una cola de 32; lo que no cabe se descarta con una
  línea de log que solo lleva el tipo.

`service.forgot(email, *, policy)` conserva la semántica de v0.1 (no lee ni escribe); sus pruebas
siguen en `test_reset_forgot.py`.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.security import hash_opaque_token
from app.modules.auth import service
from tests.auth._correos import (
    FORGOT,
    EntornoCorreo,
    entorno_correo,
    habilitar_canal_correo,
    hacer_que_send_mail_lance,
    post_cronometrado,
    token_del_cuerpo,
)
from tests.auth._cuentas import tokens_de
from tests.auth._sesion import politica
from tests.conftest import CrearUsuario, SleeperEspia

MARGEN_S = 0.050
CORRIDAS = 20


@pytest.fixture
async def entorno(
    monkeypatch: pytest.MonkeyPatch,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    sleeper_nulo: SleeperEspia,
) -> EntornoCorreo:
    """SMTP falso, canal de correo habilitado y fábrica de sesiones de la prueba."""
    admin = await usuario_real("admin")
    nuevo = entorno_correo(monkeypatch, api_prueba, session, con_smtp_=True)
    await habilitar_canal_correo(session, admin.id)
    return nuevo


# La cuenta elegible recibe el correo, después de responder ---------------------------------


@pytest.mark.parametrize("rol", ["coach", "admin"])
async def test_una_cuenta_elegible_recibe_el_correo_con_un_token_reset(
    rol: str,
    entorno: EntornoCorreo,
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
) -> None:
    usuario = await usuario_real(rol)

    r = await app_http.post(FORGOT, json={"email": usuario.email})

    assert r.status_code == 204 and r.content == b""
    (mensaje,) = entorno.smtp.mensajes
    assert mensaje["To"] == usuario.email
    token = token_del_cuerpo(mensaje.get_content())
    assert mensaje.get_content().count(f"{entorno.settings.FRONT_BASE_URL}/restablecer/") == 1
    (fila,) = await tokens_de(session, usuario.id)
    assert fila.purpose == "reset" and fila.used_at is None
    assert fila.token_hash == hash_opaque_token(token)


async def test_el_correo_sale_despues_de_enviar_la_respuesta(
    entorno: EntornoCorreo,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
) -> None:
    usuario = await usuario_real("coach")

    estado, _, enviados_al_responder = await post_cronometrado(
        api_prueba, usuario.email, "198.51.100.9", alerta=lambda: len(entorno.smtp.mensajes)
    )

    assert estado == 204
    assert enviados_al_responder == 0, "el correo salió antes de la respuesta (canal de tiempos)"
    assert len(entorno.smtp.mensajes) == 1, "la tarea de fondo no se ejecutó"


async def test_la_normalizacion_del_correo_encuentra_la_cuenta(
    entorno: EntornoCorreo, app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    usuario = await usuario_real("coach")

    r = await app_http.post(FORGOT, json={"email": f"  {usuario.email.upper()} "})

    assert r.status_code == 204
    (mensaje,) = entorno.smtp.mensajes
    assert mensaje["To"] == usuario.email


# Cuentas no elegibles: sin correo y sin rastro -------------------------------------------


@pytest.mark.parametrize(
    "cambios",
    [{"bloqueado": True}, {"activo": False}, {"borrado": True}],
    ids=["bloqueada", "inactiva", "borrada"],
)
async def test_una_cuenta_no_elegible_no_recibe_correo_ni_token(
    cambios: dict[str, Any],
    entorno: EntornoCorreo,
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
) -> None:
    usuario = await usuario_real("coach", **cambios)

    r = await app_http.post(FORGOT, json={"email": usuario.email})

    assert r.status_code == 204
    assert entorno.smtp.mensajes == []
    assert await tokens_de(session, usuario.id) == []


async def test_una_cuenta_pendiente_de_activacion_no_recibe_correo_ni_token(
    entorno: EntornoCorreo,
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
) -> None:
    """S5-D236: la activación la reenvía el admin con `resend_link`, no `forgot`."""
    pendiente = await usuario_real("coach", password=None)

    r = await app_http.post(FORGOT, json={"email": pendiente.email})

    assert r.status_code == 204
    assert entorno.smtp.mensajes == []
    assert await tokens_de(session, pendiente.id) == []


async def test_un_correo_inexistente_no_envia_nada(
    entorno: EntornoCorreo, app_http: AsyncClient
) -> None:
    r = await app_http.post(FORGOT, json={"email": "nadie-fondo@test.apex"})

    assert r.status_code == 204
    assert entorno.smtp.mensajes == []
    assert entorno.smtp.conexiones == []


async def test_existente_e_inexistente_dan_la_misma_respuesta(
    entorno: EntornoCorreo, app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")

    existe = await app_http.post(FORGOT, json={"email": coach.email})
    no_existe = await app_http.post(FORGOT, json={"email": "nadie-igual@test.apex"})

    def sin_variables(r: Any) -> dict[str, str]:
        return {k: v for k, v in r.headers.items() if k.lower() not in {"date", "x-request-id"}}

    assert (existe.status_code, existe.content) == (no_existe.status_code, no_existe.content)
    assert sin_variables(existe) == sin_variables(no_existe)
    assert len(entorno.smtp.mensajes) == 1


# Sin SMTP o con el canal apagado: no se envía --------------------------------------------


async def test_sin_smtp_no_se_envia_ni_se_deja_token(
    monkeypatch: pytest.MonkeyPatch,
    app_http: AsyncClient,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    sleeper_nulo: SleeperEspia,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    entorno = entorno_correo(monkeypatch, api_prueba, session, con_smtp_=False)
    await habilitar_canal_correo(session, admin.id)

    r = await app_http.post(FORGOT, json={"email": coach.email})

    assert r.status_code == 204
    assert entorno.smtp.conexiones == []
    assert await tokens_de(session, coach.id) == []


async def test_con_el_canal_de_correo_apagado_no_se_envia(
    monkeypatch: pytest.MonkeyPatch,
    app_http: AsyncClient,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    sleeper_nulo: SleeperEspia,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    entorno = entorno_correo(monkeypatch, api_prueba, session, con_smtp_=True)
    await habilitar_canal_correo(session, admin.id, habilitado=False)

    r = await app_http.post(FORGOT, json={"email": coach.email})

    assert r.status_code == 204
    assert entorno.smtp.conexiones == []


# Un fallo del correo no cambia la respuesta ----------------------------------------------


async def test_un_fallo_de_smtp_no_cambia_la_respuesta(
    entorno: EntornoCorreo, app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    entorno.smtp.fallo = ConnectionRefusedError("sin servidor")

    r = await app_http.post(FORGOT, json={"email": coach.email})

    assert r.status_code == 204 and r.content == b""
    assert entorno.smtp.conexiones, "debió intentar enviar"


async def test_una_excepcion_del_envio_no_cambia_la_respuesta_ni_filtra_el_enlace(
    entorno: EntornoCorreo,
    monkeypatch: pytest.MonkeyPatch,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """M-7d: se captura TODA excepción y el log lleva solo el tipo."""
    coach = await usuario_real("coach")
    cuerpos = hacer_que_send_mail_lance(monkeypatch)
    caplog.set_level(logging.DEBUG)

    r = await app_http.post(FORGOT, json={"email": coach.email})

    assert r.status_code == 204 and r.content == b""
    assert len(cuerpos) == 1, "send_mail debió llamarse una vez"
    texto = caplog.text + " ".join(str(x.__dict__) for x in caplog.records)
    assert token_del_cuerpo(cuerpos[0]) not in texto
    assert coach.email not in texto.lower()
    assert "RuntimeError" in texto


# Logs -----------------------------------------------------------------------------------


async def test_ni_el_enlace_ni_el_correo_llegan_a_los_logs(
    entorno: EntornoCorreo,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    caplog: pytest.LogCaptureFixture,
) -> None:
    coach = await usuario_real("coach")
    caplog.set_level(logging.DEBUG)

    r = await app_http.post(FORGOT, json={"email": coach.email})
    r2 = await app_http.post(FORGOT, json={"email": "Nadie-Log-Fondo@Test.Apex"})

    assert (r.status_code, r2.status_code) == (204, 204)
    (mensaje,) = entorno.smtp.mensajes
    token = token_del_cuerpo(mensaje.get_content())
    texto = (caplog.text + " ".join(str(x.__dict__) for x in caplog.records)).lower()
    assert token.lower() not in texto
    assert coach.email not in texto
    assert coach.email.split("@")[0] not in texto
    assert "nadie-log-fondo@test.apex" not in texto


# Tiempos (H-2) --------------------------------------------------------------------------


async def test_el_tiempo_hasta_la_respuesta_no_depende_de_si_la_cuenta_existe(
    entorno: EntornoCorreo,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
) -> None:
    """Medianas de 20 corridas dentro de 50 ms. Se mide hasta `http.response.start` (el cliente
    de httpx espera a las tareas de fondo y falsearía la medición). El piso `wait_floor` lo
    anula `sleeper_nulo`: lo que se compara es el trabajo de la petición. Cada petición usa su IP
    (tope de IP) y cada cuenta recibe 4 intentos (tope por cuenta de 5)."""
    cuentas = [(await usuario_real("coach")).email for _ in range(5)]
    sin_cuenta = [f"sin-cuenta-{i}@test.apex" for i in range(5)]
    tiempos: dict[str, list[float]] = {"existe": [], "no_existe": []}
    for i in range(CORRIDAS):
        for clave, grupo in (("existe", cuentas), ("no_existe", sin_cuenta)):
            correo = grupo[i % 5]
            ip = f"198.51.{1 if clave == 'existe' else 2}.{i + 1}"
            estado, segundos, _ = await post_cronometrado(api_prueba, correo, ip)
            assert estado == 204, (clave, i, estado)
            tiempos[clave].append(segundos)

    mediana_existe = statistics.median(tiempos["existe"])
    mediana_no_existe = statistics.median(tiempos["no_existe"])
    assert abs(mediana_existe - mediana_no_existe) <= MARGEN_S, (mediana_existe, mediana_no_existe)
    assert len(entorno.smtp.mensajes) == CORRIDAS, "las cuentas existentes debían recibir correo"


# Cola acotada (M-7e, D91) ---------------------------------------------------------------


async def test_forgot_deliver_limita_a_4_en_vuelo_y_descarta_lo_que_pasa_de_la_cola(
    entorno: EntornoCorreo,
    session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """50 llamadas con la puerta de la sesión cerrada: a lo sumo 4 llegan a abrir sesión (el
    semáforo), a lo más 32 + 4 quedan admitidas y el resto se descarta con una línea de log que
    no lleva correos ni enlaces. Las sesiones se serializan con un candado: la de la prueba es
    una sola."""
    from app.modules.auth import links

    puerta = asyncio.Event()
    candado = asyncio.Lock()
    simultaneas = 0
    pico_cerrada = 0

    async def esperar_puerta() -> None:
        nonlocal simultaneas, pico_cerrada
        simultaneas += 1
        if not puerta.is_set():
            pico_cerrada = max(pico_cerrada, simultaneas)
        await puerta.wait()
        await candado.acquire()

    def al_salir() -> None:
        nonlocal simultaneas
        simultaneas -= 1
        candado.release()

    entorno.fabrica.puerta = esperar_puerta
    entorno.fabrica.al_salir = al_salir
    caplog.set_level(logging.DEBUG)
    correos = [f"cola-{i}@test.apex" for i in range(50)]
    tareas = [
        asyncio.create_task(
            links.forgot_deliver(c, session_factory=entorno.fabrica, settings=entorno.settings)
        )
        for c in correos
    ]
    for _ in range(200):
        await asyncio.sleep(0)
    assert entorno.fabrica.entradas <= 4, entorno.fabrica.entradas
    puerta.set()
    await asyncio.gather(*tareas)

    assert pico_cerrada <= 4
    admitidas = entorno.fabrica.entradas
    assert 32 <= admitidas <= 36, admitidas
    texto = caplog.text + " ".join(str(x.__dict__) for x in caplog.records)
    descartes = [
        r for r in caplog.records if any(p in r.getMessage().lower() for p in ("descart", "cola"))
    ]
    assert len(descartes) >= 1, "el descarte debe dejar una línea de log"
    assert all("@" not in str(r.__dict__) for r in descartes)
    assert "cola-" not in texto


# `service.forgot` conserva la semántica de v0.1 ------------------------------------------


async def test_service_forgot_sigue_sin_leer_ni_enviar(
    entorno: EntornoCorreo,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    settings_prueba: Settings,
) -> None:
    coach = await usuario_real("coach")

    assert await service.forgot(coach.email, policy=politica()) is None

    assert entorno.smtp.conexiones == []
    assert await tokens_de(session, coach.id) == []
