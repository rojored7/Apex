"""`GET` y `PATCH /settings/payment_methods` con el api real (S3-B3, US-056; D24, S3-D55).

Rutas tipadas antes de la genérica (S2-D15), solo admin: el coach recibe 403 en las dos (lee los
medios por `GET /payments/methods`); el socio 403 y sin token 401. El admin lee los defaults en
versión 0, guarda en versión 1, una versión vieja da 409 `version_conflict` y un valor inválido
422 con `field` (`value.tarjeta`, `value.nequi.label`) sin tocar la fila.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.settings._apoyo import (
    API,
    PAYMENT_METHODS_DEFAULTS,
    PAYMENT_METHODS_OK,
    fila,
    filas_de_auditoria,
)

RUTA = f"{API}/settings/payment_methods"


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


async def _patch(
    cliente: AsyncClient, cabeceras: dict[str, str], valor: dict[str, Any], version: int
) -> Response:
    return await cliente.patch(RUTA, headers=cabeceras, json={"value": valor, "version": version})


async def test_admin_lee_los_defaults_en_version_0(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await app_http.get(RUTA, headers=cabeceras(admin))
    assert r.status_code == 200
    assert r.json() == {
        "key": "payment_methods",
        "value": PAYMENT_METHODS_DEFAULTS,
        "version": 0,
        "updated_at": None,
        "updated_by": None,
    }
    assert "no-store" in r.headers["cache-control"]


async def test_admin_guarda_y_lee_lo_guardado(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _patch(app_http, cabeceras(admin), PAYMENT_METHODS_OK, 0)
    assert r.status_code == 200
    cuerpo = r.json()
    assert (cuerpo["key"], cuerpo["version"], cuerpo["value"]) == (
        "payment_methods",
        1,
        PAYMENT_METHODS_OK,
    )
    assert cuerpo["updated_by"] == str(admin.id)
    assert (await app_http.get(RUTA, headers=cabeceras(admin))).json() == cuerpo


@pytest.mark.parametrize("metodo", ["GET", "PATCH"])
async def test_coach_403_en_get_y_patch_sin_escribir(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    metodo: str,
) -> None:
    coach = await usuario_real("coach")
    cuerpo = {"value": PAYMENT_METHODS_OK, "version": 0} if metodo == "PATCH" else None
    r = await app_http.request(metodo, RUTA, headers=cabeceras(coach), json=cuerpo)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert await fila(session, "payment_methods") is None
    assert await filas_de_auditoria(session) == []


async def test_socio_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    assert (await app_http.get(RUTA, headers=cabeceras(socio))).status_code == 403
    sin_token = await app_http.get(RUTA)
    assert sin_token.status_code == 401
    assert sin_token.json()["error"]["code"] == "unauthorized"


async def test_version_vieja_da_409_sin_tocar_la_fila(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    assert (await _patch(app_http, cabeceras(admin), PAYMENT_METHODS_OK, 0)).status_code == 200
    r = await _patch(app_http, cabeceras(admin), PAYMENT_METHODS_DEFAULTS, 0)
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    guardada = await fila(session, "payment_methods")
    assert guardada is not None
    assert (guardada["version"], guardada["value"]) == (1, PAYMENT_METHODS_OK)


@pytest.mark.parametrize(
    ("valor", "campo"),
    [
        ({**PAYMENT_METHODS_OK, "tarjeta": {"label": "Tarjeta"}}, "value.tarjeta"),
        (
            {**PAYMENT_METHODS_OK, "cash": {"label": "Nequi"}, "nequi": {"label": "nequi"}},
            "value.nequi.label",
        ),
        ({**PAYMENT_METHODS_OK, "cash": {"label": ""}}, "value.cash.label"),
        ({**PAYMENT_METHODS_OK, "cash": {"label": "Caja", "hint": "y" * 121}}, "value.cash.hint"),
    ],
    ids=["codigo-ajeno", "etiqueta-repetida", "etiqueta-vacia", "pista-de-121"],
)
async def test_un_valor_invalido_da_422_con_field_sin_crear_fila(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    valor: dict[str, Any],
    campo: str,
) -> None:
    r = await _patch(app_http, cabeceras(admin), valor, 0)
    assert r.status_code == 422
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)
    assert await fila(session, "payment_methods") is None


async def test_el_openapi_declara_las_rutas_tipadas(api_prueba: FastAPI) -> None:
    rutas = api_prueba.openapi()["paths"]["/api/v1/settings/payment_methods"]
    esquemas = {
        metodo: operacion["responses"]["200"]["content"]["application/json"]["schema"]
        for metodo, operacion in rutas.items()
    }
    assert esquemas == {
        "get": {"$ref": "#/components/schemas/PaymentMethodsSectionOut"},
        "patch": {"$ref": "#/components/schemas/PaymentMethodsSectionOut"},
    }
    assert "409" in rutas["patch"]["responses"]
