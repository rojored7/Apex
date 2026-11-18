"""Candado de aviso en vuelo y control optimista a prueba de fallos (S9-W0-4b; S9-D44, S9-D45).

Cubre los hallazgos de las revisiones de S9-W0-4: la defensa 2 (`attempts`), `_lock_key`,
`_lock_eligible`, la sesión del candado frente a `idle_in_transaction_session_timeout`, el tope
total del envío, el fallo al tomar el candado, la cancelación, `_finish` sin pisar estados
cerrados, el `skip` frente a un envío en vuelo y el opt-in de correo al enviar.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.notifications import sending, service
from app.modules.notifications.channels.base import ChannelPayload
from app.modules.notifications.schemas import SendResult
from app.modules.notifications.sending import send_pending
from app.worker.registry import get_registry
from tests.notifications._apoyo_avisos import HOY, canales
from tests.notifications._apoyo_envio import (
    OK,
    CanalFalso,
    aviso_correo,
    cargar_correo,
    estado_de,
    fallo,
    habilitar_correo,
    regla_correo,
    socio_con_correo,
    todos,
)

Fabrica = async_sessionmaker[AsyncSession]

pytestmark = pytest.mark.usefixtures("bus_confirmado", "reloj")


async def _pasar(fabrica: Fabrica, canal: CanalFalso, **kw: object) -> SendResult:
    return await send_pending(fabrica, HOY, load_contact=cargar_correo, channel=canal, **kw)  # type: ignore[arg-type]


async def _un_aviso(fabrica: Fabrica, **cambios: Any) -> Any:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    return await aviso_correo(fabrica, await regla_correo(fabrica), miembro, **cambios)


async def _esperar(fabrica: Fabrica, nid: UUID, estado: str, segundos: float = 8.0) -> None:
    async with asyncio.timeout(segundos):
        while (await estado_de(fabrica, nid))["status"] != estado:  # noqa: ASYNC110
            await asyncio.sleep(0.02)


async def _candado_libre(fabrica: Fabrica, nid: UUID) -> bool:
    """`True` si una conexión independiente obtiene (y suelta) el candado de aviso."""
    async with fabrica() as sesion:
        try:
            return await sending.try_in_flight_lock(sesion, nid)
        finally:
            await sesion.rollback()


# 1. Defensa 2: control optimista por `attempts` ---------------------------------------------------


async def test_una_lista_vieja_no_reenvia_un_aviso_que_otra_pasada_ya_proceso(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B lista `(id, 0)`; A procesa completo (falla, `attempts = 1`, candado liberado); B sigue
    con su lista vieja. Solo `attempts == expected_attempts` evita que B lo reenvíe."""
    aviso = await _un_aviso(fabrica)
    listo = asyncio.Event()
    seguir = asyncio.Event()
    original = sending._channels_config
    primera = True

    async def _enganchada(sf: Fabrica) -> Any:
        nonlocal primera
        if primera:
            primera = False
            listo.set()
            await seguir.wait()
        return await original(sf)

    monkeypatch.setattr(sending, "_channels_config", _enganchada)
    canal_a = CanalFalso(resultados=[fallo("timeout")])
    canal_b = CanalFalso()
    tarea_b = asyncio.create_task(_pasar(fabrica, canal_b))
    await asyncio.wait_for(listo.wait(), timeout=5)
    a = await _pasar(fabrica, canal_a)
    seguir.set()
    b = await asyncio.wait_for(tarea_b, timeout=10)

    assert (a.enviados, a.fallidos) == (0, 1)
    assert canal_b.enviados == []
    assert (b.enviados, b.fallidos) == (0, 0)
    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["attempts"]) == ("failed", 1)
    assert {f["attempts"] for f in await todos(fabrica)} == {1}


async def test_lock_eligible_exige_que_attempts_coincida(fabrica: Fabrica) -> None:
    aviso = await _un_aviso(fabrica, status="failed", attempts=1, last_error="timeout")
    async with fabrica() as sesion, sesion.begin():
        assert await sending.lock_eligible(sesion, aviso.id, 0, HOY, 3) is None
    async with fabrica() as sesion, sesion.begin():
        fila = await sending.lock_eligible(sesion, aviso.id, 1, HOY, 3)
        assert fila is not None and fila.id == aviso.id


