"""`POST /api/v1/members` por HTTP (S2-B7; US-069 criterios 1, 2, 5, 7, 8, 9 y 11; M-4, M-5,
L-1, L-3).

- admin y coach: 201 `MemberDetailOut` enmascarado, `created_by` = quien llama;
- `member` 403 `forbidden`; sin token 401 `unauthorized`;
- 422 `validation_error` con `field`: nombres en blanco, sexo, fecha futura, documento corto o que
  se normaliza a vacío, teléfono `"+57"`, correo inválido, tipo de documento, y los campos que el
  cliente no envía (`data_consent_at`, M-4; `notes`, M-5; `extra="forbid"`); nada se crea;
- 409 `member_document_duplicated` con `field` y `existing_id`;
- el alta 61 de un mismo usuario en un minuto da 429 `rate_limited` con `Retry-After` y otro
  usuario no se ve afectado (L-1);
- ningún log lleva el documento, el teléfono, el correo, el token ni un blob.
`Cache-Control: no-store` lo exige `tests/architecture/test_no_store_routes.py` (revisión Python
M6: `core.http.no_store` en el router de socios); Nginx también lo pone en `/api/`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto.keyring import Keyring
from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories.members import KNOWN_NORMALIZED, unique_document
from tests.members._apoyo import (
    CAMPOS_DETALLE,
    MASCARAS_KNOWN,
    MEMBERS,
    cuantos_socios,
    cuerpo,
    fila_socio,
)

LIMITE_POR_MINUTO = 60


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_crean_y_reciben_el_detalle_enmascarado(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    r = await app_http.post(MEMBERS, json=cuerpo(), headers=cabeceras(quien))
    assert r.status_code == 201, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_DETALLE
    assert datos["status"] == "active"
    assert datos["first_name"] == "Lucía" and datos["last_name"] == "Gómez"
    assert datos["document_type"] == "CC"
    for campo, mascara in MASCARAS_KNOWN.items():
        assert datos[campo] == mascara, campo
    assert datos["warnings"] == []
    assert datetime.fromisoformat(datos["data_consent_at"]) == T0
    assert datos["data_consent_version"] is None
    assert datos["membership_status"] == "none"  # PL4 de Fase 4: como la ficha y la lista
    assert datetime.fromisoformat(datos["created_at"]).tzinfo is not None
    for valor in KNOWN_NORMALIZED:
        assert valor not in r.text, valor
    assert "apx1." not in r.text
    fila = await fila_socio(session, UUID(datos["id"]))
    assert fila["created_by"] == quien.id


async def test_sin_autorizacion_responde_con_el_aviso(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.post(MEMBERS, json=cuerpo(data_consent=False), headers=cabeceras(coach))
    assert r.status_code == 201, r.text
    assert r.json()["warnings"] == ["data_consent_missing"]
    assert r.json()["data_consent_at"] is None


async def test_un_cuerpo_minimo_crea_con_tipo_cc_y_sin_autorizacion(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    minimo = {"first_name": "Ana", "last_name": "Ruiz", "document": "1.020.304"}
    r = await app_http.post(MEMBERS, json=minimo, headers=cabeceras(admin))
    assert r.status_code == 201, r.text
    datos = r.json()
    assert datos["document_type"] == "CC" and datos["document"] == "CC •••• 0304"
    assert datos["phone"] is None and datos["email"] is None and datos["sex"] is None
    assert datos["warnings"] == ["data_consent_missing"]


async def test_el_rol_member_recibe_403(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await usuario_real("member")
    r = await app_http.post(MEMBERS, json=cuerpo(), headers=cabeceras(socio))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert await cuantos_socios(session) == 0


async def test_sin_token_recibe_401(
    app_http: AsyncClient, session: AsyncSession, bus_listo: Keyring
) -> None:
    r = await app_http.post(MEMBERS, json=cuerpo())
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"
    assert await cuantos_socios(session) == 0


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"first_name": "   "}, "first_name"),
        ({"last_name": ""}, "last_name"),
        ({"sex": "z"}, "sex"),
        ({"birth_date": "2026-10-22"}, "birth_date"),
        ({"document": "12"}, "document"),
        ({"document": "..."}, "document"),
        ({"phone": "+57"}, "phone"),
        ({"phone": "..."}, "phone"),
        ({"email": "no-es-correo"}, "email"),
        ({"document_type": "NIT"}, "document_type"),
        ({"data_consent_at": "2020-01-01T00:00:00Z"}, "data_consent_at"),
        ({"notes": "lesión de rodilla"}, "notes"),
    ],
    ids=[
        "nombre-en-blanco",
        "apellido-vacio",
        "sexo",
        "fecha-futura",
        "documento-corto",
        "documento-solo-puntos",
        "telefono-solo-prefijo",
        "telefono-solo-puntos",
        "correo",
        "tipo-documento",
        "data_consent_at-del-cliente",
        "notes",
    ],
)
async def test_una_entrada_invalida_da_422_con_field_y_no_crea_nada(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    cambios: dict[str, Any],
    campo: str,
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.post(MEMBERS, json=cuerpo(**cambios), headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert error["code"] == "validation_error"
    assert error["field"] == campo
    for valor in cambios.values():
        if len(str(valor).strip()) > 3:
            assert str(valor) not in error["message"]
    assert await cuantos_socios(session) == 0


async def test_un_documento_repetido_da_409_con_existing_id(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    primero = await app_http.post(
        MEMBERS, json=cuerpo(document="1.020.304.417"), headers=cabeceras(coach)
    )
    assert primero.status_code == 201, primero.text
    r = await app_http.post(
        MEMBERS, json=cuerpo(document="1020304417", phone=None), headers=cabeceras(coach)
    )
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["code"] == "member_document_duplicated"
    assert error["field"] == "document"
    assert error["existing_id"] == primero.json()["id"]
    assert "1020304417" not in r.text
    assert await cuantos_socios(session) == 1


async def test_el_alta_61_de_un_usuario_en_un_minuto_da_429_y_otro_usuario_sigue(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    """L-1: `ratelimit.enforce("members-write", str(user_id), limit=60, window_s=60)`; el reloj
    está congelado, así las 61 caen en la misma ventana."""
    coach = await usuario_real("coach")
    otro = await usuario_real("coach")
    minimo = {"first_name": "Ana", "last_name": "Ruiz", "phone": None}
    for numero in range(LIMITE_POR_MINUTO):
        r = await app_http.post(
            MEMBERS, json={**minimo, "document": unique_document()}, headers=cabeceras(coach)
        )
        assert r.status_code == 201, (numero, r.text)
    r = await app_http.post(
        MEMBERS, json={**minimo, "document": unique_document()}, headers=cabeceras(coach)
    )
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    assert await cuantos_socios(session) == LIMITE_POR_MINUTO
    r = await app_http.post(
        MEMBERS, json={**minimo, "document": unique_document()}, headers=cabeceras(otro)
    )
    assert r.status_code == 201, r.text


async def test_los_logs_no_llevan_documento_telefono_correo_token_ni_blob(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    caplog: pytest.LogCaptureFixture,
) -> None:
    coach = await usuario_real("coach")
    caplog.set_level(logging.DEBUG)
    creado = await app_http.post(MEMBERS, json=cuerpo(), headers=cabeceras(coach))
    assert creado.status_code == 201, creado.text
    repetido = await app_http.post(MEMBERS, json=cuerpo(), headers=cabeceras(coach))
    assert repetido.status_code == 409, repetido.text
    texto = caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    for valor in (*KNOWN_NORMALIZED, coach.token, "apx1."):
        assert valor not in texto, valor
