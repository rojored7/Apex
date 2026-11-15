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
    # S7-C4 (S7-D41): entrar al quiosco (por IP) y salir con la contraseña (tope por usuario).
    ("post", "/api/v1/auth/kiosk"),
    ("post", "/api/v1/auth/kiosk/exit"),
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
    ("patch", "/api/v1/settings/hours"),  # S7-A1 (US-154)
    ("patch", "/api/v1/settings/classes"),
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
    # S6-A3 (S6-D10): el estado de las firmas consume la misma `staff-read`.
    ("get", "/api/v1/audit/signatures/latest"),
    # S6-B1 (US-143, S6-D13): el inventario de llaves consume `staff-read`.
    ("get", "/api/v1/crypto/keys"),
    # S6-B2 (US-144, S6-D16): la bitacora y los trabajos consumen la misma `staff-read`.
    ("get", "/api/v1/crypto/ops"),
    ("get", "/api/v1/crypto/jobs"),
    # S6-B3 (US-146, S6-D57): el CBOM consume `cbom-export` (2 por minuto).
    ("get", "/api/v1/crypto/cbom"),
    # S6-R1 (US-145, S6-D57): rotar desde la pantalla consume `keys-rotate` y `keys-rotate-hour`.
    ("post", "/api/v1/crypto/keys/{key_id}/rotate"),
    # S4A-B5 (S4A-D20, S4A-D45, M-1): el historial del socio consume la misma `staff-read`.
    ("get", "/api/v1/members/{member_id}/audit"),
    # S4A-B7 (S4A-D26, C8): editar, activar, desactivar y dar de baja un plan consumen
    # `admin-write` (compartida con `POST /plans`); las lecturas de planes no limitan.
    ("patch", "/api/v1/plans/{plan_id}"),
    ("post", "/api/v1/plans/{plan_id}/activate"),
    ("post", "/api/v1/plans/{plan_id}/deactivate"),
    ("delete", "/api/v1/plans/{plan_id}"),
    # S4A-B8 (S4A-D27 con S4A-D45, M-1): el tablero consume `staff-read`; sin parámetros, sin 422.
    ("get", "/api/v1/dashboard"),
    # S5-B5 (US-123, S5-D81): fijar los canales de un socio consume `notifications-write`; el
    # `GET` consume `staff-read` como las demás lecturas del staff (revisión de seguridad, LOW).
    ("patch", "/api/v1/members/{member_id}/channels"),
    ("get", "/api/v1/members/{member_id}/channels"),
    # S5-B6 (US-120, US-121, S5-D81): las escrituras de plantillas y reglas (y la vista previa)
    # consumen `notifications-write`; las lecturas, `staff-read`.
    ("get", "/api/v1/notification-templates"),
    ("post", "/api/v1/notification-templates"),
    ("post", "/api/v1/notification-templates/preview"),
    ("get", "/api/v1/notification-templates/{template_id}"),
    ("patch", "/api/v1/notification-templates/{template_id}"),
    ("get", "/api/v1/notification-rules"),
    ("post", "/api/v1/notification-rules"),
    ("get", "/api/v1/notification-rules/{rule_id}"),
    ("patch", "/api/v1/notification-rules/{rule_id}"),
    # S5-B7 (US-124, US-127 a US-130, S5-D59, S5-D81): `wa-link` consume `members-reveal*`, `skip`
    # `notifications-write` y las cuatro lecturas `staff-read`.
    # S5-B11 (US-137, S5-D40): el recibo PDF consume `staff-read` (Rojo B11).
    ("get", "/api/v1/payments/{payment_id}/receipt.pdf"),
    # S5-B12 (US-138, US-139, S5-D81): las dos exportaciones consumen `export`, `export-hour` y
    # `export-day` (Rojo B12).
    ("get", "/api/v1/members/export"),
    ("get", "/api/v1/payments/export"),
    ("get", "/api/v1/notifications/today"),
    ("get", "/api/v1/notifications"),
    ("get", "/api/v1/notifications/{notification_id}"),
    ("post", "/api/v1/notifications/{notification_id}/wa-link"),
    ("post", "/api/v1/notifications/{notification_id}/skip"),
    ("get", "/api/v1/members/{member_id}/notifications"),
    # S6-C2 (US-148, S6-D57): subir consume `attachments-upload`; listar, `staff-read`.
    ("post", "/api/v1/members/{member_id}/attachments"),
    ("get", "/api/v1/members/{member_id}/attachments"),
    # S6-C4 (US-150, S6-D57): descargar un adjunto consume `attachments-download` (y `-hour`) o
    # `attachments-photo` según la fila.
    ("get", "/api/v1/attachments/{attachment_id}"),
    # S7-A2 (US-155, S7-D19): las franjas consumen `classes-write` (escrituras) y `staff-read`.
    ("post", "/api/v1/class-slots"),
    ("get", "/api/v1/class-slots"),
    ("patch", "/api/v1/class-slots/{slot_id}"),
    # S7-B2 (US-157, S7-D19): sesiones; las lecturas consumen `staff-read` y las escrituras
    # `classes-write`.
    ("get", "/api/v1/class-sessions"),
    ("post", "/api/v1/class-sessions"),
    ("get", "/api/v1/class-sessions/{session_id}"),
    ("post", "/api/v1/class-sessions/{session_id}/cancel"),
    ("post", "/api/v1/class-slots/{slot_id}/cancel-future-sessions"),
    # S7-C1 (US-159, S7-D12): el check-in consume `attendance-write`; la lista, `staff-read`.
    ("post", "/api/v1/attendance"),
    ("delete", "/api/v1/attendance/{attendance_id}"),
    ("get", "/api/v1/attendance"),
    # S7-R1 (US-162): el resumen y la asistencia de la ficha consumen `staff-read`.
    ("get", "/api/v1/attendance/summary"),
    ("get", "/api/v1/members/{member_id}/attendance"),
    # S8-A1 (US-165, S8-D22): movimientos; `wods-write` en las escrituras, `staff-read` en la lista.
    ("get", "/api/v1/movements"),
    ("post", "/api/v1/movements"),
    ("patch", "/api/v1/movements/{movement_id}"),
}
PLANES_B7 = {
    ("patch", "/api/v1/plans/{plan_id}"): {"200", "401", "403", "404", "409", "422", "429"},
    ("post", "/api/v1/plans/{plan_id}/activate"): {"200", "401", "403", "404", "422", "429"},
    ("post", "/api/v1/plans/{plan_id}/deactivate"): {"200", "401", "403", "404", "422", "429"},
    ("delete", "/api/v1/plans/{plan_id}"): {"204", "401", "403", "404", "409", "422", "429"},
}
"""S4A-B7 (S4A-D22 a D26): códigos exactos de cada escritura de planes (más `500` y `503`)."""
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


