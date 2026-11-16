"""Sin gastar intento SOLO al abrir la conexión; saturación visible; `_handle` blindado
(S9-W0-4d, S9-D47; hallazgos MEDIUM 1 y 2, LOW 4 y 6 de la revisión de S9-W0-4c).

- Un `OSError` determinista ligado a una fila (`FileNotFoundError`, `TimeoutError`) lanzado en la
  preparación (suscriptor, `load_contact`) GASTA intento y a los 3 queda definitivo.
- La apertura rechazada (puerto cerrado, `CONNECTION LIMIT`, pool agotado) deja el aviso intacto y
  se cuenta en `SendResult.sin_conexion`; tras `NOTIFY_MAX_CONNECTION_ERRORS` seguidos la pasada
  se corta; un éxito entre medias reinicia la cuenta.
- `_handle` atrapa un fallo inesperado de UN aviso (lo cuenta fallido) pero deja pasar la
  cancelación y el fallo del custodio.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.notifications import sending
from app.modules.notifications.schemas import SendResult
from app.modules.notifications.sending import send_pending
from tests.core._apoyo_conexion import conectar_a_puerto_cerrado
from tests.notifications._apoyo_avisos import HOY
from tests.notifications._apoyo_envio import (
    CanalFalso,
    aviso_correo,
    cargar_correo,
    estado_de,
    habilitar_correo,
    regla_correo,
    socio_con_correo,
)

Fabrica = async_sessionmaker[AsyncSession]

pytestmark = pytest.mark.usefixtures("bus_confirmado", "reloj")


async def _avisos(fabrica: Fabrica, cuantos: int) -> list[Any]:
    await habilitar_correo(fabrica)
    regla = await regla_correo(fabrica)
    salida = []
    for i in range(cuantos):
        miembro = await socio_con_correo(fabrica, f"socio{i}@example.com", nombre=f"Socio{i}")
        salida.append(await aviso_correo(fabrica, regla, miembro))
    return salida


async def _pasar(fabrica: Fabrica, canal: CanalFalso, **kw: Any) -> SendResult:
    return await send_pending(fabrica, HOY, load_contact=cargar_correo, channel=canal, **kw)


# MEDIUM 1: un OSError ajeno a la conexión gasta intento -----------------------------------------


@pytest.mark.parametrize("error", [FileNotFoundError("x"), TimeoutError("x")])
async def test_un_oserror_ligado_a_la_fila_gasta_intento_y_a_los_tres_es_definitivo(
    fabrica: Fabrica, error: OSError
) -> None:
    (aviso,) = await _avisos(fabrica, 1)

    async def _roto(_s: AsyncSession, _m: UUID) -> Any:
        raise error

    canal = CanalFalso()
    for esperado in (1, 2, 3):
        r = await send_pending(fabrica, HOY, load_contact=_roto, channel=canal)
        fila = await estado_de(fabrica, aviso.id)
        assert (r.fallidos, r.sin_conexion) == (1, 0)
        assert (fila["status"], fila["attempts"], fila["last_error"]) == (
            "failed",
            esperado,
            "unknown",
        )
    r = await send_pending(fabrica, HOY, load_contact=_roto, channel=canal)
    assert (r.fallidos, r.pendientes) == (0, 0)  # definitivo: ya no es elegible
    assert canal.enviados == []


# MEDIUM 2 y LOW 4: la apertura rechazada no gasta y se cuenta ------------------------------------


async def test_apertura_rechazada_deja_intacto_y_cuenta_sin_conexion(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    (aviso,) = await _avisos(fabrica, 1)

    async def _sin_servidor(_s: AsyncSession) -> None:
        await conectar_a_puerto_cerrado()

    monkeypatch.setattr(sending, "_open_connection", _sin_servidor)
    canal = CanalFalso()
    r = await _pasar(fabrica, canal)

    assert (r.enviados, r.fallidos, r.omitidos, r.sin_conexion) == (0, 0, 0, 1)
    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["attempts"]) == ("pending", 0)
    assert canal.enviados == []


async def test_pool_agotado_real_al_abrir_la_preparacion_no_gasta_intento(
    fabrica: Fabrica,
) -> None:
    """Pool de UNA conexión: el candado la ocupa y la preparación recibe el `TimeoutError` REAL del
    pool (no es un `DBAPIError`): también es un fallo de apertura (LOW 4)."""
    (aviso,) = await _avisos(fabrica, 1)
    base = fabrica.kw["bind"]
    motor = create_async_engine(
        base.url, hide_parameters=True, pool_size=1, max_overflow=0, pool_timeout=0.3
    )
    try:
        canal = CanalFalso()
        r = await _pasar(async_sessionmaker(motor, expire_on_commit=False), canal)
    finally:
        await motor.dispose()

    assert (r.enviados, r.fallidos, r.sin_conexion) == (0, 0, 1)
    assert (await estado_de(fabrica, aviso.id))["attempts"] == 0
    assert canal.enviados == []


async def test_pool_agotado_al_tomar_el_candado_cuenta_sin_conexion(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    (aviso,) = await _avisos(fabrica, 1)

    async def _sin_pool(_s: AsyncSession, _n: UUID) -> bool:
        raise PoolTimeoutError("pool")

    monkeypatch.setattr(sending, "try_in_flight_lock", _sin_pool)
    r = await _pasar(fabrica, CanalFalso())

    assert (r.fallidos, r.sin_conexion) == (0, 1)
    assert (await estado_de(fabrica, aviso.id))["attempts"] == 0


async def test_tras_n_errores_de_conexion_seguidos_la_pasada_se_corta(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert sending.NOTIFY_MAX_CONNECTION_ERRORS == 3
    avisos = await _avisos(fabrica, 5)

    async def _sin_servidor(_s: AsyncSession) -> None:
        await conectar_a_puerto_cerrado()

    monkeypatch.setattr(sending, "_open_connection", _sin_servidor)
    canal = CanalFalso()
    r = await _pasar(fabrica, canal)

    assert r.sin_conexion == 3, "debió cortar a la tercera y no intentar los 5"
    assert r.pendientes == 5
    for aviso in avisos:
        assert (await estado_de(fabrica, aviso.id))["attempts"] == 0


async def test_un_exito_entre_errores_reinicia_la_cuenta(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _avisos(fabrica, 5)
    original = sending._open_connection
    llamadas: list[int] = []

    async def _a_ratos(sesion: AsyncSession) -> None:
        llamadas.append(len(llamadas) + 1)
        if llamadas[-1] in {1, 2, 5, 6}:  # prep a1, prep a2 | prep a4, prep a5
            await conectar_a_puerto_cerrado()
        await original(sesion)

    monkeypatch.setattr(sending, "_open_connection", _a_ratos)
    canal = CanalFalso()
    r = await _pasar(fabrica, canal)

    # a3 envía (aperturas 3 y 4); a1, a2, a4, a5 quedan sin conexión: nunca 3 seguidos
    assert (r.enviados, r.sin_conexion) == (1, 4)


# LOW 6: `_handle` blindado ------------------------------------------------------------------------


async def test_un_fallo_inesperado_de_un_aviso_lo_cuenta_fallido_y_la_pasada_sigue(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    avisos = await _avisos(fabrica, 2)
    original = sending._locked_unit

    async def _revienta_el_primero(sf: Any, notification_id: UUID, *args: Any, **kw: Any) -> str:
        if notification_id == avisos[0].id:
            raise RuntimeError("secreto@ejemplo.co")
        return await original(sf, notification_id, *args, **kw)

    monkeypatch.setattr(sending, "_locked_unit", _revienta_el_primero)
    canal = CanalFalso()
    with caplog.at_level(logging.WARNING):
        r = await _pasar(fabrica, canal)

    assert (r.fallidos, r.enviados) == (1, 1)
    assert "secreto" not in caplog.text
    registros = [x for x in caplog.records if getattr(x, "error_type", None) == "RuntimeError"]
    assert [x.notification_id for x in registros] == [str(avisos[0].id)]  # type: ignore[attr-defined]


async def test_handle_deja_pasar_la_cancelacion(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _cancelada(*_a: object, **_k: object) -> str:
        raise asyncio.CancelledError

    monkeypatch.setattr(sending, "_process_one", _cancelada)
    config = await sending._channels_config(fabrica)
    with pytest.raises(asyncio.CancelledError):
        await sending._handle(fabrica, UUID(int=1), 0, HOY, 3, cargar_correo, CanalFalso(), config)


async def test_handle_deja_pasar_un_fallo_del_custodio(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Sellado(Exception):
        code = "crypto_unavailable"

    async def _sellado(*_a: object, **_k: object) -> str:
        raise Sellado

    monkeypatch.setattr(sending, "_process_one", _sellado)
    config = await sending._channels_config(fabrica)
    with pytest.raises(Sellado):
        await sending._handle(fabrica, UUID(int=1), 0, HOY, 3, cargar_correo, CanalFalso(), config)
