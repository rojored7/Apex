"""Redacción por clave y por forma del valor, y JSON de una línea (US-018, T1, T2 y T5)."""

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
    assert {"document", "phone", "email", "birth_date", "emergency_contact"} <= app_logging.SENSITIVE_KEYS
    assert {"password", "token", "refresh_token", "access_token", "authorization"} <= app_logging.SENSITIVE_KEYS
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
