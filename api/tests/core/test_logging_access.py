"""Línea de acceso por petición sin query, cuerpo ni cabeceras; `X-Request-ID` (US-018, T4 y T7)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import load_settings
from app.core.context import request_id_var
from app.core.logging import RequestLogMiddleware, configure_logging

JWT = "eyJhbGciOiJFZERTQSJ9.eyJzdWIiOiIxIn0.firma"


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLogMiddleware)

    @app.get("/api/v1/members")
    async def members(q: str = "") -> dict[str, str | None]:
        logging.getLogger("app.members").info("buscando socios")
        return {"request_id": request_id_var.get()}

    @app.get("/api/v1/members/{member_id}")
    async def member(member_id: str) -> dict[str, str]:
        return {"id": member_id}

    return app


def _lineas(salida: str) -> list[dict[str, object]]:
    return [json.loads(linea) for linea in salida.splitlines() if linea.startswith("{")]


async def test_acceso_sin_query_ni_cabeceras_y_request_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=postgresql+asyncpg://apex:x@db:5432/apex\n"
        "JWT_PRIVATE_KEY_PATH=/k.pem\nCRYPTO_PROVIDER=local\nCRYPTO_LOCAL_KEK_PATH=/kek\n"
        'UPLOADS_DIR=/data\nCORS_ORIGINS=["http://localhost"]\n'
        "COOKIE_SECURE=true\n",  # sin ENV es producción: M-9 (E3)
        encoding="utf-8",
    )
    configure_logging(load_settings(env_file=env))

    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://pruebas") as c:
        r = await c.get(
            "/api/v1/members?q=1020304",
            headers={"Authorization": f"Bearer {JWT}", "X-Request-ID": "inyectado\nfalso"},
        )
        r2 = await c.get("/api/v1/members/abc-123")

    assert r.status_code == 200
    request_id = r.headers["X-Request-ID"]
    assert request_id and request_id != "inyectado\nfalso"
    assert r.json()["request_id"] == request_id
    assert r2.headers["X-Request-ID"] != request_id

    salida = capsys.readouterr().out
    assert "1020304" not in salida
    assert "eyJ" not in salida
    assert "inyectado" not in salida
    lineas = _lineas(salida)
    acceso = [linea for linea in lineas if linea.get("message") == "http_request"]
    assert len(acceso) == 2
    primera = acceso[0]
    assert primera["path"] == "/api/v1/members"
    assert primera["method"] == "GET"
    assert primera["status"] == 200
    assert isinstance(primera["duration_ms"], int | float)
    assert primera["request_id"] == request_id
    assert acceso[1]["path"] in ("/api/v1/members/{member_id}", "/api/v1/members/abc-123")
    interno = [linea for linea in lineas if linea.get("message") == "buscando socios"]
    assert interno and interno[0]["request_id"] == request_id
