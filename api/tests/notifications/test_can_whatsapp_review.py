"""Revisión de seguridad de S9-X1 (M1, L2 a L6): `can_whatsapp` ante datos raros y por HTTP."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.modules.notifications import service
from app.modules.notifications.schemas import NotificationFilters
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.notifications import make_notification, make_rule
from tests.notifications._apoyo import en_peticion
from tests.notifications._apoyo_avisos import (
    ANTES,
    AVISOS,
    HOY,
    HOY_RUTA,
    ajustar_canales,
    ruta_aviso,
    ruta_del_socio,
    ruta_omitir,
    ruta_wa,
    socio,
)

pytestmark = pytest.mark.usefixtures("listo", "canales_habilitados")
PAGINA = PageParams(limit=50, offset=0)
TELEFONO_OK = "300 765 4321"


async def _aviso(session: AsyncSession, *, estado: str = "pending", **del_socio: Any) -> Any:
    telefono = del_socio.pop("telefono", TELEFONO_OK)
    miembro = await socio(session, phone=telefono, **del_socio)
    regla = await make_rule(session)
    aviso = await make_notification(session, regla, member_id=miembro.id, status=estado)
    return miembro, aviso


async def _seccion_invalida(session: AsyncSession) -> None:
    """Un JSON guardado a mano que ya no valida (valor de tipo incorrecto y clave ajena)."""
    await session.execute(
        text(
            "UPDATE settings.settings_sections SET value = CAST(:v AS jsonb) WHERE key = 'channels'"
        ),
        {"v": '{"whatsapp": {"enabled": "tal vez", "ajena": 1}}'},
    )
    await session.commit()


# M1 -------------------------------------------------------------------------------------------


async def test_m1_seccion_channels_invalida_da_200_y_falso_en_las_cuatro_listas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await usuario_real("admin")
    miembro, aviso = await _aviso(session)
    await _seccion_invalida(session)

    with caplog.at_level(logging.WARNING):
        rutas = [HOY_RUTA, AVISOS, ruta_aviso(aviso.id), ruta_del_socio(miembro.id)]
        respuestas = [await app_http.get(r, headers=cabeceras(admin)) for r in rutas]

    assert [r.status_code for r in respuestas] == [200, 200, 200, 200]
    for r in respuestas:
        cuerpo = r.json()
        filas = cuerpo["items"] if "items" in cuerpo else [cuerpo]
        assert [f["can_whatsapp"] for f in filas] == [False]
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert "300 765" not in caplog.text and str(miembro.id) not in caplog.text


async def test_m1_skip_con_seccion_invalida_responde_y_queda_guardado(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    _, aviso = await _aviso(session)
    await _seccion_invalida(session)

    salida = await en_peticion(
        session, admin.id, lambda: service.skip(session, aviso.id, "Motivo", admin.id)
    )

    assert (salida.status, salida.can_whatsapp) == ("skipped", False)
    estado = (
        await session.execute(
            text("SELECT status FROM notifications.notifications WHERE id = :i"), {"i": aviso.id}
        )
    ).scalar_one()
    assert estado == "skipped"


# L2 -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["sent", "failed"])
async def test_l2_sent_y_failed_ofrecen_whatsapp_y_wa_link_funciona(
    session: AsyncSession, usuario_real: CrearUsuario, estado: str
) -> None:
    admin = await usuario_real("admin")
    _, aviso = await _aviso(session, estado=estado)

    assert (await service.get(session, aviso.id)).can_whatsapp is True
    salida = await en_peticion(
        session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id)
    )
    assert salida.url.startswith("https://wa.me/57")


# L3 -------------------------------------------------------------------------------------------


async def _conteos(session: AsyncSession) -> tuple[int, int]:
    await session.commit()
    ops = (await session.execute(text("SELECT count(*) FROM crypto.crypto_ops"))).scalar_one()
    audit = (await session.execute(text("SELECT count(*) FROM audit.audit_log"))).scalar_one()
    return ops, audit


async def test_l3_lecturas_no_dejan_filas_en_crypto_ops_ni_auditoria_y_wa_link_si(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    _, aviso = await _aviso(session)
    antes = await _conteos(session)

    await service.list(session, NotificationFilters(), PAGINA)
    await service.get(session, aviso.id)
    await service.today_list(session, HOY, PAGINA, None)
    assert await _conteos(session) == antes

    await en_peticion(session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id))
    ops, audit = await _conteos(session)
    assert ops > antes[0] and audit > antes[1]  # control positivo


# L4 -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("telefono", ["(601) 234 5678", "123 4567"])
async def test_l4_un_fijo_ofrece_whatsapp_pero_wa_link_responde_422_invalid_phone(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    telefono: str,
) -> None:
    """Caso ACEPTADO (S9-D36 L-5): `whatsapp_ready` no valida el formato (exigiría descifrar)."""
    admin = await usuario_real("admin")
    _, aviso = await _aviso(session, telefono=telefono)
    assert (await service.get(session, aviso.id)).can_whatsapp is True

    r = await app_http.post(ruta_wa(aviso.id), headers=cabeceras(admin))

    assert (r.status_code, r.json()["error"]["code"]) == (422, "invalid_phone")


# L6 -------------------------------------------------------------------------------------------

CASOS_HTTP = [
    pytest.param({"estado": "skipped"}, 409, "notification_closed", id="skipped"),
    pytest.param({"canal": "email"}, 409, "wrong_channel", id="canal"),
    pytest.param({"habilitado": False}, 409, "channel_disabled", id="apagado"),
    pytest.param({"consentido": False}, 400, "member_not_contactable", id="sin_autorizacion"),
    pytest.param(
        {"deleted_at": ANTES, "status": "inactive"}, 400, "member_not_contactable", id="baja"
    ),
    pytest.param({"telefono": None}, 422, "member_without_phone", id="sin_telefono"),
]


@pytest.mark.parametrize(("cambios", "http", "codigo"), CASOS_HTTP)
async def test_l6_cada_caso_falso_coincide_con_el_post_wa_link_por_http(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    cambios: dict[str, Any],
    http: int,
    codigo: str,
) -> None:
    admin = await usuario_real("admin")
    cambios = dict(cambios)
    estado = cambios.pop("estado", "pending")
    canal = cambios.pop("canal", "whatsapp_link")
    habilitado = cambios.pop("habilitado", True)
    telefono = cambios.pop("telefono", TELEFONO_OK)
    await ajustar_canales(session, whatsapp=habilitado, email=True)
    miembro = await socio(session, phone=telefono, **cambios)
    regla = await make_rule(session, channel=canal)
    aviso = await make_notification(session, regla, member_id=miembro.id, status=estado)
    visto = await app_http.get(ruta_aviso(aviso.id), headers=cabeceras(admin))
    assert visto.json()["can_whatsapp"] is False

    r = await app_http.post(ruta_wa(aviso.id), headers=cabeceras(admin))

    assert r.json()["error"]["code"] == codigo, r.text
    assert r.status_code == http


async def test_l6_con_verdadero_el_post_wa_link_responde_200(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    _, aviso = await _aviso(session)
    visto = await app_http.get(ruta_aviso(aviso.id), headers=cabeceras(admin))
    assert visto.json()["can_whatsapp"] is True

    r = await app_http.post(ruta_wa(aviso.id), headers=cabeceras(admin))

    assert r.status_code == 200 and r.json()["url"].startswith("https://wa.me/57")


async def test_l6_omitir_por_http_devuelve_can_whatsapp_falso(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    _, aviso = await _aviso(session)

    r = await app_http.post(
        ruta_omitir(aviso.id), headers=cabeceras(admin), json={"reason": "Motivo"}
    )

    assert r.status_code == 200 and r.json()["can_whatsapp"] is False