# `wa-link` descifra el teléfono: declara también el 400 de `MemberNotContactable` (S5-D224) y por
# eso, con 401/403 del rol y 404/409/422/429/500, publica los ocho. Es la única excepción.
EXENTAS_DE_LOS_OCHO = frozenset({"post /api/v1/notifications/{notification_id}/wa-link"})


def test_ninguna_operacion_declara_los_ocho_genericos(esquema: dict[str, Any]) -> None:
    todos = [f"{m} {r}" for m, r, op in _operaciones(esquema) if GENERICOS <= set(op["responses"])]
    assert set(todos) - EXENTAS_DE_LOS_OCHO == set()
    assert len(todos) == len(set(todos))


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


@pytest.mark.parametrize(("metodo", "ruta"), sorted(PLANES_B7), ids=lambda v: str(v))
def test_las_escrituras_de_planes_declaran_sus_codigos_exactos(
    esquema: dict[str, Any], metodo: str, ruta: str
) -> None:
    """S4A-B7: 422 por el `{plan_id}` (y el cuerpo del PATCH), 409 solo en PATCH (nombre) y
    DELETE (membresías activas), 204 sin cuerpo en DELETE y 429 de `admin-write` en las cuatro."""
    operacion = esquema["paths"][ruta][metodo]
    assert set(operacion["responses"]) == PLANES_B7[(metodo, ruta)] | {"500", "503"}
    assert (metodo, ruta) in CON_LIMITE
    parametros = {p["name"] for p in operacion.get("parameters", [])}
    assert "plan_id" in parametros


def test_delete_de_planes_responde_204_sin_cuerpo(esquema: dict[str, Any]) -> None:
    respuesta = esquema["paths"]["/api/v1/plans/{plan_id}"]["delete"]["responses"]["204"]
    assert "content" not in respuesta


def test_el_tablero_declara_200_401_403_y_429_sin_422(esquema: dict[str, Any]) -> None:
    """S4A-B8 (S4A-D27, S4A-D45): `GET /dashboard` no tiene parámetros ni cuerpo (sin 422) y
    consume `staff-read` (429); el resto lo pone el gancho del OpenAPI (500 y 503)."""
    operacion = esquema["paths"]["/api/v1/dashboard"]["get"]
    assert set(operacion["responses"]) == {"200", "401", "403", "429", "500", "503"}
    assert not operacion.get("parameters")
    assert "requestBody" not in operacion


