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
    # S3-B2 (E2, H-2): congelar consume la misma cubeta `memberships-write`.
    ("post", "/api/v1/memberships/{membership_id}/freeze"),
    # S3-B4 (E2, E9, H-2): registrar un pago consume `payments-write`.
    ("post", "/api/v1/memberships/{membership_id}/payments"),
    # S3-B5 (E2, H-2, E15): anular un pago consume `admin-write`.
    ("post", "/api/v1/payments/{payment_id}/void"),
    # S3-B6 (E2, H-2): anular una membresía consume `admin-write` (compartida con anular un pago);
    # la vista previa de la renovación es una lectura y no tiene límite (S3-D42).
    ("post", "/api/v1/memberships/{membership_id}/cancel"),
    # S3-B7 (E2, M-2, S3-D45): la lista de membresías con `q` consume la cubeta compartida de
    # búsquedas de personas (`PII_SEARCH_BUCKET`); el resumen y el detalle no tienen límite.
    ("get", "/api/v1/memberships"),
    # S3-B8 (E2, M-2, S3-D45): la lista de pagos con `q` consume la misma cubeta compartida; el
    # resumen, los medios y el detalle no tienen límite.
    ("get", "/api/v1/payments"),
    # S3-B9b (E2, M-2, S3-D45): la ficha del socio consume `members-detail` (120 por minuto); el
    # 429 del router de `members` baja a sus tres rutas (D27).
    ("get", "/api/v1/members/{member_id}"),
    # S3-B10 (E2, D27, M-1, S3-D44): editar consume `members-write` (compartida con el alta) y
    # revelar las tres ventanas `members-reveal`, `members-reveal-hour` y `members-reveal-day`.
    ("patch", "/api/v1/members/{member_id}"),
    ("post", "/api/v1/members/{member_id}/reveal"),
    # L1 de la revisión de Fase 4 del Sprint 3: dar de baja y reactivar (solo admin) consumen
    # `admin-write`, como anular un pago o una membresía.
    ("delete", "/api/v1/members/{member_id}"),
    ("post", "/api/v1/members/{member_id}/reactivate"),
    # M-A de la revisión de seguridad V10 del Sprint 3 (S3-D100): toda escritura de solo admin
    # consume `admin-write`. Las tres de emergencia (`lock`, `unlock`, `revoke-sessions`) quedan
    # exentas con su motivo en `test_writes_have_user_limit.py`.
    ("post", "/api/v1/plans"),
    ("patch", "/api/v1/settings/gym"),
    ("patch", "/api/v1/settings/privacy"),
    ("patch", "/api/v1/settings/memberships"),
    ("patch", "/api/v1/settings/payment_methods"),
    ("patch", "/api/v1/settings/{section}"),
    ("post", "/api/v1/users"),
    ("post", "/api/v1/users/{user_id}/resend-link"),
    ("patch", "/api/v1/users/{user_id}"),
    ("delete", "/api/v1/users/{user_id}"),
    # S4A-B3 (S4A-D47, M-3): verificar la cadena consume `audit-verify` y `audit-verify-hour`;
    # `GET /audit/verify/last` no tiene límite (lee una fila).
    ("post", "/api/v1/audit/verify"),
    # S4A-B4 (S4A-D45, M-1): la lista y el detalle de la auditoría consumen `staff-read`.
    ("get", "/api/v1/audit"),
    ("get", "/api/v1/audit/{seq}"),
    # S4A-B5 (S4A-D20, S4A-D45, M-1): el historial del socio consume la misma `staff-read`.
    ("get", "/api/v1/members/{member_id}/audit"),
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
