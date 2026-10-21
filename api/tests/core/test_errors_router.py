"""Los handlers responden siempre el envelope `{ error: {...} }` (US-017, T3, T7 y T9)."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.errors import (
    ERROR_RESPONSES,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationFailed,
    register_error_handlers,
)

EXISTENTE = UUID("11111111-2222-3333-4444-555555555555")
SQL_SECRETO = "SELECT * FROM members WHERE document = '1020304' AND clave = 'super-secreto'"


class PagoIn(BaseModel):
    amount_cop: int


def _app() -> FastAPI:
    app = FastAPI(responses=ERROR_RESPONSES)
    register_error_handlers(app)

    @app.get("/conflicto")
    async def conflicto() -> dict[str, str]:
        raise ConflictError(
            "member_duplicate",
            "Ya existe un socio con este documento",
            field="document",
            existing_id=EXISTENTE,
        )

    @app.post("/pagos")
    async def pagos(pago: PagoIn) -> dict[str, int]:
        return {"amount_cop": pago.amount_cop}

    @app.get("/explota")
    async def explota() -> dict[str, str]:
        raise RuntimeError(SQL_SECRETO)

    @app.get("/dominio")
    async def dominio() -> dict[str, str]:
        raise DomainError("plan_inactive", "El plan está inactivo")

    @app.get("/sin-permiso")
    async def sin_permiso() -> dict[str, str]:
        raise ForbiddenError(message="Solo un administrador puede anular")

    @app.get("/sin-sesion")
    async def sin_sesion() -> dict[str, str]:
        raise UnauthorizedError()

    @app.get("/no-hay")
    async def no_hay() -> dict[str, str]:
        raise NotFoundError("member_not_found", "No existe el socio")

    @app.get("/invalido")
    async def invalido() -> dict[str, str]:
        raise ValidationFailed("start_date_too_old", "La fecha es muy antigua", field="start_date")

    return app


@pytest.fixture
def cliente() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=_app(), raise_app_exceptions=False),
        base_url="http://pruebas",
    )


async def test_conflicto_devuelve_exactamente_el_envelope(cliente: AsyncClient) -> None:
    async with cliente:
        r = await cliente.get("/conflicto")
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {
        "error": {
            "code": "member_duplicate",
            "message": "Ya existe un socio con este documento",
            "field": "document",
            "existing_id": str(EXISTENTE),
        }
    }


async def test_validacion_422_con_field_y_sin_el_valor(cliente: AsyncClient) -> None:
    async with cliente:
        r = await cliente.post("/pagos", json={"amount_cop": 12.5})
    assert r.status_code == 422
    cuerpo = r.json()
    assert cuerpo["error"]["code"] == "validation_error"
    assert cuerpo["error"]["field"] == "amount_cop"
    assert "amount_cop" in cuerpo["error"]["message"]
    assert "12.5" not in r.text
    assert "existing_id" not in cuerpo["error"]


async def test_500_no_filtra_traza_ni_sql(cliente: AsyncClient) -> None:
    async with cliente:
        r = await cliente.get("/explota")
    assert r.status_code == 500
    assert r.json() == {
        "error": {
            "code": "internal_error",
            "message": "Ocurrió un error inesperado. Intente de nuevo.",
        }
    }
    assert "1020304" not in r.text
    assert "super-secreto" not in r.text
    assert "Traceback" not in r.text


async def test_ruta_inexistente_da_404_con_envelope(cliente: AsyncClient) -> None:
    async with cliente:
        r = await cliente.get("/api/v1/no-existe")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["error"]["code"] == "not_found"
    assert "field" not in r.json()["error"]


async def test_metodo_no_permitido_da_405_con_envelope(cliente: AsyncClient) -> None:
    async with cliente:
        r = await cliente.delete("/conflicto")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"


@pytest.mark.parametrize(
    ("ruta", "estado", "codigo"),
    [
        ("/dominio", 400, "plan_inactive"),
        ("/sin-permiso", 403, "forbidden"),
        ("/sin-sesion", 401, "unauthorized"),
        ("/no-hay", 404, "member_not_found"),
        ("/invalido", 422, "start_date_too_old"),
    ],
)
async def test_jerarquia_de_errores(
    cliente: AsyncClient, ruta: str, estado: int, codigo: str
) -> None:
    async with cliente:
        r = await cliente.get(ruta)
    assert r.status_code == estado
    assert set(r.json()) == {"error"}
    assert r.json()["error"]["code"] == codigo
    assert r.json()["error"]["message"]


def test_mensajes_por_defecto_en_espanol() -> None:
    assert (
        "sesión" in UnauthorizedError().message.lower()
        or "inicia" in UnauthorizedError().message.lower()
    )
    assert ForbiddenError().status == 403
    assert NotFoundError().message
    assert ConflictError("x", "y").code == "x"
