"""`/settings/hours` y `/settings/classes` con el api real (US-154; S7-D8)."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.settings._apoyo import (
    API,
    CLASSES_DEFAULTS,
    CLASSES_OK,
    HOURS_DEFAULTS,
    HOURS_OK,
    fila,
    filas_de_auditoria,
)

SECCIONES: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "hours": (HOURS_OK, HOURS_DEFAULTS),
    "classes": (CLASSES_OK, CLASSES_DEFAULTS),
}


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


@pytest.mark.parametrize("seccion", list(SECCIONES))
async def test_admin_lee_y_parchea(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, seccion: str
) -> None:
    valido, por_defecto = SECCIONES[seccion]
    ruta = f"{API}/settings/{seccion}"
    leida = await app_http.get(ruta, headers=cabeceras(admin))
    assert leida.status_code == 200
    assert leida.json()["value"] == por_defecto and leida.json()["version"] == 0
    r = await app_http.patch(ruta, headers=cabeceras(admin), json={"value": valido, "version": 0})
    assert r.status_code == 200
    assert r.json()["key"] == seccion and r.json()["value"] == valido
    assert r.json()["version"] == 1
    relectura = await app_http.get(ruta, headers=cabeceras(admin))
    assert relectura.json()["value"] == valido


@pytest.mark.parametrize("rol", ["coach", "member"])
@pytest.mark.parametrize("seccion", list(SECCIONES))
@pytest.mark.parametrize("metodo", ["GET", "PATCH"])
async def test_coach_y_socio_403(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
    seccion: str,
    metodo: str,
) -> None:
    usuario = await usuario_real(rol)
    cuerpo = {"value": SECCIONES[seccion][0], "version": 0} if metodo == "PATCH" else None
    r = await app_http.request(
        metodo, f"{API}/settings/{seccion}", headers=cabeceras(usuario), json=cuerpo
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert await fila(session, seccion) is None


@pytest.mark.parametrize("seccion", list(SECCIONES))
async def test_patch_audita_y_sube_version(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    seccion: str,
) -> None:
    valido, _ = SECCIONES[seccion]
    ruta = f"{API}/settings/{seccion}"
    primero = await app_http.patch(
        ruta, headers=cabeceras(admin), json={"value": valido, "version": 0}
    )
    assert primero.status_code == 200
    segundo_valor = (
        {**valido, "default_capacity": 20} if seccion == "classes" else {**valido, "saturday": []}
    )
    segundo = await app_http.patch(
        ruta, headers=cabeceras(admin), json={"value": segundo_valor, "version": 1}
    )
    assert segundo.status_code == 200 and segundo.json()["version"] == 2
    guardada = await fila(session, seccion)
    assert guardada is not None and guardada["version"] == 2 and guardada["updated_by"] == admin.id
    auditoria = await filas_de_auditoria(session)
    assert [f["action"] for f in auditoria] == ["insert", "update"]
    assert all(f["user_id"] == admin.id for f in auditoria)


@pytest.mark.parametrize("seccion", list(SECCIONES))
async def test_version_vieja_409(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, seccion: str
) -> None:
    valido, _ = SECCIONES[seccion]
    ruta = f"{API}/settings/{seccion}"
    await app_http.patch(ruta, headers=cabeceras(admin), json={"value": valido, "version": 0})
    r = await app_http.patch(ruta, headers=cabeceras(admin), json={"value": valido, "version": 0})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"


async def test_hours_invalida_da_422_con_field_y_no_guarda(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    valor = {**HOURS_DEFAULTS, "monday": [{"open": "21:00", "close": "05:00"}]}
    r = await app_http.patch(
        f"{API}/settings/hours", headers=cabeceras(admin), json={"value": valor, "version": 0}
    )
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "validation_error" and "monday" in error["field"]
    assert await fila(session, "hours") is None


async def test_classes_con_allow_over_capacity_da_422(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    valor = {**CLASSES_OK, "allow_over_capacity": True}
    r = await app_http.patch(
        f"{API}/settings/classes", headers=cabeceras(admin), json={"value": valor, "version": 0}
    )
    assert r.status_code == 422 and "allow_over_capacity" in r.json()["error"]["field"]
