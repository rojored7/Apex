"""Redacción por clave y por forma del valor, y JSON de una línea (US-018, T1, T2 y T5).

S2-B3: el token de `/restablecer/<token>`, el valor de `apex_refresh=` y las claves
`activation_url`, `url` y `set-cookie` (blueprint 7.2; sección 2, regla 7).
"""

from __future__ import annotations

import json
import logging

from app.core import logging as app_logging
from app.core.context import request_id_var
from app.core.logging import JsonFormatter, redact, redact_text

BLOB = "apx1.k1.A256GCM.bm9uY2U.Y2lmcmFkbw"
JWT = "eyJhbGciOiJFZERTQSJ9.eyJzdWIiOiIxIn0.firma_x-y"


def test_redacta_password_y_document() -> None:
    assert redact({"password": "x", "document": "1020304"}) == {
        "password": "[redacted]",
        "document": "[redacted]",
    }


def test_redacta_anidado_listas_y_mayusculas() -> None:
    entrada = {
        "Authorization": "Bearer abc",
        "socio": {"Phone": "3001234567", "nombre": "Ana"},
        "items": [{"email": "a@b.c", "monto": 1}, "texto"],
    }
    assert redact(entrada) == {
        "Authorization": "[redacted]",
        "socio": {"Phone": "[redacted]", "nombre": "Ana"},
        "items": [{"email": "[redacted]", "monto": 1}, "texto"],
    }


def test_redacta_blob_y_jwt_bajo_cualquier_clave() -> None:
    assert redact({"valor": BLOB, "otro": JWT, "sano": "hola"}) == {
        "valor": "[redacted]",
        "otro": "[redacted]",
        "sano": "hola",
    }


def test_redacta_dentro_del_texto() -> None:
    texto = f"falló con token {JWT} y blob {BLOB} fin"
    limpio = redact_text(texto)
    assert "eyJ" not in limpio
    assert "apx1." not in limpio
    assert limpio.startswith("falló con token [redacted]")
    assert limpio.endswith("fin")


def test_no_toca_claves_sanas_ni_numeros() -> None:
    assert redact({"status": 200, "duration_ms": 3.5, "path": "/x"}) == {
        "status": 200,
        "duration_ms": 3.5,
        "path": "/x",
    }


def test_lista_de_claves_cubre_los_campos_cifrados_de_v01() -> None:
    assert {
        "document",
        "phone",
        "email",
        "birth_date",
        "emergency_contact",
    } <= app_logging.SENSITIVE_KEYS
    assert {
        "password",
        "token",
        "refresh_token",
        "access_token",
        "authorization",
    } <= app_logging.SENSITIVE_KEYS
    assert {"kek", "dek", "secret"} <= app_logging.SENSITIVE_KEYS


def test_formatter_produce_json_en_una_linea_con_traza() -> None:
    token = request_id_var.set("req-123")
    try:
        try:
            raise ValueError(f"explotó con {JWT}")
        except ValueError:
            record = logging.LogRecord(
                name="app.prueba",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="documento %s",
                args=("1020304",),
                exc_info=True,
            )
            import sys

            record.exc_info = sys.exc_info()
        record.path = "/api/v1/members"  # type: ignore[attr-defined]
        record.document = "1020304"  # type: ignore[attr-defined]
        linea = JsonFormatter().format(record)
    finally:
        request_id_var.reset(token)

    assert "\n" not in linea
    datos = json.loads(linea)
    assert datos["level"] == "ERROR"
    assert datos["logger"] == "app.prueba"
    assert datos["request_id"] == "req-123"
    assert datos["timestamp"].endswith("Z")
    assert datos["path"] == "/api/v1/members"
    assert datos["document"] == "[redacted]"
    assert "Traceback" in datos["exception"]
    assert "eyJ" not in linea


# S2-B3 · enlaces de un solo uso y cookie del refresh (blueprint 7.2, sección 2 regla 7) ------

# Forma base64url de 43+ caracteres, como `new_opaque_token()`; no es un secreto real.
TOKEN = "Qm9uaXRvLXRva2VuLWRlLXVuLXNvbG8tdXNvXzEyMzQ1Ng"  # noqa: S105


def test_redacta_el_token_de_la_ruta_restablecer_en_el_texto() -> None:
    texto = f"enlace http://localhost:8180/restablecer/{TOKEN} entregado"
    limpio = redact_text(texto)
    assert TOKEN not in limpio
    assert "http://localhost:8180/restablecer/[redacted] entregado" in limpio


def test_redacta_la_ruta_restablecer_con_query_o_fragmento() -> None:
    limpio = redact_text(f"GET /restablecer/{TOKEN}?a=1#x")
    assert TOKEN not in limpio
    assert limpio.startswith("GET /restablecer/[redacted]")


def test_redacta_el_valor_de_la_cookie_apex_refresh() -> None:
    texto = f"Set-Cookie: apex_refresh={TOKEN}; HttpOnly; Path=/api/v1/auth; SameSite=strict"
    limpio = redact_text(texto)
    assert TOKEN not in limpio
    assert "apex_refresh=[redacted]; HttpOnly; Path=/api/v1/auth" in limpio


def test_las_claves_nuevas_estan_en_la_lista() -> None:
    assert {"activation_url", "url", "set-cookie"} <= app_logging.SENSITIVE_KEYS


def test_redacta_activation_url_url_y_set_cookie_por_clave() -> None:
    entrada = {
        "activation_url": f"http://localhost:8180/restablecer/{TOKEN}",
        "URL": "http://localhost:8180/socios",
        "Set-Cookie": f"apex_refresh={TOKEN}",
        "set-cookie": "otra=1",
        "ruta": "/api/v1/users",
    }
    assert redact(entrada) == {
        "activation_url": "[redacted]",
        "URL": "[redacted]",
        "Set-Cookie": "[redacted]",
        "set-cookie": "[redacted]",
        "ruta": "/api/v1/users",
    }


def test_el_token_bajo_una_clave_sana_tambien_se_redacta() -> None:
    datos = redact({"detalle": f"abrió /restablecer/{TOKEN}", "lista": [f"apex_refresh={TOKEN}"]})
    assert TOKEN not in json.dumps(datos)


def test_el_formatter_no_deja_pasar_el_enlace() -> None:
    record = logging.LogRecord(
        name="app.auth",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="enlace %s",
        args=(f"http://localhost:8180/restablecer/{TOKEN}",),
        exc_info=None,
    )
    record.cabecera = f"apex_refresh={TOKEN}"  # type: ignore[attr-defined]
    linea = JsonFormatter().format(record)
    assert TOKEN not in linea
    assert "/restablecer/[redacted]" in json.loads(linea)["message"]


def test_no_toca_rutas_parecidas_sin_token() -> None:
    assert redact_text("/api/v1/auth/reset y /restablecer") == "/api/v1/auth/reset y /restablecer"


def test_redacta_el_enlace_codificado_en_una_url() -> None:
    """Revisión de seguridad S2-B3 (LOW-5): `%2Frestablecer%2F<token>` dentro de un parámetro."""
    limpio = redact_text(f"next=%2Frestablecer%2F{TOKEN}&x=1")
    assert TOKEN not in limpio
    assert limpio == "next=%2Frestablecer%2F[redacted]&x=1"
