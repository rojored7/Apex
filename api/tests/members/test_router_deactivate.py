"""`DELETE /api/v1/members/{member_id}` y `POST /api/v1/members/{member_id}/reactivate` por HTTP
(S3-B10; US-076; D21, D27, N-20).

Baja: 204 sin cuerpo y con `Cache-Control: no-store` para el admin (la ficha sigue visible con
`deleted_at`); 403 `forbidden` para coach y `member` sin cambios; 401 sin token; 404
`member_not_found`; 409 `member_already_deactivated`; 422 con `field="member_id"`.
Reactivar: 200 con la ficha para el admin; 403 para el coach; 409 `member_not_deactivated` sobre
un vivo y `member_document_duplicated` con `existing_id` si otro socio vivo tomó el documento.
Ninguna de las dos rutas tiene límite por usuario (sin 429, D27).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto.keyring import Keyring
from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories.members import KNOWN, make_member
from tests.members._apoyo import (
    CAMPOS_DETALLE,
    MASCARAS_KNOWN,
    MEMBERS,
    cuerpo,
    fila_socio,
    ruta_reactivar,
    ruta_socio,
)


async def test_el_admin_da_de_baja_con_204_y_la_ficha_sigue_visible(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    admin = await usuario_real("admin")
    r = await app_http.delete(ruta_socio(socio_id), headers=cabeceras(admin))
    assert r.status_code == 204, r.text
    assert r.content == b""
    assert r.headers["cache-control"] == "no-store"
    fila = await fila_socio(session, socio_id)
    assert fila["deleted_at"] == T0 and fila["status"] == "inactive"
    ficha = await app_http.get(ruta_socio(socio_id), headers=cabeceras(admin))
    assert ficha.status_code == 200, ficha.text
    assert ficha.json()["deleted_at"] is not None


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_member_reciben_403_en_la_baja_sin_cambios(
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
    antes = await fila_socio(session, socio_id)
    r = await app_http.delete(ruta_socio(socio_id), headers=cabeceras(quien))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert await fila_socio(session, socio_id) == antes


async def test_sin_token_la_baja_da_401(
    app_http: AsyncClient, session: AsyncSession, bus_listo: Keyring
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    r = await app_http.delete(ruta_socio(socio_id))
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"


async def test_la_baja_de_un_id_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.delete(
        ruta_socio("00000000-0000-4000-8000-000000000999"), headers=cabeceras(admin)
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"


async def test_una_baja_repetida_da_409(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    socio_id = socio.id
    admin = await usuario_real("admin")
    r = await app_http.delete(ruta_socio(socio_id), headers=cabeceras(admin))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "member_already_deactivated"


@pytest.mark.parametrize("metodo", ["delete", "post"])
async def test_un_id_que_no_es_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, metodo: str
) -> None:
    admin = await usuario_real("admin")
    ruta = f"{MEMBERS}/no-es-uuid" + ("/reactivate" if metodo == "post" else "")
    r = await app_http.request(metodo.upper(), ruta, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "member_id"


# Reactivar ------------------------------------------------------------------------------------


async def test_el_admin_reactiva_y_recibe_la_ficha(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    socio_id = socio.id
    admin = await usuario_real("admin")
    r = await app_http.post(ruta_reactivar(socio_id), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_DETALLE
    assert (datos["status"], datos["deleted_at"]) == ("active", None)
    assert datos["document"] == MASCARAS_KNOWN["document"]
    assert r.headers["cache-control"] == "no-store"
    assert KNOWN["document"] not in r.text
    fila = await fila_socio(session, socio_id)
    assert (fila["status"], fila["deleted_at"]) == ("active", None)


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_member_reciben_403_al_reactivar(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    rol: str,
) -> None:
    socio = await make_member(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    socio_id = socio.id
    quien = await usuario_real(rol)
    r = await app_http.post(ruta_reactivar(socio_id), headers=cabeceras(quien))
    assert r.status_code == 403, r.text
    assert (await fila_socio(session, socio_id))["deleted_at"] is not None


async def test_reactivar_un_vivo_da_409(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    admin = await usuario_real("admin")
    r = await app_http.post(ruta_reactivar(socio_id), headers=cabeceras(admin))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "member_not_deactivated"


async def test_reactivar_con_el_documento_tomado_da_409_con_existing_id(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    socio_id = socio.id
    admin = await usuario_real("admin")
    nuevo = await app_http.post(MEMBERS, json=cuerpo(), headers=cabeceras(admin))
    assert nuevo.status_code == 201, nuevo.text
    r = await app_http.post(ruta_reactivar(socio_id), headers=cabeceras(admin))
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("member_document_duplicated", "document")
    assert error["existing_id"] == nuevo.json()["id"]
    assert (await fila_socio(session, socio_id))["deleted_at"] is not None


async def test_reactivar_un_id_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(
        ruta_reactivar("00000000-0000-4000-8000-000000000999"), headers=cabeceras(admin)
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"