# 6. `_lock_key` -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entero", "esperado"),
    [
        (0, 0),
        (1, 1),
        (0x7FFFFFFF, 2_147_483_647),
        (0x80000000, -2_147_483_648),
        (0x80000001, -2_147_483_647),
        (0xFFFFFFFF, -1),
        ((7 << 64) | 0x80000000, -2_147_483_648),
    ],
)
def test_lock_key_es_un_int4_con_signo_de_los_32_bits_bajos(entero: int, esperado: int) -> None:
    assert sending._lock_key(UUID(int=entero)) == esperado


def test_lock_key_siempre_cabe_en_int4() -> None:
    for _ in range(500):
        assert -(2**31) <= sending._lock_key(uuid4()) < 2**31


# 2. Inactividad y tope total ----------------------------------------------------------------------


async def test_la_sesion_del_candado_sobrevive_a_idle_in_transaction_session_timeout(
    fabrica: Fabrica,
) -> None:
    """Con el rol del worker en 60 s, un SMTP lento mataría la sesión del candado. La sesión del
    candado desactiva ese tiempo (`set_config(..., true)`): aquí el motor lo fija en 300 ms."""
    aviso = await _un_aviso(fabrica)
    motor = fabrica.kw["bind"]
    corto = create_async_engine(
        motor.url,
        hide_parameters=True,
        connect_args={"server_settings": {"idle_in_transaction_session_timeout": "300ms"}},
    )
    libres: list[bool] = []

    async def _lento(_p: ChannelPayload) -> None:
        await asyncio.sleep(1.0)
        libres.append(await _candado_libre(fabrica, aviso.id))

    try:
        resultado = await _pasar(
            async_sessionmaker(corto, expire_on_commit=False), CanalFalso(espia=_lento)
        )
    finally:
        await corto.dispose()

    assert libres == [False], "el candado se soltó a mitad del envío"
    assert resultado.enviados == 1


async def test_el_tope_total_corta_un_canal_que_no_responde(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    aviso = await _un_aviso(fabrica)
    monkeypatch.setattr(sending, "NOTIFY_SEND_TIMEOUT_S", 0.2)

    async def _colgado(_p: ChannelPayload) -> None:
        await asyncio.sleep(30)

    resultado = await asyncio.wait_for(_pasar(fabrica, CanalFalso(espia=_colgado)), timeout=10)

    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["last_error"], fila["attempts"]) == ("failed", "timeout", 1)
    assert resultado.fallidos == 1  # sigue elegible: un reintento posterior lo envía
    assert await _candado_libre(fabrica, aviso.id)


def test_el_tope_total_mas_el_plazo_blando_y_el_cierre_caben_en_el_plazo_del_job() -> None:
    """S9-D46 (LOW 5): el peor caso de una corrida es el plazo blando (la última unidad empieza
    justo antes), su envío, el cierre y el conteo final; todo debe caber en el `timeout_s`
    REGISTRADO del job `notify`, no en un literal."""
    spec = next(s for s in get_registry() if s.name == "notify")
    campos = Settings.model_fields
    cierre_s = 2 * campos["DB_LOCK_TIMEOUT_MS"].default / 1000  # `_finish` y su reintento
    conteo_s = campos["DB_STATEMENT_TIMEOUT_MS"].default / 1000  # `_count_eligible`
    assert sending.NOTIFY_CLOSE_MARGIN_S >= cierre_s + conteo_s
    total = (
        sending.NOTIFY_PRE_MARGIN_S
        + sending.NOTIFY_SOFT_DEADLINE_S
        + sending.NOTIFY_PREPARE_MARGIN_S
        + sending.NOTIFY_SEND_TIMEOUT_S
        + sending.NOTIFY_CLOSE_MARGIN_S
    )
    assert 0 < sending.NOTIFY_SEND_TIMEOUT_S < sending.NOTIFY_SOFT_DEADLINE_S
    assert total < spec.timeout_s


