"""`GET /api/v1/crypto/keys` (S6-B1, US-143; S6-D12, S6-D13, S6-D44, S6-D52). Rojo B1.

Contrato HTTP: admin 200 con `{items, total, limit, offset, summary}`; coach y socio 403; sin
token 401; `Cache-Control: no-store`; cubeta `staff-read` (120 por minuto: la 121.ª da 429); 422
en filtros inválidos y en `limit` fuera de 1..200; la respuesta no lleva material ni referencias.
`create_app` cablea `set_audit_writer(audit.record)` (S6-D52).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.crypto import router as keys_router
from app.core.crypto.models import CryptoKey
from tests.conftest import Cabeceras, CrearUsuario
from tests.crypto.conftest import KEYS_URL, ClienteAdmin, llaves_mixtas

LIMITE_DE_LECTURAS = 120


@pytest.fixture
async def con_llaves(
    session: AsyncSession, bus_listo: object, proveedor_local: object
) -> dict[str, CryptoKey]:
    return await llaves_mixtas(session, proveedor_local)  # type: ignore[arg-type]


async def test_admin_recibe_200_con_la_forma_de_page_mas_summary(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey]
) -> None:
    r = await cliente_admin.get()

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {"items", "total", "limit", "offset", "summary"}
    assert (cuerpo["total"], cuerpo["limit"], cuerpo["offset"]) == (
        12,
        25,
        0,
    )  # S9-A1: +1 por `athlete.metric` (antes 11)
    assert len(cuerpo["items"]) == 12
    assert set(cuerpo["summary"]) == {
        "active_count",
        "operations_today",
        "running_jobs",
        "provider",
    }
    assert cuerpo["summary"]["active_count"] == 11  # S9-A1: +1 (antes 10)
    assert cuerpo["summary"]["provider"]["names"] == ["local"]


async def test_la_respuesta_lleva_no_store(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey]
) -> None:
    r = await cliente_admin.get()

    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_socio_reciben_403(
    app_http: object, usuario_real: CrearUsuario, cabeceras: Cabeceras, rol: str
) -> None:
    quien = await usuario_real(rol)

    r = await app_http.get(KEYS_URL, headers=cabeceras(quien))  # type: ignore[attr-defined]

    assert r.status_code == 403, r.text


async def test_sin_token_401(app_http: object) -> None:
    r = await app_http.get(KEYS_URL)  # type: ignore[attr-defined]

    assert r.status_code == 401, r.text


async def test_filtros_por_query_string_llegan_al_inventario(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey]
) -> None:
    r = await cliente_admin.get(purpose="index", limit=2, offset=1)

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["total"], len(cuerpo["items"]), cuerpo["limit"], cuerpo["offset"]) == (
        3,
        2,
        2,
        1,
    )
    assert {i["purpose"] for i in cuerpo["items"]} == {"index"}
    q = (await cliente_admin.get(q="phone")).json()
    assert {i["data_class"] for i in q["items"]} == {"member.phone"}


@pytest.mark.parametrize(
    "params",
    [
        {"purpose": "decrypt"},
        {"state": "borrada"},
        {"provider": "vault"},
        {"data_class": "sin_punto"},
        {"data_class": "Member.Document"},
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"q": "x" * 101},
    ],
)
async def test_filtros_invalidos_dan_422(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey], params: dict[str, object]
) -> None:
    r = await cliente_admin.get(**params)

    assert r.status_code == 422, (params, r.text)
    assert r.json()["error"]["code"] == "validation_error"


async def test_la_121_del_minuto_da_429_en_staff_read(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey]
) -> None:
    for numero in range(LIMITE_DE_LECTURAS):
        r = await cliente_admin.get(limit=1)
        assert r.status_code == 200, (numero, r.text)

    r = await cliente_admin.get(limit=1)

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1


async def test_la_respuesta_no_trae_material_ni_referencias(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey]
) -> None:
    r = await cliente_admin.get()

    assert r.status_code == 200, r.text
    for prohibido in ("wrapped_material", "public_key", "apex-sign-audit", "apxw1", "vault:"):
        assert prohibido not in r.text, prohibido


async def test_listar_no_escribe_crypto_ops(
    cliente_admin: ClienteAdmin, session: AsyncSession, con_llaves: dict[str, CryptoKey]
) -> None:
    from sqlalchemy import text

    await cliente_admin.get()  # la primera lectura puede dejar el `refresh` del keyring
    antes = await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops"))

    await cliente_admin.get()
    await cliente_admin.get(purpose="sign")

    assert await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops")) == antes


def test_el_openapi_declara_la_ruta_con_sus_codigos(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"][KEYS_URL]["get"]

    assert {"200", "401", "403", "422", "429"} <= set(operacion["responses"])


# Puerta de auditoría (S6-D52) ------------------------------------------------------------------


def test_create_app_cablea_la_puerta_de_auditoria_con_audit_record(api_prueba: FastAPI) -> None:
    assert keys_router.audit_writer_registered()
    assert keys_router._audit_writer is audit.record


def test_sin_audit_writer_la_app_queda_sin_puerta(sin_audit_writer: None) -> None:
    assert not keys_router.audit_writer_registered()
