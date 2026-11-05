"""`sending.send_pending` y `service.send_pending` (US-125; S5-D28, S5-D35, M-6). # Rojo B8

Contrato que fija el Rojo:
- toma avisos `email` en `pending` (solo de `today`) o `failed` (de `today` y anteriores) con
  `attempts < max_attempts`; nunca toca `whatsapp_link`, `sent` ni `skipped`;
- una transacción por aviso: (a) `attempts += 1` + descifrar el correo y COMMIT; (b) `channel.send`
  FUERA de la transacción; (c) `sent` (`sent_at`, `sent_by` sistema, `last_error` limpio) o
  `failed` + `last_error` de código cerrado; por ORM (deja `update` en `audit_log`);
- `NotificationFailed` solo al agotar los intentos; `NotificationSent` al enviar; sin PII;
- `SendResult(enviados, fallidos, omitidos, pendientes)`: `fallidos` = fallidos en esta pasada,
  `pendientes` = `email` aún elegibles al terminar;
- sin canal configurado o con `channels.email.enabled` falso: cada aviso `email` queda `skipped`
  con `skip_reason = "canal_no_configurado"` y cuenta en `omitidos`, sin descifrar nada;
- sin correo utilizable (socio sin correo o sin consentimiento): `failed`/`invalid_recipient`
  sin llamar al canal;
- un canal que lanza se trata como `unknown` y el lote sigue; los logs no llevan PII.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.notifications import service
from app.modules.notifications.channels.base import ChannelPayload
from app.modules.notifications.schemas import SendResult
from app.modules.notifications.sending import NOTIFY_MAX_ATTEMPTS, send_pending
from app.modules.notifications.service import NotificationFailed, NotificationSent
from tests.factories.notifications import make_rule
from tests.notifications._apoyo_avisos import HOY, eventos_de
from tests.notifications._apoyo_envio import (
    CORREO,
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


async def test_el_nombre_del_tope_de_intentos_es_tres() -> None:
    assert NOTIFY_MAX_ATTEMPTS == 3


async def test_sin_avisos_no_llama_al_canal_ni_descifra(fabrica: Fabrica) -> None:
    canal = CanalFalso()
    resultado = await _pasar(fabrica, canal)
    assert resultado == SendResult(enviados=0, fallidos=0, omitidos=0, pendientes=0)
    assert canal.enviados == []


async def test_envia_y_marca_sent_con_hora_actor_e_intento(
    fabrica: Fabrica, reloj: FrozenClock
) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    canal = CanalFalso()

    resultado = await _pasar(fabrica, canal)

    fila = await estado_de(fabrica, aviso.id)
    assert resultado == SendResult(enviados=1, fallidos=0, omitidos=0, pendientes=0)
    assert (fila["status"], fila["attempts"], fila["last_error"]) == ("sent", 1, None)
    assert fila["sent_by"] == SYSTEM_USER_ID
    assert fila["sent_at"] == reloj.now_utc()


async def test_el_canal_recibe_el_correo_descifrado_y_el_texto_ya_renderizado(
    fabrica: Fabrica,
) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    canal = CanalFalso()

    await _pasar(fabrica, canal)

    (payload,) = canal.enviados
    assert payload.to == CORREO
    assert payload.subject == aviso.rendered_subject
    assert payload.body == aviso.rendered_body


async def test_el_payload_lleva_reply_to_y_nombre_de_la_configuracion(fabrica: Fabrica) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    canal = CanalFalso()

    await _pasar(fabrica, canal)

    (payload,) = canal.enviados
    assert (payload.reply_to, payload.from_name) == ("hola@gimnasio.test", "APEX CrossFit")


async def test_solo_toca_avisos_email(fabrica: Fabrica) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    wa = await aviso_correo(
        fabrica,
        await make_rule_wa(fabrica),
        miembro,
        channel="whatsapp_link",
    )
    canal = CanalFalso()

    resultado = await _pasar(fabrica, canal)

    fila = await estado_de(fabrica, wa.id)
    assert (fila["status"], fila["attempts"]) == ("pending", 0)
    assert canal.enviados == []
    assert resultado == SendResult(0, 0, 0, 0)


async def make_rule_wa(fabrica: Fabrica) -> object:
    async with fabrica() as sesion:
        return await make_rule(sesion, channel="whatsapp_link", name="WA")


@pytest.mark.parametrize("estado", ["sent", "skipped"])
async def test_no_toca_avisos_sent_ni_skipped(fabrica: Fabrica, estado: str) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro, status=estado)
    canal = CanalFalso()

    await _pasar(fabrica, canal)

    assert canal.enviados == []
    assert (await estado_de(fabrica, aviso.id))["status"] == estado


# Fallos y reintentos ----------------------------------------------------------------------------


@pytest.mark.parametrize("codigo", ["timeout", "auth", "refused", "invalid_recipient", "unknown"])
async def test_un_fallo_deja_failed_con_el_codigo_cerrado_y_sigue_elegible(
    fabrica: Fabrica, codigo: str
) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    caido = eventos_de(NotificationFailed)

    resultado = await _pasar(fabrica, CanalFalso([fallo(codigo)]))

    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["attempts"], fila["last_error"]) == ("failed", 1, codigo)
    assert fila["sent_at"] is None
    assert resultado == SendResult(enviados=0, fallidos=1, omitidos=0, pendientes=1)
    assert caido.vistos == [], "con intentos disponibles aún no es un fallo definitivo"


async def test_reintenta_un_failed_y_al_enviar_limpia_el_error(fabrica: Fabrica) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    canal = CanalFalso([fallo("timeout"), OK])

    await _pasar(fabrica, canal)
    segunda = await _pasar(fabrica, canal)

    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["attempts"], fila["last_error"]) == ("sent", 2, None)
    assert segunda == SendResult(enviados=1, fallidos=0, omitidos=0, pendientes=0)
    assert len(canal.enviados) == 2


async def test_al_tercer_fallo_queda_failed_para_siempre_y_emite_el_evento(
    fabrica: Fabrica,
) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro, attempts=2)
    caido = eventos_de(NotificationFailed)
    canal = CanalFalso([fallo("refused")])

    tercera = await _pasar(fabrica, canal)
    cuarta = await _pasar(fabrica, canal)

    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["attempts"], fila["last_error"]) == ("failed", 3, "refused")
    assert tercera == SendResult(enviados=0, fallidos=1, omitidos=0, pendientes=0)
    assert cuarta == SendResult(0, 0, 0, 0)
    assert len(canal.enviados) == 1, "con 3 intentos ya no se vuelve a enviar"
    assert [(e.notification_id, e.member_id, e.channel) for e in caido.vistos] == [
        (aviso.id, miembro.id, "email")
    ]


async def test_max_attempts_se_respeta(fabrica: Fabrica) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(
        fabrica, await regla_correo(fabrica), miembro, status="failed", attempts=1
    )
    canal = CanalFalso()

    resultado = await _pasar(fabrica, canal, max_attempts=1)

    assert canal.enviados == [] and resultado == SendResult(0, 0, 0, 0)
    assert (await estado_de(fabrica, aviso.id))["attempts"] == 1


async def test_failed_de_dias_anteriores_se_reintenta_y_pending_viejo_no(
    fabrica: Fabrica,
) -> None:
    await habilitar_correo(fabrica)
    regla = await regla_correo(fabrica)
    ayer = HOY - timedelta(days=1)
    viejo_failed = await aviso_correo(
        fabrica,
        regla,
        await socio_con_correo(fabrica),
        target_date=ayer,
        status="failed",
        attempts=1,
    )
    viejo_pending = await aviso_correo(
        fabrica,
        regla,
        await socio_con_correo(fabrica, "otra@example.com"),
        target_date=HOY - timedelta(days=20),
    )
    de_ayer = await aviso_correo(
        fabrica, regla, await socio_con_correo(fabrica, "tres@example.com"), target_date=ayer
    )
    canal = CanalFalso()

    await _pasar(fabrica, canal)

    assert (await estado_de(fabrica, viejo_failed.id))["status"] == "sent"
    assert (await estado_de(fabrica, viejo_pending.id))["status"] == "pending"
    # S5-D227: un pending de ayer (dentro de la ventana de 15 días) sí se envía hoy.
    assert (await estado_de(fabrica, de_ayer.id))["status"] == "sent"
    assert len(canal.enviados) == 2


async def test_un_corte_entre_el_envio_y_el_cierre_repite_el_correo_una_vez(
    fabrica: Fabrica,
) -> None:
    """Entrega "al menos una vez": tras un corte el aviso quedó `pending` con 1 intento; la
    corrida siguiente lo reenvía una vez y lo cierra en `sent` con 2."""
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro, attempts=1)
    canal = CanalFalso()

    await _pasar(fabrica, canal)
    await _pasar(fabrica, canal)

    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["attempts"]) == ("sent", 2)
    assert len(canal.enviados) == 1


async def test_un_canal_que_lanza_cuenta_como_unknown_y_el_lote_sigue(fabrica: Fabrica) -> None:
    await habilitar_correo(fabrica)
    regla = await regla_correo(fabrica)
    primero = await aviso_correo(fabrica, regla, await socio_con_correo(fabrica))
    segundo = await aviso_correo(
        fabrica, regla, await socio_con_correo(fabrica, "dos@example.com", nombre="Ana")
    )
    llamadas: list[int] = []

    class Mixto(CanalFalso):
        async def send(self, payload: ChannelPayload):  # type: ignore[no-untyped-def, override]
            llamadas.append(1)
            if len(llamadas) == 1:
                raise RuntimeError("falla con lucia.gomez@example.com")
            return OK

    resultado = await _pasar(fabrica, Mixto())

    filas = await todos(fabrica)
    assert sorted((f["status"], f["last_error"]) for f in filas) == [
        ("failed", "unknown"),
        ("sent", None),
    ]
    assert {primero.id, segundo.id} == {f["id"] for f in filas}
    assert resultado == SendResult(enviados=1, fallidos=1, omitidos=0, pendientes=1)


# Sin correo utilizable --------------------------------------------------------------------------


async def test_socio_sin_correo_queda_omitido_sin_correo_sin_llamar_al_canal(
    fabrica: Fabrica,
) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica, None)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    canal = CanalFalso()

    resultado = await _pasar(fabrica, canal)

    fila = await estado_de(fabrica, aviso.id)
    # S5-D227: reintentar no sirve, no es `failed`.
    assert (fila["status"], fila["skip_reason"], fila["last_error"]) == (
        "skipped",
        "sin_correo",
        None,
    )
    assert canal.enviados == []
    assert (resultado.omitidos, resultado.fallidos) == (1, 0)


async def test_socio_sin_consentimiento_no_recibe_el_correo(fabrica: Fabrica) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica, consentido=False)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    canal = CanalFalso()

    await _pasar(fabrica, canal)

    assert canal.enviados == []
    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["skip_reason"]) == ("skipped", "sin_consentimiento")


# Canal apagado o sin credenciales ----------------------------------------------------------------


async def test_canal_habilitado_sin_credenciales_espera_sin_descifrar(fabrica: Fabrica) -> None:
    """S5-D231: antes se omitía; ahora el aviso queda `pending` (ver la prueba de D231 abajo)."""
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    canal = CanalFalso(configured=False)

    resultado = await _pasar(fabrica, canal)

    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["skip_reason"], fila["attempts"]) == ("pending", None, 0)
    assert canal.enviados == []
    assert resultado.omitidos == 0 and resultado.pendientes == 1
    async with fabrica() as sesion:
        revelados = await sesion.scalar(
            text("SELECT count(*) FROM audit.audit_log WHERE action = 'reveal'")
        )
    assert revelados == 0


async def test_canal_apagado_en_la_configuracion_omite_aunque_haya_credenciales(
    fabrica: Fabrica,
) -> None:
    """Sin fila en `settings.channels` los valores por defecto dejan el correo apagado."""
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    canal = CanalFalso(configured=True)

    resultado = await _pasar(fabrica, canal)

    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["skip_reason"]) == ("skipped", "canal_no_configurado")
    assert canal.enviados == [] and resultado.omitidos == 1


# Transacciones y candados -----------------------------------------------------------------------


async def test_el_envio_ocurre_fuera_de_la_transaccion_y_sin_candado(
    fabrica: Fabrica,
) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    visto: dict[str, object] = {}

    async def espiar(_payload: ChannelPayload) -> None:
        async with fabrica() as otra, otra.begin():
            await otra.execute(text("SET LOCAL lock_timeout = '500ms'"))
            visto["attempts"] = await otra.scalar(
                text("SELECT attempts FROM notifications.notifications WHERE id = :i FOR UPDATE"),
                {"i": aviso.id},
            )

    await _pasar(fabrica, CanalFalso(espia=espiar))

    assert visto["attempts"] == 1, "el intento ya estaba confirmado y la fila libre al enviar"


async def test_salta_los_avisos_bloqueados_por_otra_transaccion(fabrica: Fabrica) -> None:
    await habilitar_correo(fabrica)
    regla = await regla_correo(fabrica)
    bloqueado = await aviso_correo(fabrica, regla, await socio_con_correo(fabrica))
    libre = await aviso_correo(
        fabrica, regla, await socio_con_correo(fabrica, "libre@example.com", nombre="Ana")
    )
    canal = CanalFalso()

    async with fabrica() as retenedor, retenedor.begin():
        await retenedor.execute(
            text("SELECT id FROM notifications.notifications WHERE id = :i FOR UPDATE"),
            {"i": bloqueado.id},
        )
        resultado = await asyncio.wait_for(_pasar(fabrica, canal), timeout=10)

    assert (await estado_de(fabrica, bloqueado.id))["attempts"] == 0
    assert (await estado_de(fabrica, libre.id))["status"] == "sent"
    assert resultado.enviados == 1 and len(canal.enviados) == 1


# Rastro, eventos y logs -------------------------------------------------------------------------


async def test_el_cambio_de_estado_deja_update_en_la_auditoria_por_orm(fabrica: Fabrica) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)

    await _pasar(fabrica, CanalFalso())

    async with fabrica() as sesion:
        filas = (
            await sesion.execute(
                text(
                    "SELECT action, user_id FROM audit.audit_log "
                    "WHERE table_name = 'notifications.notifications' AND record_id = :i "
                    "ORDER BY seq"
                ),
                {"i": aviso.id},
            )
        ).all()
    acciones = [f[0] for f in filas]
    assert "update" in acciones
    assert all(f[1] == SYSTEM_USER_ID for f in filas if f[0] == "update")


async def test_emite_notification_sent_solo_con_ids_y_canal(fabrica: Fabrica) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    enviado = eventos_de(NotificationSent)

    await _pasar(fabrica, CanalFalso())

    (evento,) = enviado.vistos
    assert (evento.notification_id, evento.member_id, evento.channel) == (
        aviso.id,
        miembro.id,
        "email",
    )
    assert CORREO not in repr(evento)


async def test_los_logs_no_llevan_correo_nombre_ni_cuerpo(
    fabrica: Fabrica, caplog: pytest.LogCaptureFixture
) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    caplog.set_level(logging.DEBUG)

    await _pasar(fabrica, CanalFalso([fallo("timeout"), OK]))
    await _pasar(fabrica, CanalFalso())

    texto = "\n".join(
        r.getMessage() + " " + " ".join(f"{k}={v}" for k, v in r.__dict__.items())
        for r in caplog.records
        if r.name.startswith("app.")
    )
    for prohibido in (CORREO, "Lucía", "Gómez", aviso.rendered_body, "tu plan Mensual"):
        assert prohibido not in texto, prohibido


# La fachada -------------------------------------------------------------------------------------


async def test_service_send_pending_descifra_solo_el_correo_con_proposito_notify(
    fabrica: Fabrica,
) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica, phone="300 765 4321")
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    canal = CanalFalso()

    with actor_scope(SYSTEM_USER_ID):
        resultado = await service.send_pending(fabrica, HOY, channel=canal)

    assert resultado.enviados == 1 and len(canal.enviados) == 1
    async with fabrica() as sesion:
        campos = (
            await sesion.execute(
                text(
                    "SELECT after->>'field', after->>'purpose' FROM audit.audit_log "
                    "WHERE action = 'reveal' AND record_id = :m"
                ),
                {"m": miembro.id},
            )
        ).all()
        claves = (
            await sesion.execute(
                text(
                    "SELECT DISTINCT data_class FROM crypto.crypto_ops "
                    "WHERE verb = 'decrypt' AND record_id = :m"
                ),
                {"m": miembro.id},
            )
        ).all()
    assert {tuple(c) for c in campos} == {("email", "notify")}
    assert {c[0] for c in claves} == {"member.email"}
    assert (await estado_de(fabrica, aviso.id))["status"] == "sent"


# S5-D227 / S5-D228 ------------------------------------------------------------------------------


async def test_dos_pasadas_en_paralelo_no_envian_el_mismo_aviso_dos_veces(
    fabrica: Fabrica,
) -> None:
    """S5-D228: además del `claim_run`, el candado por fila: ninguna fila la toman ambas."""
    await habilitar_correo(fabrica)
    regla = await regla_correo(fabrica)
    for i in range(4):
        await aviso_correo(
            fabrica, regla, await socio_con_correo(fabrica, f"p{i}@example.com", nombre=f"P{i}")
        )
    canal = CanalFalso()

    async def _lento(_p: ChannelPayload) -> None:
        await asyncio.sleep(0.05)

    canal.espia = _lento
    a, b = await asyncio.gather(_pasar(fabrica, canal), _pasar(fabrica, canal))

    assert a.enviados + b.enviados == 4
    assert len(canal.enviados) == 4
    assert {f["attempts"] for f in await todos(fabrica)} == {1}


async def test_una_fila_whatsapp_pending_no_se_modifica_aunque_el_canal_este_apagado(
    fabrica: Fabrica,
) -> None:
    """S5-D228 (nota D222): con el correo apagado se omiten los `email`, no un `whatsapp_link`."""
    regla = await regla_correo(fabrica)
    otro = await socio_con_correo(fabrica, "wa@example.com", nombre="Wa")
    wa = await aviso_correo(fabrica, regla, otro, channel="whatsapp_link")
    correo = await aviso_correo(fabrica, regla, await socio_con_correo(fabrica))

    resultado = await _pasar(fabrica, CanalFalso(configured=False))

    assert resultado.omitidos == 1
    fila = await estado_de(fabrica, wa.id)
    assert (fila["status"], fila["skip_reason"], fila["attempts"]) == ("pending", None, 0)
    assert (await estado_de(fabrica, correo.id))["status"] == "skipped"


# Revisión de seguridad de B8 (S5-D229 a D232) -----------------------------------------------------

import inspect  # noqa: E402
from typing import Any  # noqa: E402

from sqlalchemy.exc import OperationalError  # noqa: E402

from app.core.crypto.errors import CryptoUnavailable  # noqa: E402
from app.modules.members.service import Contact  # noqa: E402
from app.modules.notifications import sending  # noqa: E402
from app.modules.notifications.service import NotificationFailed as _Fallido  # noqa: E402


async def _esperar_estado(fabrica: Fabrica, nid: Any, estado: str, segundos: float = 8.0) -> None:
    limite = asyncio.get_running_loop().time() + segundos
    while asyncio.get_running_loop().time() < limite:
        if (await estado_de(fabrica, nid))["status"] == estado:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"el aviso no llegó a {estado}")


async def test_si_el_cierre_falla_una_vez_se_reintenta_y_queda_sent(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S5-D229: el correo ya salió; un fallo de la base al cerrar se reintenta con sesión nueva."""
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    real = sending._finish
    llamadas: list[int] = []

    async def inestable(*args: Any, **kw: Any) -> str:
        llamadas.append(1)
        if len(llamadas) == 1:
            raise OperationalError("UPDATE", {}, Exception("corte"))
        return await real(*args, **kw)

    monkeypatch.setattr(sending, "_finish", inestable)

    resultado = await _pasar(fabrica, CanalFalso())

    assert (await estado_de(fabrica, aviso.id))["status"] == "sent"
    assert (resultado.enviados, resultado.fallidos) == (1, 0)


