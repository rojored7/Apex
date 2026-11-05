"""`CryptoUnavailable` -> 503 `crypto_unavailable` con `Retry-After: 30` (S5-B3; S5-D14). Rojo B3.

- cada razón (`sealed`, `unreachable`, `forbidden`, `not_loaded`) da el mismo 503 con el envelope y
  el texto fijo; ni la razón ni la URL ni el mensaje interno salen en el cuerpo;
- una ruta que usa el bus sin keyring (`current_keyring()` -> `not_loaded`) responde ese 503;
- los demás `CryptoError` no cambian: siguen siendo 500 `internal_error`;
- el 503 común de OpenAPI describe `busy` y `crypto_unavailable`.
"""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.crypto import bus
from app.core.crypto.errors import CryptoError, CryptoUnavailable, UnavailableReason
from app.core.crypto.keyring import configure_keyring
from app.core.errors import register_error_handlers

MENSAJE = "El custodio de llaves no está disponible. Avise al administrador para desellarlo."
SECRETO_INTERNO = "http://openbao:8200/token-s.secreto"


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/razon/{razon}")
    async def razon(razon: str) -> dict[str, str]:
        raise CryptoUnavailable(razon, SECRETO_INTERNO)  # type: ignore[arg-type]

    @app.get("/sin-keyring")
    async def sin_keyring() -> dict[str, str]:
        return {"blob": bus.encrypt("member.phone", b"3001234567", b"aad", record_id=uuid4())}

    @app.get("/otro-error")
    async def otro_error() -> dict[str, str]:
        raise CryptoError("decrypt_failed", SECRETO_INTERNO)

    return app


@pytest.mark.parametrize("razon", ["sealed", "unreachable", "forbidden", "not_loaded"])
async def test_cada_razon_responde_503_con_el_envelope_y_el_texto_fijo(
    razon: UnavailableReason,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as c:
        r = await c.get(f"/razon/{razon}")
    assert r.status_code == 503, r.text
    assert r.json() == {"error": {"code": "crypto_unavailable", "message": MENSAJE}}
    assert r.headers["retry-after"] == "30"
    assert r.headers["content-type"].startswith("application/json")
    assert razon not in r.text and SECRETO_INTERNO not in r.text and "openbao" not in r.text


async def test_una_ruta_que_usa_el_bus_sin_keyring_responde_503_crypto_unavailable() -> None:
    configure_keyring(None)
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as c:
        r = await c.get("/sin-keyring")
    assert r.status_code == 503, r.text
    assert r.json()["error"]["code"] == "crypto_unavailable"
    assert r.headers["retry-after"] == "30"


async def test_el_503_no_registra_la_url_ni_el_token(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as c:
        await c.get("/razon/sealed")
    assert SECRETO_INTERNO not in caplog.text and "s.secreto" not in caplog.text


async def test_los_demas_crypto_error_siguen_siendo_500_internal_error() -> None:
    app = _app()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        r = await c.get("/otro-error")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "retry-after" not in r.headers and SECRETO_INTERNO not in r.text


def test_el_503_comun_de_openapi_describe_busy_y_crypto_unavailable() -> None:
    """La descripción cambia de "Base de datos ocupada" a la que nombra las dos causas."""
    from app.core import errors

    assert "busy" in errors.MENSAJE_503 and "crypto_unavailable" in errors.MENSAJE_503
