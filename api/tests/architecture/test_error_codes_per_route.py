"""Cada ruta declara en el OpenAPI solo los errores que puede devolver (M7 de la revisión general).

Antes las 31 operaciones publicaban idénticos 400/401/403/404/409/422/429/500 (incluido
`/health`), porque la app los ponía con `FastAPI(responses=ERROR_RESPONSES)`. Ahora cada router
o ruta los pide con `core.errors.responses_for(...)` y el gancho del OpenAPI solo agrega `500`
(toda ruta puede fallar) y convierte en `ErrorResponse` el `422` que FastAPI pone a las rutas
con parámetros o cuerpo. Reglas que se comprueban sobre el esquema real de `create_app()`:
- ninguna operación declara los ocho códigos genéricos a la vez;
- `/health` no declara ninguno de 400/401/403/404/409/422/429 y su 503 sigue siendo `HealthOut`;
- una ruta con rol declara 401; una ruta con `rate_limit` (o límite por cuenta/usuario) 429;
- una ruta con parámetros o cuerpo declara 422 y una sin ellos no;
- todo 4xx/5xx genérico apunta a `ErrorResponse`.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.core.errors import responses_for
from app.main import create_app

GENERICOS = frozenset({"400", "401", "403", "404", "409", "422", "429", "500"})
CON_LIMITE = {
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/refresh"),
    ("post", "/api/v1/auth/logout"),
    ("post", "/api/v1/auth/forgot"),
    ("post", "/api/v1/auth/reset"),
    ("post", "/api/v1/auth/me/password"),
    ("post", "/api/v1/members"),
    ("get", "/api/v1/members"),
    # S3-B1 (E2, H-2): vender consume `memberships-write`.
    ("post", "/api/v1/members/{member_id}/memberships"),
}
PUBLICAS = {
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/refresh"),
    ("post", "/api/v1/auth/logout"),
    ("post", "/api/v1/auth/forgot"),
    ("post", "/api/v1/auth/reset"),
}


@pytest.fixture
def esquema(settings_prueba: Settings) -> dict[str, Any]:
    return create_app(settings_prueba, run_migrations_on_startup=False).openapi()


def _operaciones(esquema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (metodo, ruta, operacion)
        for ruta, operaciones in esquema["paths"].items()
        for metodo, operacion in operaciones.items()
    ]


def test_ninguna_operacion_declara_los_ocho_genericos(esquema: dict[str, Any]) -> None:
    todos = [f"{m} {r}" for m, r, op in _operaciones(esquema) if GENERICOS <= set(op["responses"])]
    assert todos == []


@pytest.mark.parametrize("ruta", ["/health", "/api/v1/health"])
def test_health_no_declara_errores_de_sesion_ni_de_validacion(
    esquema: dict[str, Any], ruta: str
) -> None:
    respuestas = esquema["paths"][ruta]["get"]["responses"]
    assert set(respuestas) & {"400", "401", "403", "404", "409", "422", "429"} == set()
    salud = respuestas["503"]["content"]["application/json"]["schema"]["$ref"]
    assert salud == "#/components/schemas/HealthOut"


def test_las_rutas_con_sesion_declaran_401_y_las_publicas_no_lo_inventan(
    esquema: dict[str, Any],
) -> None:
    for metodo, ruta, operacion in _operaciones(esquema):
        if "health" in ruta:
            continue
        if (metodo, ruta) in PUBLICAS and ruta.endswith(("/logout", "/forgot", "/reset")):
            assert "401" not in operacion["responses"], f"{metodo} {ruta}"
        else:
            assert "401" in operacion["responses"], f"{metodo} {ruta}"


def test_las_rutas_con_limite_declaran_429_y_las_demas_no(esquema: dict[str, Any]) -> None:
    for metodo, ruta, operacion in _operaciones(esquema):
        assert ("429" in operacion["responses"]) == ((metodo, ruta) in CON_LIMITE), (metodo, ruta)


def test_422_solo_con_parametros_o_cuerpo(esquema: dict[str, Any]) -> None:
    for metodo, ruta, operacion in _operaciones(esquema):
        tiene_entrada = bool(operacion.get("parameters")) or "requestBody" in operacion
        if ruta.endswith(("/auth/refresh", "/auth/logout")):
            continue  # leen la cookie, sin parámetros declarados: no hay 422
        assert ("422" in operacion["responses"]) == tiene_entrada, (metodo, ruta)


def test_todo_error_generico_apunta_a_error_response(esquema: dict[str, Any]) -> None:
    for metodo, ruta, operacion in _operaciones(esquema):
        assert "500" in operacion["responses"], (metodo, ruta)
        for codigo, respuesta in operacion["responses"].items():
            if codigo in GENERICOS:
                ref = respuesta["content"]["application/json"]["schema"]["$ref"]
                assert ref == "#/components/schemas/ErrorResponse", (metodo, ruta, codigo)


def test_responses_for_rechaza_un_codigo_fuera_del_catalogo() -> None:
    assert set(responses_for(401, 403)) == {401, 403}
    with pytest.raises(ValueError, match="418"):
        responses_for(418)