async def test_si_el_cierre_falla_dos_veces_cuenta_fallido_y_el_lote_sigue(
    fabrica: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    await habilitar_correo(fabrica)
    regla = await regla_correo(fabrica)
    primero = await aviso_correo(fabrica, regla, await socio_con_correo(fabrica))
    await aviso_correo(
        fabrica, regla, await socio_con_correo(fabrica, "dos@example.com", nombre="Ana")
    )
    real = sending._finish
    vistos: list[Any] = []

    async def roto_para_el_primero(sf: Any, prepared: Any, *a: Any, **kw: Any) -> str:
        vistos.append(prepared.notification_id)
        if prepared.notification_id == primero.id:
            raise OperationalError("UPDATE", {}, Exception("corte"))
        return await real(sf, prepared, *a, **kw)

    monkeypatch.setattr(sending, "_finish", roto_para_el_primero)

    resultado = await _pasar(fabrica, CanalFalso())

    assert (resultado.enviados, resultado.fallidos) == (1, 1)
    assert vistos.count(primero.id) == 2
    fila = await estado_de(fabrica, primero.id)
    assert (fila["status"], fila["attempts"]) == ("pending", 1)


async def test_cancelar_el_job_durante_el_envio_no_deja_el_aviso_sin_cerrar(
    fabrica: Fabrica,
) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    enviando = asyncio.Event()

    async def lento(_p: ChannelPayload) -> None:
        enviando.set()
        await asyncio.sleep(0.3)

    tarea = asyncio.create_task(_pasar(fabrica, CanalFalso(espia=lento)))
    await asyncio.wait_for(enviando.wait(), timeout=5)
    tarea.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tarea

    await _esperar_estado(fabrica, aviso.id, "sent")


async def _corromper_correo(fabrica: Fabrica, member_id: Any) -> None:
    async with fabrica() as sesion:
        await sesion.execute(
            text(
                "UPDATE members.members SET email = overlay(email placing "
                "CASE WHEN substr(email, length(email) - 8, 1) = 'A' THEN 'B' ELSE 'A' END "
                "from length(email) - 8 for 1) WHERE id = :i"
            ),
            {"i": member_id},
        )
        await sesion.commit()


async def test_una_fila_ilegible_no_bloquea_la_cola_y_acumula_intentos(fabrica: Fabrica) -> None:
    """S5-D230: un blob corrupto es de ESA fila: `failed`/`unknown` y el lote sigue."""
    await habilitar_correo(fabrica)
    regla = await regla_correo(fabrica)
    malo = await socio_con_correo(fabrica)
    bueno = await socio_con_correo(fabrica, "bueno@example.com", nombre="Ana")
    aviso_malo = await aviso_correo(fabrica, regla, malo)
    aviso_bueno = await aviso_correo(fabrica, regla, bueno)
    await _corromper_correo(fabrica, malo.id)
    canal = CanalFalso()

    primera = await _pasar(fabrica, canal)
    await _pasar(fabrica, canal)

    fila = await estado_de(fabrica, aviso_malo.id)
    assert (fila["status"], fila["attempts"], fila["last_error"]) == ("failed", 2, "unknown")
    assert (await estado_de(fabrica, aviso_bueno.id))["status"] == "sent"
    assert (primera.enviados, primera.fallidos) == (1, 1) and len(canal.enviados) == 1


async def test_el_sellado_a_mitad_de_lote_relanza_y_deja_lo_demas_intacto(
    fabrica: Fabrica,
) -> None:
    await habilitar_correo(fabrica)
    regla = await regla_correo(fabrica)
    primero = await aviso_correo(fabrica, regla, await socio_con_correo(fabrica))
    segundo = await aviso_correo(
        fabrica, regla, await socio_con_correo(fabrica, "dos@example.com", nombre="Ana")
    )
    llamadas: list[int] = []

    async def cargador(session: AsyncSession, member_id: Any) -> Any:
        llamadas.append(1)
        if len(llamadas) == 2:
            raise CryptoUnavailable("sealed")
        return await cargar_correo(session, member_id)

    with pytest.raises(CryptoUnavailable):
        await send_pending(fabrica, HOY, load_contact=cargador, channel=CanalFalso())

    estados = sorted([(await estado_de(fabrica, a.id))["status"] for a in (primero, segundo)])
    assert estados == ["pending", "sent"]
    assert {(await estado_de(fabrica, a.id))["attempts"] for a in (primero, segundo)} == {0, 1}


async def test_un_error_inesperado_en_un_aviso_no_derriba_el_lote(fabrica: Fabrica) -> None:
    """S5-D230: un `TypeError` (por ejemplo de un suscriptor) deja ESE aviso `failed`/`unknown`."""
    await habilitar_correo(fabrica)
    regla = await regla_correo(fabrica)
    uno = await aviso_correo(fabrica, regla, await socio_con_correo(fabrica))
    dos = await aviso_correo(
        fabrica, regla, await socio_con_correo(fabrica, "dos@example.com", nombre="Ana")
    )
    llamadas: list[int] = []

    async def cargador(session: AsyncSession, member_id: Any) -> Any:
        llamadas.append(1)
        if len(llamadas) == 1:
            raise TypeError("bug de un suscriptor con lucia.gomez@example.com")
        return await cargar_correo(session, member_id)

    resultado = await send_pending(fabrica, HOY, load_contact=cargador, channel=CanalFalso())

    filas = {f["id"]: f for f in await todos(fabrica)}
    estados = sorted((filas[a.id]["status"], filas[a.id]["last_error"] or "") for a in (uno, dos))
    assert estados == [("failed", "unknown"), ("sent", "")]
    assert (resultado.enviados, resultado.fallidos) == (1, 1)


async def test_canal_habilitado_sin_credenciales_deja_pending_y_lo_avisa(
    fabrica: Fabrica,
) -> None:
    """S5-D231: la omisión definitiva es solo cuando el admin apagó el canal."""
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    canal = CanalFalso(configured=False)

    resultado = await _pasar(fabrica, canal)

    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["skip_reason"], fila["attempts"]) == ("pending", None, 0)
    assert canal.enviados == []
    assert resultado == SendResult(0, 0, 0, 1, sin_credenciales=True)


