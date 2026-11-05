"""Avisos por HTTP (S5-B7, US-124, US-127 a US-130; S5-D27, S5-D59, S5-D92). # Rojo B7

- Seis rutas nuevas en el router plano de `notifications`: `GET /notifications/today` (registrada
  ANTES de `/notifications/{notification_id}`), `GET /notifications`, `GET /notifications/{id}`,
  `POST /notifications/{id}/wa-link`, `POST /notifications/{id}/skip` y
  `GET /members/{member_id}/notifications`.
- Roles: admin y coach hacen todo (incluido omitir y pedir el enlace); `member` 403; sin token 401.
- Contrato: claves exactas de `NotificationOut`, `Cache-Control: no-store`, listas
  `{items, total, limit, offset}` con `q`, `limit` (1..200), `offset`; filtros `status`, `channel`,
  `rule_id`, `from` y `to`; `wa-link` responde solo `{url}`.
- 422 con `field` (`reason` de 3 a 500 visibles, filtros fuera de la lista), 404, 409
  (`notification_closed`, `wrong_channel`) y 422 `member_without_phone`.
- Topes: `skip` consume `notifications-write` (30 por minuto); `wa-link`, `members-reveal` (30 por
  minuto); lecturas, `staff-read` (120); una búsqueda con `q` suma `members-search` (60).
- `/notifications/today` usa el "hoy" de Bogotá del reloj en el momento de la petición.
- OpenAPI: los códigos exactos de cada operación.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.modules.notifications.router import router
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.notifications import make_notification, make_rule, make_template
from tests.members._apoyo import auditoria_del_socio
from tests.notifications._apoyo_avisos import (
    ANTES,
    AVISOS,
    CAMPOS_AVISO,
    HOY,
    HOY_RUTA,
    TELEFONO,
    TELEFONO_DIGITOS,
    ruta_aviso,
    ruta_del_socio,
    ruta_omitir,
    ruta_wa,
    socio,
)

pytestmark = pytest.mark.usefixtures("listo")

RUTAS_NUEVAS = {
    ("GET", "/notifications/today"),
    ("GET", "/notifications"),
    ("GET", "/notifications/{notification_id}"),
    ("POST", "/notifications/{notification_id}/wa-link"),
    ("POST", "/notifications/{notification_id}/skip"),
    ("GET", "/members/{member_id}/notifications"),
}
TOPE_ESCRITURAS = 30
TOPE_REVEAL = 30
TOPE_LECTURAS = 120
TOPE_BUSQUEDAS = 60


# Estructura -------------------------------------------------------------------------------------


def test_el_router_publica_las_seis_rutas_de_avisos() -> None:
    publicadas = {
        (metodo, ruta.path)
        for ruta in router.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
    }
    assert RUTAS_NUEVAS <= publicadas
    assert len(publicadas) == 9 + len(RUTAS_NUEVAS)


def test_today_se_registra_antes_de_la_ruta_por_id() -> None:
    orden = [r.path for r in router.routes if isinstance(r, APIRoute)]
    assert orden.index("/notifications/today") < orden.index("/notifications/{notification_id}")


# Datos ------------------------------------------------------------------------------------------


async def _datos(session: AsyncSession) -> dict[str, Any]:
    """Un socio con teléfono y tres avisos pendientes de una regla por WhatsApp."""
    miembro = await socio(session, phone=TELEFONO, nombre="Lucía", apellido="Gómez")
    regla = await make_rule(session)
    avisos = [
        await make_notification(session, regla, member_id=miembro.id, rendered_body=f"Hola {i}")
        for i in range(3)
    ]
    return {"socio_id": miembro.id, "regla": regla, "avisos": avisos}


def _operaciones(datos: dict[str, Any]) -> list[tuple[str, str, dict[str, Any] | None]]:
    ver, enlace, omitir = (a.id for a in datos["avisos"])
    return [
        ("GET", HOY_RUTA, None),
        ("GET", AVISOS, None),
        ("GET", ruta_aviso(ver), None),
        ("POST", ruta_wa(enlace), None),
        ("POST", ruta_omitir(omitir), {"reason": "No viene esta semana"}),
        ("GET", ruta_del_socio(datos["socio_id"]), None),
    ]


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_pueden_las_seis_operaciones(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    datos = await _datos(session)
    for metodo, ruta, cuerpo in _operaciones(datos):
        r = await app_http.request(metodo, ruta, json=cuerpo, headers=cabeceras(quien))
        assert r.status_code == 200, (metodo, ruta, r.text)
        assert r.headers["cache-control"] == "no-store", (metodo, ruta)


async def test_member_recibe_403_en_todo_sin_efectos(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    quien = await usuario_real("member")
    datos = await _datos(session)
    for metodo, ruta, cuerpo in _operaciones(datos):
        r = await app_http.request(metodo, ruta, json=cuerpo, headers=cabeceras(quien))
        assert r.status_code == 403, (metodo, ruta, r.text)
        assert r.json()["error"]["code"] == "forbidden"
    estados = await session.execute(text("SELECT status FROM notifications.notifications"))
    assert {f[0] for f in estados} == {"pending"}
    assert await auditoria_del_socio(session, datos["socio_id"], "reveal") == []


async def test_sin_token_todo_da_401(app_http: AsyncClient, session: AsyncSession) -> None:
    datos = await _datos(session)
    for metodo, ruta, cuerpo in _operaciones(datos):
        r = await app_http.request(metodo, ruta, json=cuerpo)
        assert r.status_code == 401, (metodo, ruta, r.text)
        assert r.json()["error"]["code"] == "unauthorized"


# Lecturas ---------------------------------------------------------------------------------------


async def test_hoy_y_el_historial_devuelven_la_pagina_con_el_contrato(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    datos = await _datos(session)
    for ruta in (HOY_RUTA, AVISOS, ruta_del_socio(datos["socio_id"])):
        r = await app_http.get(ruta, headers=cabeceras(admin))
        assert r.status_code == 200, (ruta, r.text)
        pagina = r.json()
        assert set(pagina) == {"items", "total", "limit", "offset"} and pagina["total"] == 3
        for fila in pagina["items"]:
            assert set(fila) == CAMPOS_AVISO, ruta
            assert fila["member_name"] == "Lucía Gómez"
        assert TELEFONO_DIGITOS not in r.text and "@" not in r.text


async def test_el_detalle_devuelve_el_aviso_y_404_si_no_existe(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    datos = await _datos(session)
    aviso = datos["avisos"][0]

    r = await app_http.get(ruta_aviso(aviso.id), headers=cabeceras(admin))
    assert r.status_code == 200 and set(r.json()) == CAMPOS_AVISO
    assert r.json()["id"] == str(aviso.id)

    r = await app_http.get(ruta_aviso(uuid4()), headers=cabeceras(admin))
    assert r.status_code == 404 and r.json()["error"]["code"] == "notification_not_found"
    r = await app_http.get(ruta_aviso("no-es-uuid"), headers=cabeceras(admin))
    assert r.status_code == 422


async def test_today_no_se_confunde_con_un_id(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    await _datos(session)
    r = await app_http.get(HOY_RUTA, headers=cabeceras(admin))
    assert r.status_code == 200 and "items" in r.json()


async def test_los_filtros_del_historial_llegan_al_service(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    regla = await make_rule(session)
    ana = await socio(session, nombre="Ana")
    objetivo = await make_notification(
        session, regla, member_id=ana.id, status="failed", target_date=HOY - timedelta(days=2)
    )
    await make_notification(session, regla, status="sent", target_date=HOY)
    cab = cabeceras(admin)

    r = await app_http.get(
        AVISOS,
        params={
            "status": "failed",
            "channel": "whatsapp_link",
            "rule_id": str(regla.id),
            "from": str(HOY - timedelta(days=3)),
            "to": str(HOY - timedelta(days=1)),
            "q": "ana",
            "limit": 10,
        },
        headers=cab,
    )

    assert r.status_code == 200, r.text
    assert [f["id"] for f in r.json()["items"]] == [str(objetivo.id)]
    assert (r.json()["limit"], r.json()["offset"]) == (10, 0)


COMUNES = [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"q": "a\x00b"}]
SOLO_HISTORIAL = [
    {"status": "queued"},
    {"channel": "sms"},
    {"rule_id": "no-es-uuid"},
    {"from": "ayer"},
    {"to": "2026-13-45"},
]
INVALIDOS = [(AVISOS, p) for p in COMUNES + SOLO_HISTORIAL] + [(HOY_RUTA, p) for p in COMUNES]


@pytest.mark.parametrize(("ruta", "params"), INVALIDOS)
async def test_parametros_invalidos_dan_422(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    ruta: str,
    params: dict[str, Any],
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.get(ruta, params=params, headers=cabeceras(admin))
    assert r.status_code == 422, (params, r.text)


async def test_today_y_la_pestana_aceptan_q_como_el_historial(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    datos = await _datos(session)
    otro = await socio(session, nombre="Marta", apellido="Ríos")
    await make_notification(session, datos["regla"], member_id=otro.id)
    cab = cabeceras(admin)

    hoy = await app_http.get(HOY_RUTA, params={"q": "marta"}, headers=cab)
    lista = await app_http.get(AVISOS, params={"q": "marta"}, headers=cab)

    assert hoy.json()["total"] == 1 and lista.json()["total"] == 1


async def test_la_pestana_de_un_socio_inexistente_da_404_y_la_de_uno_de_baja_funciona(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    baja = await socio(session, deleted_at=ANTES)
    baja_id = baja.id  # la petición 404 hace rollback y expira el ORM de la prueba
    await make_notification(session, await make_rule(session), member_id=baja_id)

    r = await app_http.get(ruta_del_socio(uuid4()), headers=cabeceras(admin))
    assert r.status_code == 404 and r.json()["error"]["code"] == "member_not_found"
    r = await app_http.get(ruta_del_socio(baja_id), headers=cabeceras(admin))
    assert r.status_code == 200 and r.json()["total"] == 1


async def test_today_usa_el_hoy_de_bogota_al_momento_de_la_peticion(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    """A las 23:30 de Bogotá del 21 (04:30Z del 22) todavía es 21; pasada la medianoche local
    (05:30Z) ya es 22 y entra el aviso del 22 (el del 21 sigue pendiente, S5-D219)."""
    regla = await make_rule(session)
    ana, eva = await socio(session, nombre="Ana"), await socio(session, nombre="Eva")
    del_21 = await make_notification(
        session, regla, member_id=ana.id, status="pending", target_date=HOY
    )
    del_22 = await make_notification(
        session, regla, member_id=eva.id, status="pending", target_date=HOY + timedelta(days=1)
    )
    reloj.advance(hours=13, minutes=30)
    antes = await app_http.get(HOY_RUTA, headers=cabeceras(await usuario_real("admin")))
    reloj.advance(hours=1)
    despues = await app_http.get(HOY_RUTA, headers=cabeceras(await usuario_real("coach")))

    assert [f["id"] for f in antes.json()["items"]] == [str(del_21.id)]
    # S5-D219: el pendiente del 21 sigue por avisar (ventana de 15 días); el del 22 entra.
    assert [f["id"] for f in despues.json()["items"]] == [str(del_22.id), str(del_21.id)]


# wa-link ----------------------------------------------------------------------------------------


async def test_wa_link_responde_solo_la_url_marca_sent_y_audita_el_reveal(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    datos = await _datos(session)
    aviso = datos["avisos"][0]

    r = await app_http.post(ruta_wa(aviso.id), headers=cabeceras(coach))

    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert set(r.json()) == {"url"}
    assert r.json()["url"].startswith(f"https://wa.me/57{TELEFONO_DIGITOS}?text=")
    estado = (
        await session.execute(
            text("SELECT status, sent_by FROM notifications.notifications WHERE id = :i"),
            {"i": aviso.id},
        )
    ).one()
    assert tuple(estado) == ("sent", coach.id)
    reveals = await auditoria_del_socio(session, datos["socio_id"], "reveal")
    assert [x["after"] for x in reveals] == [{"field": "phone", "purpose": "notify"}]


async def test_wa_link_es_un_post_y_el_get_no_existe(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    datos = await _datos(session)
    r = await app_http.get(ruta_wa(datos["avisos"][0].id), headers=cabeceras(admin))
    assert r.status_code == 405


async def test_wa_link_traduce_los_rechazos_del_service(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    cab = cabeceras(admin)
    conocido = await socio(session, phone=TELEFONO)
    sin_telefono = await socio(session, phone=None)
    plantilla = await make_template(session)
    omitido = await make_notification(
        session, await make_rule(session, plantilla), member_id=conocido.id, status="skipped"
    )
    de_correo = await make_notification(
        session, await make_rule(session, plantilla, channel="email"), member_id=conocido.id
    )
    sin_numero = await make_notification(
        session, await make_rule(session, plantilla, offset_days=0), member_id=sin_telefono.id
    )

    casos = [
        (omitido.id, 409, "notification_closed"),
        (de_correo.id, 409, "wrong_channel"),
        (sin_numero.id, 422, "member_without_phone"),
        (uuid4(), 404, "notification_not_found"),
    ]
    for aviso_id, estado, codigo in casos:
        r = await app_http.post(ruta_wa(aviso_id), headers=cab)
        assert (r.status_code, r.json()["error"]["code"]) == (estado, codigo), r.text
        assert TELEFONO_DIGITOS not in r.text


# skip -------------------------------------------------------------------------------------------


async def test_skip_devuelve_el_aviso_omitido_con_el_motivo_recortado(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    datos = await _datos(session)
    aviso = datos["avisos"][0]

    r = await app_http.post(
        ruta_omitir(aviso.id), json={"reason": "  Ya pagó en caja  "}, headers=cabeceras(coach)
    )

    assert r.status_code == 200, r.text
    assert set(r.json()) == CAMPOS_AVISO
    assert (r.json()["status"], r.json()["skip_reason"]) == ("skipped", "Ya pagó en caja")


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"reason": ""},
        {"reason": "ab"},
        {"reason": "   "},
        {"reason": "x" * 501},
        {"reason": "con\x00control"},
        {"reason": "ok ok", "status": "sent"},
        {"reason": 12345},
    ],
)
async def test_skip_con_un_cuerpo_invalido_da_422_y_no_cambia_el_aviso(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    cuerpo: dict[str, Any],
) -> None:
    admin = await usuario_real("admin")
    datos = await _datos(session)
    aviso = datos["avisos"][0]

    r = await app_http.post(ruta_omitir(aviso.id), json=cuerpo, headers=cabeceras(admin))

    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    estado = await session.scalar(
        text("SELECT status FROM notifications.notifications WHERE id = :i"), {"i": aviso.id}
    )
    assert estado == "pending"


@pytest.mark.parametrize("largo", [3, 500])
async def test_skip_acepta_los_extremos_de_3_y_500_caracteres(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    largo: int,
) -> None:
    admin = await usuario_real("admin")
    datos = await _datos(session)
    r = await app_http.post(
        ruta_omitir(datos["avisos"][0].id), json={"reason": "m" * largo}, headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text


async def test_skip_de_un_aviso_cerrado_da_409_y_de_uno_inexistente_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    cab = cabeceras(admin)
    regla = await make_rule(session)
    enviado = await make_notification(session, regla, status="sent")

    r = await app_http.post(ruta_omitir(enviado.id), json={"reason": "Tarde ya"}, headers=cab)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "notification_closed")
    r = await app_http.post(ruta_omitir(uuid4()), json={"reason": "No existe"}, headers=cab)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "notification_not_found")


# Topes ------------------------------------------------------------------------------------------


async def test_el_skip_31_del_minuto_da_429(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin, otro = await usuario_real("admin"), await usuario_real("admin")
    datos = await _datos(session)
    ruta = ruta_omitir(datos["avisos"][0].id)
    cab = cabeceras(admin)
    for i in range(TOPE_ESCRITURAS):
        r = await app_http.post(ruta, json={"reason": "Motivo"}, headers=cab)
        assert r.status_code in (200, 409), (i, r.text)
    r = await app_http.post(ruta, json={"reason": "Motivo"}, headers=cab)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    r = await app_http.post(ruta, json={"reason": "Motivo"}, headers=cabeceras(otro))
    assert r.status_code == 409  # el tope es por usuario


async def test_el_wa_link_31_del_minuto_da_429(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    datos = await _datos(session)
    ruta = ruta_wa(datos["avisos"][0].id)
    cab = cabeceras(coach)
    for i in range(TOPE_REVEAL):
        r = await app_http.post(ruta, headers=cab)
        assert r.status_code == 200, (i, r.text)
    r = await app_http.post(ruta, headers=cab)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"


async def test_la_lectura_121_del_minuto_da_429_y_las_cuatro_lecturas_comparten_staff_read(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    datos = await _datos(session)
    cab = cabeceras(coach)
    for i in range(TOPE_LECTURAS):
        r = await app_http.get(HOY_RUTA, headers=cab)
        assert r.status_code == 200, (i, r.text)
    for ruta in (HOY_RUTA, AVISOS, ruta_aviso(datos["avisos"][0].id), ruta_del_socio(uuid4())):
        r = await app_http.get(ruta, headers=cab)
        assert r.status_code == 429, (ruta, r.text)


async def test_la_busqueda_con_q_suma_el_tope_de_members_search(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    await _datos(session)
    cab = cabeceras(coach)
    for i in range(TOPE_BUSQUEDAS):
        r = await app_http.get(AVISOS, params={"q": "luc"}, headers=cab)
        assert r.status_code == 200, (i, r.text)
    r = await app_http.get(HOY_RUTA, params={"q": "luc"}, headers=cab)
    assert r.status_code == 429, r.text
    r = await app_http.get(AVISOS, headers=cab)
    assert r.status_code == 200, "sin q no consume members-search"


# OpenAPI ----------------------------------------------------------------------------------------

CODIGOS = {
    ("get", "/api/v1/notifications/today"): {"200", "401", "403", "422", "429"},
    ("get", "/api/v1/notifications"): {"200", "401", "403", "422", "429"},
    ("get", "/api/v1/notifications/{notification_id}"): {
        "200",
        "401",
        "403",
        "404",
        "422",
        "429",
    },
    ("post", "/api/v1/notifications/{notification_id}/wa-link"): {
        "200",
        "400",  # MemberNotContactable (socio dado de baja o sin autorización)
        "401",
        "403",
        "404",
        "409",
        "422",
        "429",
    },
    ("post", "/api/v1/notifications/{notification_id}/skip"): {
        "200",
        "401",
        "403",
        "404",
        "409",
        "422",
        "429",
    },
    ("get", "/api/v1/members/{member_id}/notifications"): {
        "200",
        "401",
        "403",
        "404",
        "422",
        "429",
    },
}


@pytest.mark.parametrize(("metodo", "ruta"), sorted(CODIGOS), ids=lambda v: str(v))
def test_el_openapi_declara_los_codigos_exactos(
    api_prueba: FastAPI, metodo: str, ruta: str
) -> None:
    operacion = api_prueba.openapi()["paths"][ruta][metodo]
    assert set(operacion["responses"]) == CODIGOS[(metodo, ruta)] | {"500", "503"}


def test_el_openapi_publica_los_filtros_del_historial_con_sus_alias(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"]["/api/v1/notifications"]["get"]
    parametros = {p["name"] for p in operacion["parameters"]}
    assert {"q", "status", "channel", "rule_id", "from", "to", "limit", "offset"} <= parametros


def test_wa_link_declara_el_422_de_telefono_y_el_rechazo_de_contacto(settings_prueba: Any) -> None:
    from app.main import create_app

    respuestas = create_app(settings_prueba, run_migrations_on_startup=False).openapi()["paths"][
        "/api/v1/notifications/{notification_id}/wa-link"
    ]
    assert {"400", "404", "409", "422", "429"} <= set(respuestas["post"]["responses"])
