"""Errores de conexión, unidades drenadas y cierre bajo candado (S9-W0-4c; S9-D46).

- MEDIUM 1: un error de conexión REAL (puerto cerrado = `ConnectionRefusedError` pelado; rol con
  `CONNECTION LIMIT 1` = `TooManyConnectionsError`) al tomar el candado o al abrir la sesión de
  `_prepare` deja el aviso `pending`, sin gastar intento y sin enviar.
- LOW 3: `skip` por canal apagado y `_mark_failed` corren bajo el candado de aviso; `_finish`
  avisa (sin datos personales) si el correo salió y el aviso ya estaba cerrado.
- LOW 4: la pasada espera a sus unidades al cancelarse; `_UNITS` queda vacío y ninguna tarea
  deja «exception was never retrieved».
"""

from __future__ import annotations

import asyncio
import gc
import logging
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.notifications import sending
from app.modules.notifications.channels.base import ChannelPayload
from app.modules.notifications.schemas import SendResult
from app.modules.notifications.sending import send_pending
from tests.core._apoyo_conexion import conectar_a_puerto_cerrado, rol_con_un_solo_cupo
from tests.notifications._apoyo_avisos import HOY
from tests.notifications._apoyo_envio import (
    CANALES_CON_CORREO,
    OK,
    CanalFalso,
    aviso_correo,
    cargar_correo,
    estado_de,
    habilitar_correo,
    regla_correo,
    socio_con_correo,
)

Fabrica = async_sessionmaker[AsyncSession]
_TOMAR_CANDADO = sending.try_in_flight_lock  # el real: las pruebas parchean `sending`

pytestmark = pytest.mark.usefixtures("bus_confirmado", "reloj")


async def _pasar(fabrica: Fabrica, canal: CanalFalso) -> SendResult:
    return await send_pending(fabrica, HOY, load_contact=cargar_correo, channel=canal)


async def _un_aviso(fabrica: Fabrica, **cambios: Any) -> Any:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    return await aviso_correo(fabrica, await regla_correo(fabrica), miembro, **cambios)


async def _candado_libre(fabrica: Fabrica, nid: UUID) -> bool:
    async with fabrica() as sesion:
        try:
            return await _TOMAR_CANDADO(sesion, nid)
        finally:
            await sesion.rollback()


async def _intacto(fabrica: Fabrica, canal: CanalFalso, nid: UUID, r: SendResult) -> None:
    assert canal.enviados == []
    assert (r.enviados, r.fallidos, r.omitidos) == (0, 0, 0)
    fila = await estado_de(fabrica, nid)
    assert (fila["status"], fila["attempts"], fila["last_error"]) == ("pending", 0, None)
    assert await _candado_libre(fabrica, nid)


# MEDIUM 1 ---------------------------------------------------------------------------------------


