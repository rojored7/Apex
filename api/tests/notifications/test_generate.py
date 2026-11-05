"""`notifications.service.generate_today` (S5-B7, US-124; S5-D26, S5-D71, M-6, N-35). # Rojo B7

Contrato que fija el Rojo (las dudas, en el cuaderno):
- `generate_today(session, today) -> GenerateResult(generados, ya_renovaron, sin_consentimiento,
  sin_reglas)`; `today` es el "hoy" de Bogotá que pasa quien llama (nunca el reloj ni la fecha UTC).
- Reglas activas; fechas objetivo `today - 15 ... today`; el aviso de una regla para una membresía
  lleva `target_date = end_date + offset_days`. Una regla `membership_expiring` no genera para una
  membresía que ya terminó (`end_date < today`): para eso están las de vencida.
- N-35: las reglas de vencida no avisan a quien tiene una vigente, futura o pendiente de pago
  (`ya_renovaron` cuenta pares socio-regla).
- Sin canal (socio sin `data_consent_at`) no genera y se cuenta en `sin_consentimiento`; al
  registrarse el consentimiento la corrida siguiente lo recupera. Un socio dado de baja no genera y
  no se cuenta. El canal del aviso es el de la regla y solo se genera si el socio lo tiene efectivo
  (`members.service.channels_for`).
- Render con `{nombre} {plan} {vence} {dias}`: `vence` como `5 nov 2026`, `dias` absoluto. Un
  contexto que deje saltos de línea en el asunto (`TemplateError`) deja ese aviso `skipped` con
  `skip_reason = "plantilla_invalida"` (S5-D218) y no detiene al resto.
- Inserción ORM por aviso en `begin_nested()`: un duplicado es "ya existente"; el evento
  `NotificationQueued` solo sale de las filas nuevas y después del flush; cada fila deja `insert`
  en `audit_log` con el socio como sujeto; una transacción (commit) por lote de 200 socios.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.modules.members import service as members_service
from app.modules.notifications import generate, service
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import GenerateResult
from tests.factories.members import make_members
from tests.factories.memberships import make_memberships
from tests.factories.notifications import (
    EXPIRED,
    make_notification,
    make_rule,
    make_template,
)
from tests.factories.plans import make_plan
from tests.notifications._apoyo import contar, en_peticion
from tests.notifications._apoyo_avisos import (
    ANTES,
    HOY,
    T_AVISOS,
    avisos,
    canales,
    con_membresia,
    cuerpo_esperado,
    eventos_de,
    regla_aislada,
    reglas_por_defecto,
    socio,
)

pytestmark = pytest.mark.usefixtures("listo")


async def generar(session: AsyncSession, hoy: date = HOY) -> GenerateResult:
    return await en_peticion(session, SYSTEM_USER_ID, lambda: service.generate_today(session, hoy))


async def _auditoria(session: AsyncSession) -> list[dict[str, Any]]:
    consulta = text(
        "SELECT action, user_id, record_id, subject_member_id FROM audit.audit_log "
        "WHERE table_name = 'notifications.notifications' ORDER BY seq"
    )
    return [dict(f) for f in (await session.execute(consulta)).mappings()]


# Lo que genera -----------------------------------------------------------------------------------


async def test_genera_un_aviso_pendiente_con_el_texto_de_la_plantilla(
    session: AsyncSession,
) -> None:
    await reglas_por_defecto(session)
    plan = await make_plan(session, name="Mensual")
    lucia = await socio(session, nombre="Lucía")
    fin = HOY + timedelta(days=3)
    membresia = await con_membresia(session, lucia, plan, fin)

    resultado = await generar(session)

    assert resultado == GenerateResult(
        generados=1, ya_renovaron=0, sin_consentimiento=0, sin_reglas=False
    )
    [fila] = await avisos(session)
    assert fila["offset_days"] == -3
    assert fila["member_id"] == lucia.id and fila["membership_id"] == membresia.id
    assert fila["target_date"] == HOY
    assert (fila["channel"], fila["status"], fila["attempts"]) == ("whatsapp_link", "pending", 0)
    assert fila["rendered_subject"] == "Tu membresía vence pronto"
    assert fila["rendered_body"] == cuerpo_esperado("Lucía", "Mensual", fin, 3)
    assert (fila["last_error"], fila["sent_at"], fila["sent_by"], fila["skip_reason"]) == (
        None,
        None,
        None,
        None,
    )
    assert fila["created_by"] == SYSTEM_USER_ID


async def test_el_aviso_de_vencida_cuenta_los_dias_sin_signo(session: AsyncSession) -> None:
    await reglas_por_defecto(session)
    plan = await make_plan(session)
    ana = await socio(session, nombre="Ana")
    fin = HOY - timedelta(days=7)
    await con_membresia(session, ana, plan, fin)

    resultado = await generar(session)

    assert resultado.generados == 1
    [fila] = await avisos(session)
    assert (fila["offset_days"], fila["target_date"]) == (7, HOY)
    assert fila["rendered_subject"] == "Tu membresía venció"
    assert fila["rendered_body"] == cuerpo_esperado("Ana", "Mensual", fin, 7, EXPIRED)


async def test_varias_reglas_para_la_misma_membresia_dan_un_aviso_por_regla(
    session: AsyncSession,
) -> None:
    """Fin hoy: `Vence hoy` (0) hoy; `Vence en 3 días` (-3) ya cayó 3 días atrás y la membresía
    sigue vigente, así que también entra por la ventana de recuperación de 15 días."""
    await reglas_por_defecto(session)
    plan = await make_plan(session)
    ana = await socio(session)
    await con_membresia(session, ana, plan, HOY)

    resultado = await generar(session)

    filas = await avisos(session)
    assert [f["offset_days"] for f in filas] == [-3, 0]
    assert [f["target_date"] for f in filas] == [HOY - timedelta(days=3), HOY]
    assert resultado.generados == 2


# Idempotencia (RN-17) -----------------------------------------------------------------------------


async def test_dos_corridas_no_duplican_avisos_ni_auditoria_ni_eventos(
    session: AsyncSession,
) -> None:
    await reglas_por_defecto(session)
    plan = await make_plan(session)
    for dias in (3, -1, -7):
        await con_membresia(session, await socio(session), plan, HOY + timedelta(days=dias))
    capturados = eventos_de(service.NotificationQueued)

    primera = await generar(session)
    filas = await avisos(session)
    auditoria = await _auditoria(session)
    eventos = len(capturados.vistos)
    segunda = await generar(session)

    assert primera.generados == 3 and segunda.generados == 0
    assert await avisos(session) == filas
    assert await _auditoria(session) == auditoria
    assert len(capturados.vistos) == eventos == 3


async def test_un_aviso_ya_enviado_u_omitido_no_se_vuelve_a_generar(
    session: AsyncSession,
) -> None:
    await reglas_por_defecto(session)
    plan = await make_plan(session)
    await con_membresia(session, await socio(session), plan, HOY + timedelta(days=3))
    await generar(session)
    await session.execute(
        text("UPDATE notifications.notifications SET status = 'sent', sent_at = now()")
    )

    resultado = await generar(session)

    assert resultado.generados == 0
    assert await contar(session, T_AVISOS) == 1
    assert (await avisos(session))[0]["status"] == "sent"


async def test_una_fila_existente_cuenta_como_ya_creada_y_no_frena_a_las_demas(
    session: AsyncSession,
) -> None:
    """M-6/D71: el duplicado de una clave se resuelve en su `begin_nested()`; la sesión sigue
    sana y el resto del lote se inserta."""
    regla = await regla_aislada(session, "membership_expiring", -3)
    plan = await make_plan(session)
    fin = HOY + timedelta(days=3)
    ya = await socio(session, nombre="Ya")
    nueva = await socio(session, nombre="Nueva")
    existente = await con_membresia(session, ya, plan, fin)
    await con_membresia(session, nueva, plan, fin)
    await make_notification(
        session, regla, member_id=ya.id, membership_id=existente.id, target_date=HOY
    )
    capturados = eventos_de(service.NotificationQueued)

    resultado = await generar(session)

    assert resultado.generados == 1
    assert await contar(session, T_AVISOS) == 2
    assert [e.member_id for e in capturados.vistos] == [nueva.id]


# Ventana de 15 días (N-35) ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("dias_vencida", "se_genera"),
    [(0, False), (1, True), (8, True), (16, True), (17, False), (40, False)],
)
async def test_la_ventana_de_vencida_va_de_hoy_menos_15_a_hoy(
    session: AsyncSession, dias_vencida: int, se_genera: bool
) -> None:
    """Regla de vencida +1: `target_date = fin + 1`. Con fin `k` días atrás el objetivo es
    `hoy - k + 1`: entra de `k = 1` (hoy) a `k = 16` (hoy - 15); `k = 0` es futuro."""
    await regla_aislada(session, "membership_expired", 1, plantilla=EXPIRED)
    plan = await make_plan(session)
    await con_membresia(session, await socio(session), plan, HOY - timedelta(days=dias_vencida))

    resultado = await generar(session)

    assert resultado.generados == (1 if se_genera else 0)
    assert await contar(session, T_AVISOS) == (1 if se_genera else 0)


@pytest.mark.parametrize(("dias_para_fin", "se_genera"), [(3, True), (4, False), (10, False)])
async def test_la_regla_de_vence_en_3_dias_solo_genera_el_dia_que_toca(
    session: AsyncSession, dias_para_fin: int, se_genera: bool
) -> None:
    await regla_aislada(session, "membership_expiring", -3)
    plan = await make_plan(session)
    await con_membresia(session, await socio(session), plan, HOY + timedelta(days=dias_para_fin))

    resultado = await generar(session)

    assert resultado.generados == (1 if se_genera else 0)


async def test_una_regla_de_vencimiento_proximo_no_avisa_a_una_membresia_ya_terminada(
    session: AsyncSession,
) -> None:
    """Fin ayer: `fin - 3` cae dentro de la ventana, pero decir "vence en 3 días" a quien ya
    venció sería falso; eso lo cubren las reglas de vencida."""
    await regla_aislada(session, "membership_expiring", -3)
    plan = await make_plan(session)
    await con_membresia(session, await socio(session), plan, HOY - timedelta(days=1))

    resultado = await generar(session)

    assert resultado.generados == 0 and await contar(session, T_AVISOS) == 0


async def test_cada_dia_agrega_solo_lo_que_toca_ese_dia(session: AsyncSession) -> None:
    """Cruce de días: con fin el día D+3 las reglas -3, 0, +1, +7 y +15 caen en D, D+3, D+4, D+10 y
    D+18; correr cada día suma exactamente un aviso en esos días y nada en los demás."""
    await reglas_por_defecto(session)
    plan = await make_plan(session)
    fin = HOY + timedelta(days=3)
    await con_membresia(session, await socio(session), plan, fin)

    acumulado = 0
    esperado = {HOY: 1, HOY + timedelta(days=3): 1, HOY + timedelta(days=4): 1}
    for dia in range(0, 6):
        hoy = HOY + timedelta(days=dia)
        resultado = await generar(session, hoy)
        acumulado += resultado.generados
        assert resultado.generados == esperado.get(hoy, 0), hoy
    assert acumulado == 3
    assert [f["offset_days"] for f in await avisos(session)] == [-3, 0, 1]


async def test_usa_el_hoy_recibido_y_no_el_reloj(session: AsyncSession, reloj: FrozenClock) -> None:
    await regla_aislada(session, "membership_expiring", 0)
    plan = await make_plan(session)
    fin = HOY + timedelta(days=9)
    await con_membresia(session, await socio(session), plan, fin)

    assert (await generar(session, HOY)).generados == 0
    assert (await generar(session, fin)).generados == 1
    [fila] = await avisos(session)
    assert fila["target_date"] == fin


# Renovados (N-35) ---------------------------------------------------------------------------------


async def test_no_se_avisa_como_vencido_a_quien_ya_renovo(session: AsyncSession) -> None:
    await regla_aislada(session, "membership_expired", 1, plantilla=EXPIRED)
    plan = await make_plan(session)
    renovo = await socio(session, nombre="Renovó")
    no_renovo = await socio(session, nombre="NoRenovó")
    await con_membresia(session, renovo, plan, HOY - timedelta(days=1))
    await con_membresia(session, renovo, plan, HOY + timedelta(days=29), dias=30)
    sin_pagar = await socio(session, nombre="SinPagar")
    await con_membresia(session, sin_pagar, plan, HOY - timedelta(days=1))
    await con_membresia(
        session, sin_pagar, plan, HOY + timedelta(days=29), status="pending_payment"
    )
    sola = await con_membresia(session, no_renovo, plan, HOY - timedelta(days=1))

    resultado = await generar(session)

    assert resultado == GenerateResult(
        generados=1, ya_renovaron=2, sin_consentimiento=0, sin_reglas=False
    )
    [fila] = await avisos(session)
    assert (fila["member_id"], fila["membership_id"]) == (no_renovo.id, sola.id)


async def test_una_membresia_futura_tambien_cuenta_como_renovada(session: AsyncSession) -> None:
    await regla_aislada(session, "membership_expired", 1, plantilla=EXPIRED)
    plan = await make_plan(session)
    adelantado = await socio(session)
    await con_membresia(session, adelantado, plan, HOY - timedelta(days=1))
    await con_membresia(session, adelantado, plan, HOY + timedelta(days=40))

    resultado = await generar(session)

    assert (resultado.generados, resultado.ya_renovaron) == (0, 1)


# Consentimiento y canales (D31, N-33) -------------------------------------------------------------


async def test_sin_consentimiento_no_genera_y_se_cuenta(session: AsyncSession) -> None:
    await reglas_por_defecto(session)
    plan = await make_plan(session)
    sin = await socio(session, consentido=False)
    await con_membresia(session, sin, plan, HOY + timedelta(days=3))
    capturados = eventos_de(service.NotificationQueued)

    resultado = await generar(session)

    assert resultado == GenerateResult(
        generados=0, ya_renovaron=0, sin_consentimiento=1, sin_reglas=False
    )
    assert await contar(session, T_AVISOS) == 0 and capturados.vistos == []


async def test_al_registrar_el_consentimiento_la_corrida_siguiente_lo_recupera(
    session: AsyncSession, reloj: FrozenClock
) -> None:
    await regla_aislada(session, "membership_expiring", -3)
    plan = await make_plan(session)
    sin = await socio(session, consentido=False)
    await con_membresia(session, sin, plan, HOY + timedelta(days=3))
    assert (await generar(session)).sin_consentimiento == 1

    await session.execute(
        text("UPDATE members.members SET data_consent_at = :t WHERE id = :id"),
        {"t": reloj.now_utc(), "id": sin.id},
    )
    resultado = await generar(session)

    assert (resultado.generados, resultado.sin_consentimiento) == (1, 0)


async def test_un_socio_dado_de_baja_no_genera_ni_se_cuenta(session: AsyncSession) -> None:
    await regla_aislada(session, "membership_expiring", -3)
    plan = await make_plan(session)
    baja = await socio(session, deleted_at=ANTES)
    await con_membresia(session, baja, plan, HOY + timedelta(days=3))

    resultado = await generar(session)

    assert resultado == GenerateResult(
        generados=0, ya_renovaron=0, sin_consentimiento=0, sin_reglas=False
    )
    assert await contar(session, T_AVISOS) == 0


async def test_el_canal_del_aviso_es_el_de_la_regla_y_exige_que_el_socio_lo_tenga(
    session: AsyncSession,
) -> None:
    plantilla = await make_template(session)
    await make_rule(session, plantilla, name="WA", offset_days=-3, channel="whatsapp_link")
    await make_rule(session, plantilla, name="Correo", offset_days=-3, channel="email")
    plan = await make_plan(session)
    fin = HOY + timedelta(days=3)
    solo_wa = await socio(session, nombre="SoloWA")
    ambos = await socio(session, nombre="Ambos")
    solo_correo = await socio(session, nombre="SoloCorreo")
    for s in (solo_wa, ambos, solo_correo):
        await con_membresia(session, s, plan, fin)
    await canales(session, ambos, email=True)
    await canales(session, solo_correo, email=True, whatsapp_link=False)

    resultado = await generar(session)

    por_socio: dict[Any, set[str]] = {}
    for f in await avisos(session):
        por_socio.setdefault(f["member_id"], set()).add(f["channel"])
    assert por_socio == {
        solo_wa.id: {"whatsapp_link"},
        ambos.id: {"whatsapp_link", "email"},
        solo_correo.id: {"email"},
    }
    assert resultado.generados == 4 and resultado.sin_consentimiento == 0


async def test_sin_reglas_activas_no_hay_nada_que_generar(session: AsyncSession) -> None:
    await regla_aislada(session, "membership_expiring", -3, is_active=False)
    plan = await make_plan(session)
    await con_membresia(session, await socio(session), plan, HOY + timedelta(days=3))

    resultado = await generar(session)

    assert resultado == GenerateResult(
        generados=0, ya_renovaron=0, sin_consentimiento=0, sin_reglas=True
    )


# Render seguro (S5-D216) --------------------------------------------------------------------------


async def test_un_asunto_con_salto_de_linea_queda_omitido_por_plantilla_y_el_resto_sigue(
    session: AsyncSession,
) -> None:
    plantilla = await make_template(session, subject="Hola {nombre}", body="Cuerpo de {nombre}")
    await make_rule(session, plantilla, offset_days=-3, channel="whatsapp_link")
    plan = await make_plan(session)
    fin = HOY + timedelta(days=3)
    malo = await socio(session, nombre="Ana" + chr(0x2028) + "Falsa: urgente")
    bueno = await socio(session, nombre="Eva")
    await con_membresia(session, malo, plan, fin)
    await con_membresia(session, bueno, plan, fin)

    resultado = await generar(session)

    assert (resultado.generados, resultado.omitidos_por_plantilla) == (1, 1)
    por_socio = {fila["member_id"]: fila for fila in await avisos(session)}
    assert por_socio[bueno.id]["rendered_subject"] == "Hola Eva"
    assert por_socio[bueno.id]["status"] == "pending"
    assert (por_socio[malo.id]["status"], por_socio[malo.id]["skip_reason"]) == (
        "skipped",
        "plantilla_invalida",
    )


# Auditoría y eventos (M-6, D71) -------------------------------------------------------------------


async def test_cada_fila_nueva_deja_un_insert_en_audit_log_con_el_socio_como_sujeto(
    session: AsyncSession,
) -> None:
    await reglas_por_defecto(session)
    plan = await make_plan(session)
    s1, s2 = await socio(session, nombre="Uno"), await socio(session, nombre="Dos")
    await con_membresia(session, s1, plan, HOY + timedelta(days=3))
    await con_membresia(session, s2, plan, HOY - timedelta(days=7))

    await generar(session)

    filas = await avisos(session)
    auditoria = await _auditoria(session)
    assert len(auditoria) == len(filas) == 2
    assert {a["action"] for a in auditoria} == {"insert"}
    assert {a["user_id"] for a in auditoria} == {SYSTEM_USER_ID}
    assert {a["record_id"] for a in auditoria} == {f["id"] for f in filas}
    assert {a["subject_member_id"] for a in auditoria} == {s1.id, s2.id}


async def test_notification_queued_solo_lleva_ids_canal_y_fecha_y_sale_tras_el_flush(
    session: AsyncSession,
) -> None:
    await regla_aislada(session, "membership_expiring", -3)
    plan = await make_plan(session)
    fin = HOY + timedelta(days=3)
    uno = await socio(session)
    await con_membresia(session, uno, plan, fin)
    existencias: list[int] = []

    async def espiar(evento: service.NotificationQueued, s: AsyncSession) -> None:
        cuenta = await s.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.id == evento.notification_id)
        )
        existencias.append(int(cuenta or 0))

    events.subscribe(service.NotificationQueued, espiar)
    capturados = eventos_de(service.NotificationQueued)

    await generar(session)

    [fila] = await avisos(session)
    [evento] = capturados.vistos
    assert existencias == [1]
    assert (evento.notification_id, evento.member_id, evento.rule_id) == (
        fila["id"],
        uno.id,
        fila["rule_id"],
    )
    assert (evento.channel, evento.target_date) == ("whatsapp_link", HOY)
    assert "Lucía" not in repr(evento) and fila["rendered_body"] not in repr(evento)


# Lotes de 200 -------------------------------------------------------------------------------------


async def test_450_candidatos_se_procesan_en_tres_lotes_de_200(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await regla_aislada(session, "membership_expiring", -3)
    plan = await make_plan(session)
    socios = await make_members(session, 450, data_consent_at=ANTES)
    await make_memberships(
        session,
        450,
        plan,
        members=socios,
        status="active",
        start=HOY - timedelta(days=26),
        end=HOY + timedelta(days=3),
    )
    tamanos: list[int] = []
    original = members_service.channels_for

    async def espia(s: AsyncSession, ids: Any) -> Any:
        lote = list(ids)
        tamanos.append(len(lote))
        return await original(s, lote)

    monkeypatch.setattr(members_service, "channels_for", espia)

    resultado = await generar(session)

    assert generate.BATCH_SIZE == 200
    assert tamanos == [200, 200, 50]
    assert resultado.generados == 450 and await contar(session, T_AVISOS) == 450


async def test_cada_lote_se_confirma_antes_de_empezar_el_siguiente(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una transacción por lote: si el segundo lote falla, el primero ya quedó confirmado."""
    await regla_aislada(session, "membership_expiring", -3)
    plan = await make_plan(session)
    socios = await make_members(session, 5, data_consent_at=ANTES)
    await make_memberships(
        session,
        5,
        plan,
        members=socios,
        status="active",
        start=HOY - timedelta(days=26),
        end=HOY + timedelta(days=3),
    )
    monkeypatch.setattr(generate, "BATCH_SIZE", 2)
    original = members_service.channels_for
    llamadas: list[int] = []

    async def falla_en_el_segundo(s: AsyncSession, ids: Any) -> Any:
        llamadas.append(1)
        if len(llamadas) == 2:
            raise RuntimeError("falla simulada del segundo lote")
        return await original(s, list(ids))

    monkeypatch.setattr(members_service, "channels_for", falla_en_el_segundo)

    with pytest.raises(RuntimeError, match="segundo lote"):
        await generar(session)
    await session.rollback()

    assert await contar(session, T_AVISOS) == 2


