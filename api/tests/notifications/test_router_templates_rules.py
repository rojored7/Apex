"""Plantillas y reglas de aviso por HTTP (S5-B6, US-120 y US-121; S5-D24, S5-D25). # Rojo B6

- Nueve rutas (desde B7 el router suma las de avisos); `POST /notification-templates/preview`
  va antes de `/{template_id}`.
- Roles: el admin escribe; el coach lee y recibe 403 al escribir (sin efectos); `member` 403 en
  todo; sin token 401.
- Contrato: claves exactas de `TemplateOut` y `RuleOut`, `Cache-Control: no-store`, 201 en las
  altas, listas `{items, total, limit, offset}` con `q`, `limit` (1..200) y `offset`.
- 422 con `field` (cuerpo, enumeraciones, signo del desfase, variable desconocida), 404 y 409
  (`template_name_taken`, `duplicate_active_rule`).
- Topes: las escrituras comparten `notifications-write` (30 por minuto); las lecturas y la vista
  previa (S5-D216, un POST sin escritura), `staff-read` (120 por minuto); un 403 no consume cupo.
- OpenAPI: los códigos exactos de cada operación.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.router import router
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.notifications import make_rule, make_template
from tests.notifications._apoyo import (
    CAMPOS_PLANTILLA,
    CAMPOS_REGLA,
    EJEMPLO_RENDER,
    EJEMPLO_TEXTO,
    PLANTILLAS,
    PREVIEW,
    REGLAS,
    T_PLANTILLAS,
    T_REGLAS,
    contar,
    cuerpo_plantilla,
    cuerpo_regla,
    fila,
    ruta_plantilla,
    ruta_regla,
)

RUTAS = {
    ("GET", "/notification-templates"),
    ("POST", "/notification-templates"),
    ("POST", "/notification-templates/preview"),
    ("GET", "/notification-templates/{template_id}"),
    ("PATCH", "/notification-templates/{template_id}"),
    ("GET", "/notification-rules"),
    ("POST", "/notification-rules"),
    ("GET", "/notification-rules/{rule_id}"),
    ("PATCH", "/notification-rules/{rule_id}"),
}
TOPE_ESCRITURAS = 30
TOPE_LECTURAS = 120


# Estructura -------------------------------------------------------------------------------------


def test_el_router_publica_las_nueve_rutas_de_plantillas_y_reglas() -> None:
    publicadas = {
        (metodo, ruta.path)
        for ruta in router.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
    }
    # S5-B7 suma las seis de avisos (`test_router_notifications.py`).
    assert RUTAS <= publicadas


def test_la_vista_previa_se_registra_antes_de_la_plantilla_por_id() -> None:
    orden = [r.path for r in router.routes if isinstance(r, APIRoute)]
    assert orden.index("/notification-templates/preview") < orden.index(
        "/notification-templates/{template_id}"
    )


# Roles ------------------------------------------------------------------------------------------


async def _con_datos(session: AsyncSession) -> tuple[UUID, UUID]:
    regla = await make_rule(session)
    return regla.template_id, regla.id


def _operaciones(
    plantilla: UUID, regla: UUID
) -> list[tuple[str, str, dict[str, Any] | None, bool]]:
    """`(método, ruta, cuerpo, es_escritura)` de las nueve operaciones."""
    return [
        ("GET", PLANTILLAS, None, False),
        ("POST", PLANTILLAS, cuerpo_plantilla(name="Nueva"), True),
        ("POST", PREVIEW, {"subject": "Hola", "body": "Chao"}, True),
        ("GET", ruta_plantilla(plantilla), None, False),
        ("PATCH", ruta_plantilla(plantilla), {"subject": "Otro"}, True),
        ("GET", REGLAS, None, False),
        ("POST", REGLAS, cuerpo_regla(plantilla, offset_days=0), True),
        ("GET", ruta_regla(regla), None, False),
        ("PATCH", ruta_regla(regla), {"name": "Otra"}, True),
    ]


async def test_el_admin_puede_las_nueve_operaciones(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    plantilla, regla = await _con_datos(session)
    for metodo, ruta, cuerpo, _ in _operaciones(plantilla, regla):
        r = await app_http.request(metodo, ruta, json=cuerpo, headers=cabeceras(admin))
        assert r.status_code in (200, 201), (metodo, ruta, r.text)


async def test_el_coach_lee_y_recibe_403_al_escribir_sin_efectos(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    plantilla, regla = await _con_datos(session)
    plantillas_antes, reglas_antes = (
        await contar(session, T_PLANTILLAS),
        await contar(session, T_REGLAS),
    )
    for metodo, ruta, cuerpo, escritura in _operaciones(plantilla, regla):
        r = await app_http.request(metodo, ruta, json=cuerpo, headers=cabeceras(coach))
        if escritura:
            assert r.status_code == 403, (metodo, ruta, r.text)
            assert r.json()["error"]["code"] == "forbidden"
        else:
            assert r.status_code == 200, (metodo, ruta, r.text)
    assert await contar(session, T_PLANTILLAS) == plantillas_antes
    assert await contar(session, T_REGLAS) == reglas_antes
    assert (await fila(session, T_PLANTILLAS, plantilla))["subject"] != "Otro"
    assert (await fila(session, T_REGLAS, regla))["name"] != "Otra"


async def test_member_recibe_403_en_todo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    quien = await usuario_real("member")
    plantilla, regla = await _con_datos(session)
    for metodo, ruta, cuerpo, _ in _operaciones(plantilla, regla):
        r = await app_http.request(metodo, ruta, json=cuerpo, headers=cabeceras(quien))
        assert r.status_code == 403, (metodo, ruta, r.text)
        assert r.json()["error"]["code"] == "forbidden"


async def test_sin_token_todo_da_401(app_http: AsyncClient, session: AsyncSession) -> None:
    plantilla, regla = await _con_datos(session)
    for metodo, ruta, cuerpo, _ in _operaciones(plantilla, regla):
        r = await app_http.request(metodo, ruta, json=cuerpo)
        assert r.status_code == 401, (metodo, ruta, r.text)
        assert r.json()["error"]["code"] == "unauthorized"


# Plantillas -------------------------------------------------------------------------------------


async def test_crear_plantilla_da_201_con_el_contrato_y_no_store(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(PLANTILLAS, json=cuerpo_plantilla(), headers=cabeceras(admin))
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    datos = r.json()
    assert set(datos) == CAMPOS_PLANTILLA
    assert (datos["name"], datos["subject"]) == ("Vence pronto", "Tu membresía vence pronto")
    assert (await fila(session, T_PLANTILLAS, UUID(datos["id"])))["created_by"] == admin.id


_INVALIDAS: list[tuple[dict[str, Any], str]] = [
    (cuerpo_plantilla(name="   "), "name"),
    (cuerpo_plantilla(name="N" * 81), "name"),
    (cuerpo_plantilla(subject="S" * 151), "subject"),
    (cuerpo_plantilla(subject=""), "subject"),
    (cuerpo_plantilla(body="B" * 2001), "body"),
    (cuerpo_plantilla(body=""), "body"),
    (cuerpo_plantilla(name="a​b\x00"), "name"),
    (cuerpo_plantilla(body="Hola {apellido}"), "body"),
    (cuerpo_plantilla(subject="Hola {apellido}"), "subject"),
    (cuerpo_plantilla(body="Hola {nombre"), "body"),
    (cuerpo_plantilla(body="Hola {nombre.__class__}"), "body"),
    ({"name": "X", "subject": "Y"}, "body"),
    ({**cuerpo_plantilla(), "id": str(uuid4())}, "id"),
    ({**cuerpo_plantilla(), "created_by": str(uuid4())}, "created_by"),
]


@pytest.mark.parametrize(("cuerpo", "campo"), _INVALIDAS)
async def test_crear_plantilla_invalida_da_422_con_field_y_no_crea_nada(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    cuerpo: dict[str, Any],
    campo: str,
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(PLANTILLAS, json=cuerpo, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["field"] == campo
    assert await contar(session, T_PLANTILLAS) == 0


async def test_crear_plantilla_con_nombre_repetido_da_409_con_existing_id(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    existente = await make_template(session, name="Vence pronto")
    r = await app_http.post(PLANTILLAS, json=cuerpo_plantilla(), headers=cabeceras(admin))
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("template_name_taken", "name")
    assert error["existing_id"] == str(existente.id)
    assert await contar(session, T_PLANTILLAS) == 1


async def test_listar_plantillas_pagina_busca_y_valida(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    for nombre in ("Alfa", "Bravo", "Venció"):
        await make_template(session, name=nombre)
    r = await app_http.get(PLANTILLAS, params={"limit": 2}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    pagina = r.json()
    assert set(pagina) == {"items", "total", "limit", "offset"}
    assert (pagina["total"], pagina["limit"], pagina["offset"]) == (3, 2, 0)
    assert [t["name"] for t in pagina["items"]] == ["Alfa", "Bravo"]
    assert set(pagina["items"][0]) == CAMPOS_PLANTILLA
    r = await app_http.get(PLANTILLAS, params={"q": "vencio"}, headers=cabeceras(coach))
    assert [t["name"] for t in r.json()["items"]] == ["Venció"]


@pytest.mark.parametrize(
    ("params", "campo"),
    [
        ({"limit": 0}, "limit"),
        ({"limit": 201}, "limit"),
        ({"offset": -1}, "offset"),
        ({"q": "a" * 101}, "q"),
        ({"q": "a\x00b"}, "q"),
    ],
)
@pytest.mark.parametrize("ruta", [PLANTILLAS, REGLAS])
async def test_las_listas_rechazan_parametros_fuera_de_contrato(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    ruta: str,
    params: dict[str, Any],
    campo: str,
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(ruta, params=params, headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == campo


async def test_plantilla_por_id_200_404_y_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    base = await make_template(session)
    r = await app_http.get(ruta_plantilla(base.id), headers=cabeceras(coach))
    assert r.status_code == 200 and r.json()["id"] == str(base.id)
    r = await app_http.get(ruta_plantilla(uuid4()), headers=cabeceras(coach))
    assert r.status_code == 404 and r.json()["error"]["code"] == "template_not_found"
    r = await app_http.get(ruta_plantilla("no-es-uuid"), headers=cabeceras(coach))
    assert r.status_code == 422


async def test_editar_plantilla_200_404_409_y_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    otra = await make_template(session, name="Venció")
    base = await make_template(session, name="Vence pronto")
    r = await app_http.patch(
        ruta_plantilla(base.id), json={"subject": "Nuevo"}, headers=cabeceras(admin)
    )
    assert r.status_code == 200 and r.json()["subject"] == "Nuevo"
    assert r.json()["name"] == "Vence pronto"
    r = await app_http.patch(ruta_plantilla(base.id), json={}, headers=cabeceras(admin))
    assert r.status_code == 200
    r = await app_http.patch(
        ruta_plantilla(uuid4()), json={"subject": "x"}, headers=cabeceras(admin)
    )
    assert r.status_code == 404 and r.json()["error"]["code"] == "template_not_found"
    r = await app_http.patch(
        ruta_plantilla(base.id), json={"name": "Venció"}, headers=cabeceras(admin)
    )
    assert r.status_code == 409
    assert r.json()["error"]["existing_id"] == str(otra.id)
    r = await app_http.patch(
        ruta_plantilla(base.id), json={"body": "{x}"}, headers=cabeceras(admin)
    )
    assert r.status_code == 422 and r.json()["error"]["field"] == "body"
    r = await app_http.patch(
        ruta_plantilla(base.id), json={"id": str(uuid4())}, headers=cabeceras(admin)
    )
    assert r.status_code == 422


# Vista previa -----------------------------------------------------------------------------------


async def test_la_vista_previa_renderiza_con_el_contexto_de_ejemplo_y_no_escribe(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(
        PREVIEW, json={"subject": EJEMPLO_TEXTO, "body": "Hola {nombre}"}, headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"subject": EJEMPLO_RENDER, "body": "Hola Ana"}
    assert await contar(session, T_PLANTILLAS) == 0


@pytest.mark.parametrize(
    ("cuerpo", "campo"),
    [
        ({"subject": "{x}", "body": "ok"}, "subject"),
        ({"subject": "ok", "body": "{x}"}, "body"),
        ({"subject": "ok"}, "body"),
        ({"subject": "ok", "body": "ok", "extra": 1}, "extra"),
        ({"subject": "linea\ndos", "body": "ok"}, "subject"),
        ({"subject": "ok", "body": "ctl\u0000"}, "body"),
        ({"subject": "   ", "body": "ok"}, "subject"),
    ],
)
async def test_la_vista_previa_rechaza_con_422_y_field(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    cuerpo: dict[str, Any],
    campo: str,
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(PREVIEW, json=cuerpo, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == campo


# Reglas -----------------------------------------------------------------------------------------


async def test_crear_regla_da_201_con_el_contrato(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    plantilla = await make_template(session)
    r = await app_http.post(REGLAS, json=cuerpo_regla(plantilla.id), headers=cabeceras(admin))
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    datos = r.json()
    assert set(datos) == CAMPOS_REGLA
    assert (datos["trigger"], datos["offset_days"], datos["channel"]) == (
        "membership_expiring",
        -3,
        "whatsapp_link",
    )
    assert datos["is_active"] is True and datos["template_id"] == str(plantilla.id)
    assert (await fila(session, T_REGLAS, UUID(datos["id"])))["created_by"] == admin.id


def _reglas_invalidas(plantilla: UUID) -> list[tuple[dict[str, Any], str]]:
    return [
        (cuerpo_regla(plantilla, trigger="otro"), "trigger"),
        (cuerpo_regla(plantilla, channel="sms"), "channel"),
        (cuerpo_regla(plantilla, channel="push"), "channel"),
        (cuerpo_regla(plantilla, offset_days=-3.5), "offset_days"),
        (cuerpo_regla(plantilla, offset_days="-3"), "offset_days"),
        (cuerpo_regla(plantilla, offset_days=True), "offset_days"),
        (cuerpo_regla(plantilla, offset_days=10**12), "offset_days"),
        (cuerpo_regla(plantilla, offset_days=1), "offset_days"),
        (cuerpo_regla(plantilla, trigger="membership_expired", offset_days=0), "offset_days"),
        (cuerpo_regla(plantilla, name="  "), "name"),
        (cuerpo_regla(plantilla, name="N" * 81), "name"),
        (cuerpo_regla(plantilla, is_active="si"), "is_active"),
        (cuerpo_regla("no-es-uuid"), "template_id"),
        (cuerpo_regla(uuid4()), "template_id"),
        ({**cuerpo_regla(plantilla), "id": str(uuid4())}, "id"),
    ]


@pytest.mark.parametrize("posicion", range(15))
async def test_crear_regla_invalida_da_422_con_field_y_no_crea_nada(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    posicion: int,
) -> None:
    admin = await usuario_real("admin")
    plantilla = await make_template(session)
    cuerpo, campo = _reglas_invalidas(plantilla.id)[posicion]
    r = await app_http.post(REGLAS, json=cuerpo, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["field"] == campo
    assert await contar(session, T_REGLAS) == 0


async def test_crear_regla_activa_duplicada_da_409_con_existing_id(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    existente = await make_rule(session)
    r = await app_http.post(
        REGLAS, json=cuerpo_regla(existente.template_id), headers=cabeceras(admin)
    )
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert (error["code"], error["existing_id"]) == ("duplicate_active_rule", str(existente.id))
    assert await contar(session, T_REGLAS) == 1


async def test_listar_reglas_filtra_busca_y_ordena_por_desfase(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    plantilla = await make_template(session)
    await make_rule(session, plantilla, name="Vence hoy", offset_days=0)
    await make_rule(session, plantilla, name="Vence en 3 días", offset_days=-3)
    await make_rule(
        session,
        plantilla,
        name="Venció por correo",
        trigger="membership_expired",
        offset_days=7,
        channel="email",
        is_active=False,
    )
    cab = cabeceras(coach)
    r = await app_http.get(REGLAS, headers=cab)
    assert r.status_code == 200, r.text
    assert [x["offset_days"] for x in r.json()["items"]] == [-3, 0, 7]
    assert set(r.json()["items"][0]) == CAMPOS_REGLA
    for params, esperados in (
        ({"is_active": "false"}, ["Venció por correo"]),
        ({"channel": "email"}, ["Venció por correo"]),
        ({"trigger": "membership_expiring"}, ["Vence en 3 días", "Vence hoy"]),
        ({"q": "VENCIO"}, ["Venció por correo"]),
        ({"limit": 1, "offset": 1}, ["Vence hoy"]),
    ):
        r = await app_http.get(REGLAS, params=params, headers=cab)
        assert [x["name"] for x in r.json()["items"]] == esperados, params


@pytest.mark.parametrize(
    ("params", "campo"),
    [
        ({"channel": "sms"}, "channel"),
        ({"trigger": "otro"}, "trigger"),
        ({"is_active": "tal"}, "is_active"),
    ],
)
async def test_listar_reglas_rechaza_filtros_fuera_de_contrato(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    params: dict[str, Any],
    campo: str,
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(REGLAS, params=params, headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == campo


async def test_regla_por_id_200_404_y_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    base = await make_rule(session)
    r = await app_http.get(ruta_regla(base.id), headers=cabeceras(coach))
    assert r.status_code == 200 and r.json()["id"] == str(base.id)
    r = await app_http.get(ruta_regla(uuid4()), headers=cabeceras(coach))
    assert r.status_code == 404 and r.json()["error"]["code"] == "rule_not_found"
    r = await app_http.get(ruta_regla("no-es-uuid"), headers=cabeceras(coach))
    assert r.status_code == 422


async def test_editar_regla_200_404_409_y_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    ocupante = await make_rule(session, offset_days=0, name="Vence hoy")
    base = await make_rule(session, template_id=ocupante.template_id, offset_days=-3)
    cab = cabeceras(admin)
    r = await app_http.patch(ruta_regla(base.id), json={"name": "Aviso previo"}, headers=cab)
    assert r.status_code == 200 and r.json()["name"] == "Aviso previo"
    r = await app_http.patch(ruta_regla(base.id), json={"is_active": False}, headers=cab)
    assert r.status_code == 200 and r.json()["is_active"] is False
    r = await app_http.patch(ruta_regla(uuid4()), json={"name": "x"}, headers=cab)
    assert r.status_code == 404 and r.json()["error"]["code"] == "rule_not_found"
    r = await app_http.patch(
        ruta_regla(base.id), json={"offset_days": 0, "is_active": True}, headers=cab
    )
    assert r.status_code == 409
    assert r.json()["error"]["existing_id"] == str(ocupante.id)
    r = await app_http.patch(
        ruta_regla(base.id), json={"trigger": "membership_expired"}, headers=cab
    )
    assert r.status_code == 422 and r.json()["error"]["field"] == "offset_days"
    r = await app_http.patch(ruta_regla(base.id), json={"channel": "sms"}, headers=cab)
    assert r.status_code == 422 and r.json()["error"]["field"] == "channel"


# Topes ------------------------------------------------------------------------------------------


async def test_la_escritura_31_del_minuto_da_429_y_plantillas_y_reglas_comparten_la_cubeta(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    cab = cabeceras(admin)
    for i in range(TOPE_ESCRITURAS):
        r = await app_http.post(PLANTILLAS, json=cuerpo_plantilla(name=f"P{i}"), headers=cab)
        assert r.status_code == 201, (i, r.text)
    plantilla_id = r.json()["id"]
    for ruta, json in (
        (PLANTILLAS, cuerpo_plantilla(name="Tras el tope")),
        (REGLAS, cuerpo_regla(plantilla_id)),
    ):
        r = await app_http.post(ruta, json=json, headers=cab)
        assert r.status_code == 429, (ruta, r.text)
        assert r.json()["error"]["code"] == "rate_limited"
        assert int(r.headers["retry-after"]) >= 1
    assert await contar(session, T_PLANTILLAS) == TOPE_ESCRITURAS
    r = await app_http.post(PLANTILLAS, json=cuerpo_plantilla(), headers=cabeceras(otro))
    assert r.status_code == 201, r.text


async def test_la_vista_previa_consume_staff_read_y_no_la_cubeta_de_escritura(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    """S5-D216: un POST que no escribe consume `staff-read` (120 por minuto)."""
    admin = await usuario_real("admin")
    cab = cabeceras(admin)
    cuerpo = {"subject": "Hola", "body": "Chao"}
    for i in range(TOPE_LECTURAS):
        r = await app_http.post(PREVIEW, json=cuerpo, headers=cab)
        assert r.status_code == 200, (i, r.text)
    r = await app_http.post(PREVIEW, json=cuerpo, headers=cab)
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"


async def test_la_vista_previa_no_agota_el_cupo_de_escritura(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    cab = cabeceras(admin)
    for _ in range(TOPE_ESCRITURAS + 1):
        r = await app_http.post(PREVIEW, json={"subject": "a", "body": "b"}, headers=cab)
        assert r.status_code == 200, r.text
    r = await app_http.post(PLANTILLAS, json=cuerpo_plantilla(), headers=cab)
    assert r.status_code == 201, r.text


async def test_el_403_del_coach_no_consume_cupo_de_escritura(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    for _ in range(TOPE_ESCRITURAS + 1):
        r = await app_http.post(
            PREVIEW, json={"subject": "a", "body": "b"}, headers=cabeceras(coach)
        )
        assert r.status_code == 403, r.text


async def test_la_lectura_121_del_minuto_da_429_y_plantillas_y_reglas_comparten_staff_read(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    cab = cabeceras(coach)
    for i in range(TOPE_LECTURAS):
        r = await app_http.get(REGLAS, headers=cab)
        assert r.status_code == 200, (i, r.text)
    for ruta in (REGLAS, PLANTILLAS):
        r = await app_http.get(ruta, headers=cab)
        assert r.status_code == 429, (ruta, r.text)
        assert r.json()["error"]["code"] == "rate_limited"


# OpenAPI ----------------------------------------------------------------------------------------

CODIGOS = {
    ("get", "/api/v1/notification-templates"): {"200", "401", "403", "422", "429"},
    ("post", "/api/v1/notification-templates"): {"201", "401", "403", "409", "422", "429"},
    ("post", "/api/v1/notification-templates/preview"): {"200", "401", "403", "422", "429"},
    ("get", "/api/v1/notification-templates/{template_id}"): {
        "200",
        "401",
        "403",
        "404",
        "422",
        "429",
    },
    ("patch", "/api/v1/notification-templates/{template_id}"): {
        "200",
        "401",
        "403",
        "404",
        "409",
        "422",
        "429",
    },
    ("get", "/api/v1/notification-rules"): {"200", "401", "403", "422", "429"},
    ("post", "/api/v1/notification-rules"): {"201", "401", "403", "409", "422", "429"},
    ("get", "/api/v1/notification-rules/{rule_id}"): {"200", "401", "403", "404", "422", "429"},
    ("patch", "/api/v1/notification-rules/{rule_id}"): {
        "200",
        "401",
        "403",
        "404",
        "409",
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
