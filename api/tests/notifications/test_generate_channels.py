"""Generación y los ajustes de Canales (S5-V11c; S5-D265a, S5-D266). # Rojo V11c

Contrato que fija el Rojo:
- S5-D265a: si el canal de la regla está deshabilitado en `settings.channels` (`email.enabled` o
  `whatsapp.enabled` falsos, o sin fila: sin fila = apagado, S5-D231), `generate_today` crea el
  aviso `skipped` con `skip_reason = "canal_no_configurado"`; con el canal habilitado, `pending`.
  Es idempotente (la segunda corrida no crea filas). Coherente con `plantilla_invalida` (B7), un
  aviso `skipped` NO emite `NotificationQueued` y no cuenta en `generados`.
- S5-D266: socio con consentimiento que desactivó el canal de la regla en sus preferencias: aviso
  `skipped` con `skip_reason = "canal_desactivado_socio"` (no cuenta en `sin_consentimiento`).
  Sin consentimiento no hay fila (D54, `sin_consentimiento`); dado de baja, ninguna (D225).
- `today_list` y `today_count` no cuentan los `skipped`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID
from app.core.pagination import PageParams
from app.modules.notifications import generate, service
from app.modules.notifications.schemas import GenerateResult
from tests.factories.plans import make_plan
from tests.notifications._apoyo import contar, en_peticion
from tests.notifications._apoyo_avisos import (
    ANTES,
    HOY,
    T_AVISOS,
    ajustar_canales,
    avisos,
    canales,
    con_membresia,
    eventos_de,
    regla_aislada,
    socio,
)

pytestmark = pytest.mark.usefixtures("listo")

NO_CONFIGURADO = "canal_no_configurado"
DESACTIVADO_SOCIO = "canal_desactivado_socio"


async def generar(session: AsyncSession, hoy: date = HOY) -> GenerateResult:
    return await en_peticion(session, SYSTEM_USER_ID, lambda: service.generate_today(session, hoy))


async def _escenario(
    session: AsyncSession,
    canal: str,
    *,
    preferencias: dict[str, bool] | None = None,
    **socio_kw: Any,
) -> Any:
    """Una regla `canal` (vence en 3 días) y un socio con una membresía que termina en 3 días."""
    await regla_aislada(session, "membership_expiring", -3, channel=canal)
    plan = await make_plan(session)
    miembro = await socio(session, **socio_kw)
    if preferencias:
        await canales(session, miembro, **preferencias)
    await con_membresia(session, miembro, plan, HOY + timedelta(days=3))
    return miembro


def test_las_constantes_de_motivo_son_las_de_la_decision() -> None:
    assert generate.SKIP_CHANNEL_NOT_CONFIGURED == NO_CONFIGURADO
    assert generate.SKIP_MEMBER_CHANNEL_OFF == DESACTIVADO_SOCIO


# S5-D265a ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("canal", "ajustes"),
    [
        ("whatsapp_link", {"whatsapp": False, "email": True}),
        ("email", {"email": False, "whatsapp": True}),
    ],
)
async def test_con_el_canal_de_la_regla_deshabilitado_el_aviso_nace_skipped(
    session: AsyncSession, canal: str, ajustes: dict[str, bool]
) -> None:
    await ajustar_canales(session, **ajustes)
    miembro = await _escenario(session, canal, preferencias={"email": True})

    resultado = await generar(session)

    assert resultado.generados == 0
    [fila] = await avisos(session)
    assert (fila["channel"], fila["status"], fila["skip_reason"]) == (
        canal,
        "skipped",
        NO_CONFIGURADO,
    )
    assert fila["member_id"] == miembro.id and fila["attempts"] == 0
    assert fila["sent_at"] is None


@pytest.mark.parametrize("canal", ["whatsapp_link", "email"])
async def test_sin_fila_de_channels_el_canal_esta_apagado_y_el_aviso_nace_skipped(
    session: AsyncSession, canal: str
) -> None:
    await _escenario(session, canal, preferencias={"email": True})

    resultado = await generar(session)

    assert resultado.generados == 0
    [fila] = await avisos(session)
    assert (fila["status"], fila["skip_reason"]) == ("skipped", NO_CONFIGURADO)


@pytest.mark.parametrize(
    ("canal", "ajustes"),
    [("whatsapp_link", {"whatsapp": True}), ("email", {"email": True})],
)
async def test_con_el_canal_habilitado_el_aviso_nace_pending(
    session: AsyncSession, canal: str, ajustes: dict[str, bool]
) -> None:
    await ajustar_canales(session, **ajustes)
    await _escenario(session, canal, preferencias={"email": True})

    resultado = await generar(session)

    assert resultado.generados == 1
    [fila] = await avisos(session)
    assert (fila["status"], fila["skip_reason"]) == ("pending", None)


async def test_la_segunda_corrida_no_crea_filas_nuevas_de_los_omitidos(
    session: AsyncSession,
) -> None:
    await _escenario(session, "whatsapp_link")
    await generar(session)
    antes = await contar(session, T_AVISOS)

    segunda = await generar(session)

    assert antes == 1
    assert await contar(session, T_AVISOS) == 1
    assert segunda.generados == 0


async def test_un_aviso_skipped_por_canal_no_emite_notification_queued(
    session: AsyncSession,
) -> None:
    await ajustar_canales(session, whatsapp=False)
    await _escenario(session, "whatsapp_link")
    capturados = eventos_de(service.NotificationQueued)

    await generar(session)

    assert capturados.vistos == []
    assert await contar(session, T_AVISOS) == 1


async def test_el_canal_apagado_de_otra_regla_no_afecta_a_la_de_whatsapp(
    session: AsyncSession,
) -> None:
    """Con solo el correo apagado, una regla de WhatsApp sigue generando `pending`."""
    await ajustar_canales(session, whatsapp=True, email=False)
    await _escenario(session, "whatsapp_link")

    resultado = await generar(session)

    assert resultado.generados == 1
    [fila] = await avisos(session)
    assert fila["status"] == "pending"


# S5-D266 -----------------------------------------------------------------------------------------


async def test_con_consentimiento_y_whatsapp_desactivado_por_el_socio_el_aviso_nace_skipped(
    session: AsyncSession,
) -> None:
    await ajustar_canales(session, whatsapp=True)
    miembro = await _escenario(session, "whatsapp_link", preferencias={"whatsapp_link": False})
    capturados = eventos_de(service.NotificationQueued)

    resultado = await generar(session)

    assert resultado == GenerateResult(
        generados=0, ya_renovaron=0, sin_consentimiento=0, sin_reglas=False
    )
    [fila] = await avisos(session)
    assert (fila["member_id"], fila["status"], fila["skip_reason"]) == (
        miembro.id,
        "skipped",
        DESACTIVADO_SOCIO,
    )
    assert capturados.vistos == []


async def test_el_aviso_omitido_por_el_socio_es_idempotente(session: AsyncSession) -> None:
    await ajustar_canales(session, whatsapp=True)
    await _escenario(session, "whatsapp_link", preferencias={"whatsapp_link": False})
    await generar(session)

    await generar(session)

    assert await contar(session, T_AVISOS) == 1


async def test_sin_consentimiento_no_se_crea_fila_y_se_cuenta_aparte(
    session: AsyncSession,
) -> None:
    await ajustar_canales(session, whatsapp=True)
    await _escenario(session, "whatsapp_link", consentido=False)

    resultado = await generar(session)

    assert resultado.sin_consentimiento == 1 and resultado.generados == 0
    assert await contar(session, T_AVISOS) == 0


async def test_un_socio_dado_de_baja_no_deja_fila_ni_se_cuenta(session: AsyncSession) -> None:
    await ajustar_canales(session, whatsapp=True)
    await _escenario(session, "whatsapp_link", deleted_at=ANTES)

    resultado = await generar(session)

    assert resultado == GenerateResult(
        generados=0, ya_renovaron=0, sin_consentimiento=0, sin_reglas=False
    )
    assert await contar(session, T_AVISOS) == 0


async def test_today_list_y_today_count_no_cuentan_los_skipped(session: AsyncSession) -> None:
    await ajustar_canales(session, whatsapp=True)
    await regla_aislada(session, "membership_expiring", -3)
    plan = await make_plan(session)
    activo = await socio(session, nombre="Activa")
    apagado = await socio(session, nombre="Apagado")
    await canales(session, apagado, whatsapp_link=False)
    for miembro in (activo, apagado):
        await con_membresia(session, miembro, plan, HOY + timedelta(days=3))
    await generar(session)

    pagina = await service.today_list(session, HOY, PageParams(limit=50, offset=0), None)

    assert await contar(session, T_AVISOS) == 2
    assert [a.member_id for a in pagina.items] == [activo.id]
    assert await service.today_count(session, HOY) == 1
