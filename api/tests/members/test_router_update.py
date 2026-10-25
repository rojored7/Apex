"""`PATCH /api/v1/members/{member_id}` por HTTP (S3-B10; US-075; D21, D27, M-3, S3-D46, N-20).

- admin y coach: 200 con la ficha enmascarada (`CAMPOS_DETALLE`, `warnings` presente) y
  `Cache-Control: no-store`; la respuesta no lleva valores en claro ni blobs;
- `member` 403 `forbidden`; sin token 401; id inexistente 404 `member_not_found`;
- coach con `document` (igual o distinto) o con `document_type`: 403 `forbidden_field` con
  `field` (M-3, por presencia) y nada cambia; el admin sí cambia el documento;
- 409 `member_document_duplicated` con `existing_id`; 409 `member_deactivated` sobre un dado de
  baja;
- 422 con `field`: `last_name` vacío, `sex` inválido, `birth_date` futura, `document: null`,
  `first_name: null`, `status`, `deleted_at`, `data_consent_at` y `notes` en el cuerpo,
  `emergency_contact.phone` con NUL, `data_consent: false` (`consent_cannot_be_withdrawn`);
- el PATCH comparte `members-write` con `POST /members`: 30 altas y 30 ediciones pasan y la
  edición 61 en un minuto da 429.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto import bus
from app.core.crypto.keyring import Keyring
from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories.members import KNOWN, KNOWN_NORMALIZED, make_member, unique_document
from tests.members._apoyo import CAMPOS_DETALLE, MEMBERS, cuerpo, fila_socio, ruta_socio

LIMITE_DE_ESCRITURAS = 60


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_editan_y_reciben_la_ficha_enmascarada(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    rol: str,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    quien = await usuario_real(rol)
    r = await app_http.patch(
        ruta_socio(socio_id),
        json={"phone": "+57 310 555 0000", "first_name": "Lucy"},
        headers=cabeceras(quien),
    )
    assert r.status_code == 200, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_DETALLE
    assert datos["first_name"] == "Lucy"
    assert datos["phone"] == "••• ••• 0000"
    assert datos["warnings"] == ["data_consent_missing"]
    assert r.headers["cache-control"] == "no-store"
    for valor in (*KNOWN_NORMALIZED, "+57 310 555 0000", "3105550000", "apx1."):
        assert valor not in r.text, valor
    fila = await fila_socio(session, socio_id)
    assert fila["phone_idx"] == bus.blind_index("member.phone", "3105550000")


async def test_el_admin_cambia_el_documento(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    admin = await usuario_real("admin")
    r = await app_http.patch(
        ruta_socio(socio_id), json={"document": "55667788"}, headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text
    assert r.json()["document"] == "CC •••• 7788"


async def test_el_rol_member_recibe_403(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    miembro = await usuario_real("member")
    antes = await fila_socio(session, socio_id)
    r = await app_http.patch(
        ruta_socio(socio_id), json={"first_name": "Otra"}, headers=cabeceras(miembro)
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert await fila_socio(session, socio_id) == antes


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"document": KNOWN["document"]}, "document"),
        ({"document": "55667788"}, "document"),
        ({"document_type": "CC"}, "document_type"),
        ({"document_type": "CE"}, "document_type"),
    ],
    ids=["documento-igual", "documento-distinto", "tipo-igual", "tipo-distinto"],
)
async def test_el_coach_con_documento_o_tipo_recibe_403_forbidden_field(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    cambios: dict[str, Any],
    campo: str,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    coach = await usuario_real("coach")
    antes = await fila_socio(session, socio_id)
    r = await app_http.patch(ruta_socio(socio_id), json=cambios, headers=cabeceras(coach))
    assert r.status_code == 403, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("forbidden_field", campo)
    for valor in cambios.values():
        assert str(valor) not in error["message"]
    assert await fila_socio(session, socio_id) == antes


async def test_sin_token_recibe_401(
    app_http: AsyncClient, session: AsyncSession, bus_listo: Keyring
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    r = await app_http.patch(ruta_socio(socio_id), json={"first_name": "Otra"})
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"


async def test_un_id_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.patch(
        ruta_socio("00000000-0000-4000-8000-000000000999"),
        json={"first_name": "Otra"},
        headers=cabeceras(coach),
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"


async def test_un_documento_de_otro_socio_da_409_con_existing_id(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    tomado = unique_document()
    otro = await make_member(session, document=tomado, phone=None, email=None)
    otro_id = otro.id
    admin = await usuario_real("admin")
    r = await app_http.patch(
        ruta_socio(socio_id), json={"document": tomado}, headers=cabeceras(admin)
    )
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("member_document_duplicated", "document")
    assert error["existing_id"] == str(otro_id)
    assert tomado not in error["message"]


async def test_un_dado_de_baja_da_409_member_deactivated(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    socio_id = socio.id
    coach = await usuario_real("coach")
    r = await app_http.patch(
        ruta_socio(socio_id), json={"first_name": "Otra"}, headers=cabeceras(coach)
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "member_deactivated"


@pytest.mark.parametrize(
    ("cambios", "campo", "codigo"),
    [
        ({"last_name": ""}, "last_name", "validation_error"),
        ({"last_name": "   "}, "last_name", "validation_error"),
        ({"sex": "z"}, "sex", "validation_error"),
        ({"birth_date": "2026-10-22"}, "birth_date", "validation_error"),
        ({"document": None}, "document", "validation_error"),
        ({"first_name": None}, "first_name", "validation_error"),
        ({"status": "inactive"}, "status", "validation_error"),
        ({"deleted_at": "2026-10-01T00:00:00Z"}, "deleted_at", "validation_error"),
        ({"data_consent_at": "2020-01-01T00:00:00Z"}, "data_consent_at", "validation_error"),
        ({"notes": "lesión de rodilla"}, "notes", "validation_error"),
        (
            {"emergency_contact": {"name": "Rosa", "phone": "311\x00555"}},
            "emergency_contact.phone",
            "validation_error",
        ),
        ({"data_consent": False}, "data_consent", "consent_cannot_be_withdrawn"),
    ],
    ids=[
        "apellido-vacio",
        "apellido-en-blanco",
        "sexo",
        "fecha-futura",
        "documento-nulo",
        "nombre-nulo",
        "status",
        "deleted_at",
        "data_consent_at",
        "notes",
        "contacto-con-nul",
        "retirar-autorizacion",
    ],
)
async def test_una_entrada_invalida_da_422_con_field_y_no_cambia_nada(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    cambios: dict[str, Any],
    campo: str,
    codigo: str,
) -> None:
    socio = await make_member(session, data_consent_at=T0 - timedelta(days=10))
    socio_id = socio.id
    admin = await usuario_real("admin")
    antes = await fila_socio(session, socio_id)
    r = await app_http.patch(ruta_socio(socio_id), json=cambios, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == (codigo, campo)
    assert await fila_socio(session, socio_id) == antes


async def test_warnings_vacio_con_autorizacion(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session, data_consent_at=T0)
    socio_id = socio.id
    coach = await usuario_real("coach")
    r = await app_http.patch(ruta_socio(socio_id), json={"sex": None}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == []
    assert r.json()["sex"] is None


# `members-write` compartido con el alta (D27, L-1 del Sprint 2) ------------------------------


async def test_la_edicion_61_en_un_minuto_da_429_y_comparte_cubeta_con_el_alta(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    socio_id = socio.id
    ruta = ruta_socio(socio_id)  # el 429 revierte la sesión y expira el objeto
    mitad = LIMITE_DE_ESCRITURAS // 2
    for numero in range(mitad):
        alta = cuerpo(document=unique_document(), phone=None, email=None)
        r = await app_http.post(MEMBERS, json=alta, headers=cabeceras(coach))
        assert r.status_code == 201, (numero, r.text)
    for numero in range(mitad):
        r = await app_http.patch(
            ruta, json={"first_name": f"Lucía {numero}"}, headers=cabeceras(coach)
        )
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.patch(ruta, json={"first_name": "Una más"}, headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