async def test_canal_apagado_sigue_omitiendo_sin_marcar_credenciales(fabrica: Fabrica) -> None:
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(fabrica, await regla_correo(fabrica), miembro)

    resultado = await _pasar(fabrica, CanalFalso(configured=False))

    assert (await estado_de(fabrica, aviso.id))["skip_reason"] == "canal_no_configurado"
    assert resultado.sin_credenciales is False and resultado.omitidos == 1


def test_los_topes_por_corrida_son_500_avisos_y_480_segundos() -> None:
    assert (sending.NOTIFY_MAX_PER_RUN, sending.NOTIFY_SOFT_DEADLINE_S) == (500, 480)
    parametros = inspect.signature(send_pending).parameters
    assert parametros["max_per_run"].default == 500
    assert parametros["soft_deadline_s"].default == 480


async def test_el_plazo_blando_corta_el_lote_y_lo_restante_sigue_pendiente(
    fabrica: Fabrica,
) -> None:
    await habilitar_correo(fabrica)
    regla = await regla_correo(fabrica)
    for i in range(3):
        await aviso_correo(
            fabrica, regla, await socio_con_correo(fabrica, f"t{i}@example.com", nombre=f"T{i}")
        )
    relojes = iter([0.0, 0.0, 481.0, 481.0, 481.0, 481.0])
    canal = CanalFalso()

    resultado = await send_pending(
        fabrica,
        HOY,
        load_contact=cargar_correo,
        channel=canal,
        monotonic=lambda: next(relojes),
    )

    assert (resultado.enviados, resultado.pendientes) == (1, 2)
    assert sorted(f["attempts"] for f in await todos(fabrica)) == [0, 0, 1]