async def test_el_tope_total_corta_un_envio_bloqueado_en_un_hilo(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El SMTP real corre en `asyncio.to_thread`: el hilo NO se puede cancelar y aun así la pasada
    sigue a los `NOTIFY_SEND_TIMEOUT_S` (S9-D46, LOW 7). El evento se libera al final."""
    aviso = await _un_aviso(fabrica)
    monkeypatch.setattr(sending, "NOTIFY_SEND_TIMEOUT_S", 0.3)
    hilo_libre = threading.Event()

    async def _smtp_lento(_p: ChannelPayload) -> None:
        await asyncio.to_thread(hilo_libre.wait, 20)

    try:
        resultado = await asyncio.wait_for(
            _pasar(fabrica, CanalFalso(espia=_smtp_lento)), timeout=10
        )
        assert not hilo_libre.is_set(), "la pasada esperó al hilo en vez de cortarlo"
    finally:
        hilo_libre.set()

    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["last_error"], fila["attempts"]) == ("failed", "timeout", 1)
    assert resultado.fallidos == 1
    assert await _candado_libre(fabrica, aviso.id)


# 4. Cancelación -----------------------------------------------------------------------------------


async def test_cancelar_la_pasada_no_suelta_el_candado_hasta_cerrar_el_aviso(
    fabrica: Fabrica,
) -> None:
    """Desde S9-D46 la pasada cancelada además ESPERA (con tope) a su unidad antes de salir; el
    candado se suelta solo cuando el cierre terminó."""
    aviso = await _un_aviso(fabrica)
    entro = asyncio.Event()
    libre = asyncio.Event()

    async def _detener(_p: ChannelPayload) -> None:
        entro.set()
        await libre.wait()

    canal_a = CanalFalso(espia=_detener)
    tarea = asyncio.create_task(_pasar(fabrica, canal_a))
    await asyncio.wait_for(entro.wait(), timeout=5)
    tarea.cancel()
    await asyncio.sleep(0.05)

    canal_b = CanalFalso()
    b = await _pasar(fabrica, canal_b)
    assert canal_b.enviados == [], "otra pasada obtuvo el candado con la unidad aún enviando"
    assert (b.enviados, b.fallidos) == (0, 0)
    assert not tarea.done(), "la pasada cancelada no esperó a su unidad"

    libre.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(tarea, timeout=10)
    assert (await estado_de(fabrica, aviso.id))["status"] == "sent"
    assert len(canal_a.enviados) == 1
    assert await asyncio.wait_for(_libera_pronto(fabrica, aviso.id), timeout=5)


async def _libera_pronto(fabrica: Fabrica, nid: UUID) -> bool:
    while not await _candado_libre(fabrica, nid):  # noqa: ASYNC110
        await asyncio.sleep(0.02)
    return True


# 7. `_finish` no pisa estados cerrados ------------------------------------------------------------


@pytest.mark.parametrize("estado", ["sent", "skipped"])
async def test_finish_no_pisa_un_aviso_ya_cerrado(fabrica: Fabrica, estado: str) -> None:
    aviso = await _un_aviso(fabrica, status=estado, attempts=1)
    antes = await estado_de(fabrica, aviso.id)
    preparado = sending._Prepared(
        notification_id=aviso.id,
        member_id=aviso.member_id,
        payload=ChannelPayload(to="a@b.co", subject="s", body="b"),
    )

    for resultado in (OK, fallo("timeout")):
        assert await sending._finish(fabrica, preparado, resultado, 3) == sending.UNTOUCHED

    despues = await estado_de(fabrica, aviso.id)
    for campo in ("status", "sent_at", "skip_reason", "last_error", "attempts"):
        assert despues[campo] == antes[campo]


# 7b. `skip` frente a un envío en vuelo ------------------------------------------------------------


async def test_omitir_un_aviso_en_vuelo_da_409_notification_in_flight(fabrica: Fabrica) -> None:
    from app.modules.notifications.exceptions import NotificationInFlight

    aviso = await _un_aviso(fabrica)
    resultados: list[str] = []

    async def _mientras_envia(_p: ChannelPayload) -> None:
        async with fabrica() as sesion:
            with actor_scope(SYSTEM_USER_ID):
                try:
                    await service.skip(sesion, aviso.id, "Motivo de prueba", SYSTEM_USER_ID)
                except NotificationInFlight as error:
                    resultados.append(f"{error.status}:{error.code}")
                    await sesion.rollback()

    resultado = await _pasar(fabrica, CanalFalso(espia=_mientras_envia))

    assert resultados == ["409:notification_in_flight"]
    assert resultado.enviados == 1
    assert (await estado_de(fabrica, aviso.id))["status"] == "sent"


async def test_skip_conserva_el_candado_de_aviso_hasta_confirmar(fabrica: Fabrica) -> None:
    """MEDIUM 2 (S9-D46). La versión anterior pasaba aunque se quitara el try-lock de `skip`: el
    `FOR UPDATE ... SKIP LOCKED` de la pasada ya la dejaba fuera. Lo que solo el try-lock da es el
    candado de aviso: mientras `skip` no confirma, otra conexión NO lo obtiene (así ningún envío
    empieza y, si lo hubiera en vuelo, `skip` respondería 409)."""
    aviso = await _un_aviso(fabrica)
    canal = CanalFalso()
    async with fabrica() as sesion:
        with actor_scope(SYSTEM_USER_ID):
            await service.skip(sesion, aviso.id, "Motivo de prueba", SYSTEM_USER_ID)
            assert not await _candado_libre(fabrica, aviso.id), "skip no tomó el candado de aviso"
            resultado = await _pasar(fabrica, canal)  # el `skip` aún no confirma
            await sesion.commit()

    assert canal.enviados == []
    assert resultado.enviados == 0
    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["attempts"]) == ("skipped", 0)
    assert await _candado_libre(fabrica, aviso.id)


async def test_omitir_un_aviso_que_no_esta_en_vuelo_sigue_funcionando(fabrica: Fabrica) -> None:
    aviso = await _un_aviso(fabrica)
    async with fabrica() as sesion:
        with actor_scope(SYSTEM_USER_ID):
            salida = await service.skip(sesion, aviso.id, "Motivo de prueba", SYSTEM_USER_ID)
            await sesion.commit()
    assert salida.status == "skipped"
    assert await _candado_libre(fabrica, aviso.id)


# 8. Opt-in de correo al enviar --------------------------------------------------------------------


async def test_si_el_socio_desactiva_el_correo_despues_de_generado_no_se_envia(
    fabrica: Fabrica,
) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    async with fabrica() as sesion:
        await canales(sesion, miembro, email=False)
    canal = CanalFalso()

    resultado = await _pasar(fabrica, canal)

    assert canal.enviados == []
    assert (resultado.enviados, resultado.omitidos) == (0, 1)
    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["skip_reason"], fila["attempts"]) == (
        "skipped",
        "canal_desactivado_socio",
        0,
    )


# 9. El correo apagado no se descifra (S9-D46, LOW 6) ----------------------------------------------


async def _descifrados(fabrica: Fabrica, miembro_id: UUID) -> int:
    async with fabrica() as sesion:
        total = await sesion.scalar(
            text(
                "SELECT count(*) FROM crypto.crypto_ops WHERE record_id = :r AND verb = 'decrypt'"
            ),
            {"r": miembro_id},
        )
    return int(total or 0)


async def test_un_correo_apagado_se_omite_sin_descifrar_nada(fabrica: Fabrica) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    async with fabrica() as sesion:
        await canales(sesion, miembro, email=False)
    antes = await _descifrados(fabrica, miembro.id)

    resultado = await _pasar(fabrica, CanalFalso())

    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["skip_reason"]) == ("skipped", "canal_desactivado_socio")
    assert resultado.omitidos == 1
    assert await _descifrados(fabrica, miembro.id) == antes, "descifró a un socio apagado"


async def test_un_socio_sin_consentimiento_se_omite_sin_descifrar_nada(fabrica: Fabrica) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica, consentido=False)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    antes = await _descifrados(fabrica, miembro.id)

    await _pasar(fabrica, CanalFalso())

    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["skip_reason"]) == ("skipped", "sin_consentimiento")
    assert await _descifrados(fabrica, miembro.id) == antes


async def test_con_el_correo_activo_si_se_descifra_una_vez(fabrica: Fabrica) -> None:
    aviso = await _un_aviso(fabrica)
    antes = await _descifrados(fabrica, aviso.member_id)

    await _pasar(fabrica, CanalFalso())

    assert await _descifrados(fabrica, aviso.member_id) == antes + 1