def test_s5_b3_el_503_de_las_rutas_con_rol_nombra_busy_y_crypto_unavailable(
    esquema: dict[str, Any],
) -> None:
    """S5-D14: una ruta con rol (la ficha del socio) y el tablero describen el 503 con las dos
    causas; `/health` conserva `HealthOut` y no describe `crypto_unavailable`."""
    for ruta in ("/api/v1/members/{member_id}", "/api/v1/dashboard"):
        descripcion = esquema["paths"][ruta]["get"]["responses"]["503"]["description"]
        assert "busy" in descripcion and "crypto_unavailable" in descripcion, (ruta, descripcion)
    for ruta in ("/health", "/api/v1/health"):
        respuesta = esquema["paths"][ruta]["get"]["responses"]["503"]
        ref = respuesta["content"]["application/json"]["schema"]["$ref"]
        assert ref == "#/components/schemas/HealthOut"
        assert "crypto_unavailable" not in respuesta["description"]


@pytest.mark.parametrize("ruta", ["/api/v1/members/export", "/api/v1/payments/export"])
def test_las_exportaciones_declaran_sus_codigos_exactos(esquema: dict[str, Any], ruta: str) -> None:
    """S5-B12 (S5-D41, S5-D82): 200 CSV, 401, 403 (solo admin), 409 (`export_in_progress`), 422
    (filtros y `export_too_large`) y 429 (tres cubetas); el 404 no existe. Rojo B12."""
    operacion = esquema["paths"][ruta]["get"]
    assert set(operacion["responses"]) == {"200", "401", "403", "409", "422", "429", "500", "503"}
    assert "text/csv" in operacion["responses"]["200"]["content"]
    assert ("get", ruta) in CON_LIMITE


def test_s6_b1_el_inventario_de_llaves_declara_sus_codigos_exactos(
    esquema: dict[str, Any],
) -> None:
    """S6-B1 (S6-D13): `GET /crypto/keys` publica 200, 401, 403 (solo admin), 422 (filtros) y 429
    (`staff-read`), sin 404 ni 409, y el 503 nombra `busy` y `crypto_unavailable` como el resto de
    las rutas con rol. El 503 `busy` por falta de la puerta de auditoría (S6-D52) llega con las
    rutas auditadas de B3 y R1."""
    operacion = esquema["paths"]["/api/v1/crypto/keys"]["get"]
    assert set(operacion["responses"]) == {"200", "401", "403", "422", "429", "500", "503"}
    descripcion = operacion["responses"]["503"]["description"]
    assert "busy" in descripcion and "crypto_unavailable" in descripcion, descripcion


def test_s6_b2_la_bitacora_y_los_trabajos_declaran_sus_codigos_exactos(
    esquema: dict[str, Any],
) -> None:
    """S6-B2 (S6-D16): `GET /crypto/ops` y `GET /crypto/jobs` publican 200, 401, 403 (solo admin),
    422 (filtros y rango) y 429 (`staff-read`), sin 404 ni 409; el 503 nombra `busy` y
    `crypto_unavailable`."""
    for ruta in ("/api/v1/crypto/ops", "/api/v1/crypto/jobs"):
        operacion = esquema["paths"][ruta]["get"]
        assert set(operacion["responses"]) == {"200", "401", "403", "422", "429", "500", "503"}, (
            ruta
        )
        descripcion = operacion["responses"]["503"]["description"]
        assert "busy" in descripcion and "crypto_unavailable" in descripcion, (ruta, descripcion)


def test_s6_b3_el_cbom_declara_sus_codigos_exactos(esquema: dict[str, Any]) -> None:
    """S6-B3 (S6-D17, S6-D52, S6-D57): `GET /crypto/cbom` publica 200 JSON, 401, 403 (solo admin)
    y 429 (`cbom-export`), sin 404, 409 ni 422 (no recibe parametros); el 503 nombra `busy` (por
    ejemplo, sin puerta de auditoria) y `crypto_unavailable`. Rojo B3."""
    operacion = esquema["paths"]["/api/v1/crypto/cbom"]["get"]
    assert set(operacion["responses"]) == {"200", "401", "403", "429", "500", "503"}
    assert "application/json" in operacion["responses"]["200"]["content"]
    descripcion = operacion["responses"]["503"]["description"]
    assert "busy" in descripcion and "crypto_unavailable" in descripcion, descripcion
    assert not operacion.get("parameters")
    assert ("get", "/api/v1/crypto/cbom") in CON_LIMITE