async def test_con_501_avisos_una_corrida_envia_500_y_deja_uno(fabrica: Fabrica) -> None:
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    regla = await regla_correo(fabrica)
    async with fabrica() as sesion:
        await sesion.execute(
            text(
                "INSERT INTO notifications.notifications (id, rule_id, member_id, membership_id, "
                "target_date, channel, status, rendered_subject, rendered_body, created_by) "
                "SELECT gen_random_uuid(), :r, :m, gen_random_uuid(), :d, 'email', 'pending', "
                "'Asunto', 'Cuerpo', :u FROM generate_series(1, 501)"
            ),
            {"r": regla.id, "m": miembro.id, "d": HOY, "u": SYSTEM_USER_ID},
        )
        await sesion.commit()

    async def sin_descifrar(_s: AsyncSession, _m: Any) -> Any:
        return Contact(first_name="X", phone=None, email=CORREO)

    canal = CanalFalso()
    resultado = await send_pending(fabrica, HOY, load_contact=sin_descifrar, channel=canal)

    assert (resultado.enviados, resultado.pendientes) == (500, 1)
    assert len(canal.enviados) == 500


async def test_un_asunto_con_salto_de_linea_queda_failed_sin_reintentos_ni_llamar_al_canal(
    fabrica: Fabrica, caplog: pytest.LogCaptureFixture
) -> None:
    """LOW 6 de B8: `core.mail` lo rechazaría siempre; no se gastan reintentos."""
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    aviso = await aviso_correo(
        fabrica,
        await regla_correo(fabrica),
        miembro,
        rendered_subject="Hola\r\nBcc: otro@example.com",
    )
    canal = CanalFalso()
    caido = eventos_de(_Fallido)
    caplog.set_level(logging.INFO)

    resultado = await _pasar(fabrica, canal)

    fila = await estado_de(fabrica, aviso.id)
    assert (fila["status"], fila["attempts"], fila["last_error"]) == ("failed", 3, "unknown")
    assert canal.enviados == [] and (resultado.fallidos, resultado.pendientes) == (1, 0)
    assert [e.notification_id for e in caido.vistos] == [aviso.id]
    assert any(getattr(r, "notification_id", None) == str(aviso.id) for r in caplog.records)
    assert "Bcc" not in caplog.text