async def test_puerto_cerrado_al_tomar_el_candado_no_gasta_intento(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    aviso = await _un_aviso(fabrica)

    async def _sin_servidor(_s: AsyncSession, _n: UUID) -> bool:
        await conectar_a_puerto_cerrado()
        return False

    monkeypatch.setattr(sending, "try_in_flight_lock", _sin_servidor)
    canal = CanalFalso()
    await _intacto(fabrica, canal, aviso.id, await _pasar(fabrica, canal))


async def test_puerto_cerrado_al_abrir_la_preparacion_no_gasta_intento(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    aviso = await _un_aviso(fabrica)

    async def _sin_servidor(*_a: object, **_k: object) -> None:
        await conectar_a_puerto_cerrado()

    monkeypatch.setattr(sending, "_lock_eligible", _sin_servidor)
    canal = CanalFalso()
    await _intacto(fabrica, canal, aviso.id, await _pasar(fabrica, canal))


async def test_demasiadas_conexiones_en_la_segunda_conexion_no_gasta_intento(
    fabrica: Fabrica,
) -> None:
    """Con `CONNECTION LIMIT 1` el candado ocupa el único cupo y la sesión de `_prepare` recibe
    `TooManyConnectionsError` REAL (el caso más probable con el límite 5 del rol del worker)."""
    aviso = await _un_aviso(fabrica)
    admin = fabrica.kw["bind"]
    canal = CanalFalso()
    async with rol_con_un_solo_cupo(admin) as limitado:
        resultado = await send_pending(
            async_sessionmaker(limitado, expire_on_commit=False),
            HOY,
            load_contact=cargar_correo,
            channel=canal,
        )
    await _intacto(fabrica, canal, aviso.id, resultado)


# LOW 3 ------------------------------------------------------------------------------------------


async def _a_medio_enviar(fabrica: Fabrica, canal_a: CanalFalso) -> tuple[asyncio.Task[Any], Any]:
    """Pasada A detenida dentro del canal y cancelada; su unidad sigue enviando."""
    entro = asyncio.Event()
    libre = asyncio.Event()

    async def _detener(_p: ChannelPayload) -> None:
        entro.set()
        await libre.wait()

    canal_a.espia = _detener
    tarea = asyncio.create_task(_pasar(fabrica, canal_a))
    await asyncio.wait_for(entro.wait(), timeout=5)
    tarea.cancel()
    await asyncio.sleep(0.05)
    return tarea, libre


async def test_el_skip_por_canal_apagado_respeta_una_unidad_aun_enviando(fabrica: Fabrica) -> None:
    aviso = await _un_aviso(fabrica)
    canal_a = CanalFalso()
    tarea, libre = await _a_medio_enviar(fabrica, canal_a)
    apagado = {**CANALES_CON_CORREO, "email": {**CANALES_CON_CORREO["email"], "enabled": False}}
    await habilitar_correo(fabrica, apagado, version=1)

    b = await _pasar(fabrica, CanalFalso())

    assert (b.omitidos, b.enviados) == (0, 0), "B omitió un aviso que A estaba enviando"
    assert (await estado_de(fabrica, aviso.id))["status"] == "pending"
    libre.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(tarea, timeout=10)
    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["skip_reason"]) == ("sent", None)


async def test_mark_failed_corre_bajo_el_candado_de_aviso(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    aviso = await _un_aviso(fabrica)
    visto: list[bool] = []
    original = sending._mark_failed

    async def _espiar(*args: Any, **kw: Any) -> str:
        visto.append(await _candado_libre(fabrica, aviso.id))
        return await original(*args, **kw)

    async def _roto(*_a: object, **_k: object) -> None:
        raise RuntimeError("bug de un suscriptor")

    monkeypatch.setattr(sending, "_mark_failed", _espiar)
    monkeypatch.setattr(sending, "_deliverable_contact", _roto)

    r = await _pasar(fabrica, CanalFalso())

    assert visto == [False], "_mark_failed escribió sin el candado de aviso"
    assert r.fallidos == 1
    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["attempts"], fila["last_error"]) == ("failed", 1, "unknown")


async def test_finish_avisa_si_el_correo_salio_y_el_aviso_ya_estaba_cerrado(
    fabrica: Fabrica, caplog: pytest.LogCaptureFixture
) -> None:
    aviso = await _un_aviso(fabrica, status="skipped", attempts=1)
    preparado = sending._Prepared(
        notification_id=aviso.id,
        member_id=aviso.member_id,
        payload=ChannelPayload(to="secreto@ejemplo.co", subject="asunto", body="cuerpo"),
    )
    with caplog.at_level(logging.WARNING, logger="app.notifications"):
        assert await sending._finish(fabrica, preparado, OK, 3) == sending.UNTOUCHED

    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(avisos) == 1
    assert avisos[0].notification_id == str(aviso.id)  # type: ignore[attr-defined]
    assert "secreto" not in caplog.text and "cuerpo" not in caplog.text


# LOW 4 ------------------------------------------------------------------------------------------


async def test_la_pasada_cancelada_drena_sus_unidades(fabrica: Fabrica) -> None:
    aviso = await _un_aviso(fabrica)
    perdidas: list[dict[str, Any]] = []
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(lambda _l, ctx: perdidas.append(ctx))
    try:
        tarea, libre = await _a_medio_enviar(fabrica, CanalFalso())
        libre.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(tarea, timeout=10)
        assert sending._UNITS == set()
        assert (await estado_de(fabrica, aviso.id))["status"] == "sent"
        gc.collect()
        await asyncio.sleep(0)
    finally:
        loop.set_exception_handler(None)
    assert perdidas == []


async def test_una_unidad_que_revienta_tras_cancelar_no_deja_excepcion_sin_leer(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _un_aviso(fabrica)
    perdidas: list[dict[str, Any]] = []
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(lambda _l, ctx: perdidas.append(ctx))
    soltar = asyncio.Event()

    async def _revienta(*_a: object, **_k: object) -> str:
        await soltar.wait()
        raise RuntimeError("bug")

    monkeypatch.setattr(sending, "_send_and_close", _revienta)
    try:
        tarea = asyncio.create_task(_pasar(fabrica, CanalFalso()))
        await asyncio.sleep(0.5)
        tarea.cancel()
        soltar.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(tarea, timeout=10)
        assert sending._UNITS == set()
        gc.collect()
        await asyncio.sleep(0)
    finally:
        loop.set_exception_handler(None)
    assert perdidas == []


async def test_drain_units_respeta_su_tope() -> None:
    colgada: asyncio.Future[str] = asyncio.ensure_future(asyncio.sleep(30, "x"))
    try:
        await asyncio.wait_for(sending.drain_units({colgada}, timeout_s=0.1), timeout=5)
        assert not colgada.done()
    finally:
        colgada.cancel()