# Revisiones de B7 (S5-D217 punto 3, S5-D223) ------------------------------------------------------


async def test_una_renovacion_pendiente_de_pago_cuenta_como_ya_renovo(
    session: AsyncSession,
) -> None:
    """S5-D217 (3): quien ya volvió (venta `pending_payment`) no recibe "venció"; se cuenta."""
    await regla_aislada(session, "membership_expired", 1, plantilla=EXPIRED)
    plan = await make_plan(session)
    vuelto = await socio(session)
    await con_membresia(session, vuelto, plan, HOY - timedelta(days=1))
    await con_membresia(session, vuelto, plan, HOY + timedelta(days=29), status="pending_payment")

    resultado = await generar(session)

    assert (resultado.generados, resultado.ya_renovaron) == (0, 1)
    assert await contar(session, T_AVISOS) == 0


async def test_sin_consentimiento_y_ya_renovaron_cuentan_socios_distintos(
    session: AsyncSession,
) -> None:
    """Un socio con dos reglas que dejan de generar cuenta una vez, no una por regla."""
    await reglas_por_defecto(session)
    plan = await make_plan(session)
    sin = await socio(session, consentido=False)
    await con_membresia(session, sin, plan, HOY)  # -3 y 0 caen en la ventana
    renovo = await socio(session)
    await con_membresia(session, renovo, plan, HOY - timedelta(days=7), dias=3)
    await con_membresia(session, renovo, plan, HOY - timedelta(days=1), dias=3)
    await con_membresia(session, renovo, plan, HOY + timedelta(days=29))

    resultado = await generar(session)

    assert (resultado.sin_consentimiento, resultado.ya_renovaron) == (1, 1)


async def test_un_error_de_integridad_distinto_de_la_clave_unica_no_se_traga(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Solo `uq_notifications_rule_membership_target` es "ya existente"; un CHECK se relanza."""
    from sqlalchemy.exc import IntegrityError

    plantilla = await make_template(session, subject="Hola {nombre}", body="x")
    await make_rule(session, plantilla, offset_days=-3, channel="whatsapp_link")
    plan = await make_plan(session)
    malo = await socio(session, nombre="Ana" + chr(0x2028) + "X")
    await con_membresia(session, malo, plan, HOY + timedelta(days=3))
    monkeypatch.setattr(generate, "INVALID_TEMPLATE", None)  # `skipped` sin motivo: viola el CHECK

    with pytest.raises(IntegrityError):
        await generar(session)
