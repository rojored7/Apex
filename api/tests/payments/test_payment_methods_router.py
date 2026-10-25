"""`GET /payments/methods` con el api real (S3-B3, US-056; D24, D25, S3-C7).

Coach y admin reciben 200 con un objeto `{items}` (no un arreglo, D25) con los tres medios en
orden fijo `cash`, `nequi`, `breb` y sus etiquetas; `member` recibe 403 y sin token 401. La
respuesta lleva `Cache-Control: no-store`. Las etiquetas que guarda el admin en
`PATCH /settings/payment_methods` se ven aquí (B3.9: "Bre-B (Bancolombia)").
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import Cabeceras, CrearUsuario
from tests.payments._apoyo import CAMPOS_METODO, METODOS

POR_DEFECTO: list[dict[str, Any]] = [
    {"code": "cash", "label": "Efectivo", "hint": ""},
    {"code": "nequi", "label": "Nequi", "hint": ""},
    {"code": "breb", "label": "Bre-B", "hint": ""},
]


@pytest.mark.parametrize("rol", ["coach", "admin"])
async def test_staff_recibe_los_tres_medios_en_orden_fijo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, rol: str
) -> None:
    usuario = await usuario_real(rol)
    r = await app_http.get(METODOS, headers=cabeceras(usuario))
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo) == {"items"}
    assert cuerpo["items"] == POR_DEFECTO
    assert all(set(item) == CAMPOS_METODO for item in cuerpo["items"])


async def test_la_respuesta_no_se_guarda_en_cache(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    r = await app_http.get(METODOS, headers=cabeceras(await usuario_real("coach")))
    assert r.status_code == 200
    assert "no-store" in r.headers["cache-control"]


async def test_el_socio_recibe_403(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    r = await app_http.get(METODOS, headers=cabeceras(await usuario_real("member")))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


async def test_sin_token_401(app_http: AsyncClient) -> None:
    r = await app_http.get(METODOS)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


async def test_las_etiquetas_guardadas_por_el_admin_se_ven_en_orden_fijo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    valor = {
        "breb": {"label": "Bre-B (Bancolombia)", "hint": "Llave del gimnasio"},
        "cash": {"label": "Efectivo", "hint": ""},
        "nequi": {"label": "Nequi", "hint": ""},
    }
    guardado = await app_http.patch(
        "/api/v1/settings/payment_methods",
        headers=cabeceras(admin),
        json={"value": valor, "version": 0},
    )
    assert guardado.status_code == 200
    r = await app_http.get(METODOS, headers=cabeceras(coach))
    assert r.status_code == 200
    assert r.json()["items"] == [
        {"code": "cash", "label": "Efectivo", "hint": ""},
        {"code": "nequi", "label": "Nequi", "hint": ""},
        {"code": "breb", "label": "Bre-B (Bancolombia)", "hint": "Llave del gimnasio"},
    ]


async def test_el_contrato_es_un_objeto_con_items_y_sin_paginar(api_prueba: FastAPI) -> None:
    """D25: `GET /payments/methods` no responde un arreglo ni una `Page_...`; declara 401, 403,
    500 y 503 (el gancho de OpenAPI) y no 429 (sin límite por usuario)."""
    esquema = api_prueba.openapi()
    operacion = esquema["paths"]["/api/v1/payments/methods"]["get"]
    respuesta = operacion["responses"]["200"]["content"]["application/json"]["schema"]
    assert respuesta == {"$ref": "#/components/schemas/PaymentMethodsOut"}
    salida = esquema["components"]["schemas"]["PaymentMethodsOut"]
    assert set(salida["properties"]) == {"items"} and salida["required"] == ["items"]
    assert {p["name"] for p in operacion.get("parameters", [])} == set()
    assert {"200", "401", "403", "500", "503"} <= set(operacion["responses"])
    assert "429" not in operacion["responses"]