def test_s6_c2_las_rutas_de_adjuntos_del_socio_declaran_sus_codigos_exactos(
    esquema: dict[str, Any],
) -> None:
    """S6-C2 (S6-D59, S6-D73, S6-D84): la subida declara 404 (socio), 408 (tiempo), 413 (tamaño),
    422 (`kind` y `unsupported_type`), 429 (`attachments-upload`) y 403 (coach con consent/other);
    el listado 404, 422 y 429. Ambas con 401 y 503."""
    ruta = "/api/v1/members/{member_id}/attachments"
    subida = esquema["paths"][ruta]["post"]["responses"]
    # S6-C3 suma 409 `privacy_version_missing` (subir `consent` sin politica publicada)
    assert set(subida) == {
        "201", "401", "403", "404", "408", "409", "413", "422", "429", "500", "503",
    }  # fmt: skip
    listado = esquema["paths"][ruta]["get"]["responses"]
    assert set(listado) == {"200", "401", "403", "404", "422", "429", "500", "503"}
    for codigo in ("408", "413"):
        ref = subida[codigo]["content"]["application/json"]["schema"]["$ref"]
        assert ref == "#/components/schemas/ErrorResponse"
    parametros = {p["name"]: p for p in esquema["paths"][ruta]["post"]["parameters"]}
    assert parametros["kind"]["in"] == "query" and parametros["kind"]["required"] is True
    assert set(parametros["kind"]["schema"]["enum"]) == {"photo", "consent", "other"}
    assert "requestBody" not in esquema["paths"][ruta]["post"]  # cuerpo crudo, sin multipart


def test_s6_c4_la_descarga_de_adjuntos_declara_sus_codigos_exactos(esquema: dict[str, Any]) -> None:
    """S6-C4 (US-150, S6-D45, S6-D73): `GET /attachments/{attachment_id}` publica 200 (el archivo,
    no JSON), 401, 403 (socio, o coach con consent/other), 404 (`attachment_not_found`), 422
    (id mal formado) y 429 (tres cubetas), sin 400, 408, 409 ni 413; el 503 nombra `busy` y
    `crypto_unavailable`. Rojo C4."""
    operacion = esquema["paths"]["/api/v1/attachments/{attachment_id}"]["get"]
    assert set(operacion["responses"]) == {"200", "401", "403", "404", "422", "429", "500", "503"}
    ok = operacion["responses"]["200"]["content"]
    assert "application/json" not in ok  # es una descarga, nunca el envelope JSON
    descripcion = operacion["responses"]["503"]["description"]
    assert "busy" in descripcion and "crypto_unavailable" in descripcion, descripcion
    parametros = {p["name"]: p for p in operacion["parameters"]}
    assert parametros["attachment_id"]["in"] == "path"
    assert parametros["attachment_id"]["schema"]["format"] == "uuid"
    assert "requestBody" not in operacion


def test_s6_r1_rotar_desde_la_pantalla_declara_sus_codigos_exactos(esquema: dict[str, Any]) -> None:
    """S6-R1 (US-145, S6-D43, S6-D69): `POST /crypto/keys/{key_id}/rotate` publica 202
    (`RotationStartedOut`), 401, 403 (solo admin), 404 (llave inexistente), 409 (`key_not_active`,
    `purpose_not_rotatable`, `rotation_running`, `rotation_not_supported`), 422 (`confirm` y
    `reason`) y 429 (`keys-rotate`); el 503 nombra `busy` y `crypto_unavailable`. Rojo R1."""
    operacion = esquema["paths"]["/api/v1/crypto/keys/{key_id}/rotate"]["post"]
    assert set(operacion["responses"]) == {
        "202",
        "401",
        "403",
        "404",
        "409",
        "422",
        "429",
        "500",
        "503",
    }
    ref = operacion["responses"]["202"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/RotationStartedOut")
    descripcion = operacion["responses"]["503"]["description"]
    assert "busy" in descripcion and "crypto_unavailable" in descripcion, descripcion
    assert ("post", "/api/v1/crypto/keys/{key_id}/rotate") in CON_LIMITE
    cuerpo = esquema["components"]["schemas"]["RotateIn"]
    assert set(cuerpo["properties"]) == {"reason", "confirm"}
    assert cuerpo.get("additionalProperties") is False
