"""`GET /api/v1/crypto/cbom` (S6-B3, US-146; S6-D17, S6-D52, S6-D57, Q26, L-5). Rojo B3.

Contrato HTTP: solo admin (coach y socio 403, sin token 401); descarga JSON con las cuatro
cabeceras de `file_download` y el nombre `apex-cbom-AAAA-MM-DD.json` con la fecha de Bogota;
auditoria `export` sobre `crypto.crypto_keys` con `after = {"count": n, "format": "apex-cbom/1"}`
escrita por el puerto registrado (S6-D52), en la misma transaccion y ANTES del cuerpo; sin puerta
(o si la auditoria falla) 503 `busy` y nada descargado; cubeta `cbom-export` (2 por minuto); el
cuerpo no trae material ni referencias.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.clock import FrozenClock
from app.core.crypto import router as keys_router
from app.core.crypto.models import CryptoKey
from app.core.db import DatabaseBusy
from tests.conftest import Cabeceras, CrearUsuario
from tests.crypto.conftest import ClienteAdmin, llaves_mixtas

CBOM_URL = "/api/v1/crypto/cbom"
LIMITE_POR_MINUTO = 2
PROHIBIDOS_EN_EL_CUERPO = ("vault:", "wrapped", "apex-sign", "local:", "public_key")
CSP = "default-src 'none'; sandbox"


@pytest.fixture
async def con_llaves(
    session: AsyncSession, bus_listo: object, proveedor_local: object
) -> dict[str, CryptoKey]:
    return await llaves_mixtas(session, proveedor_local)  # type: ignore[arg-type]


async def filas_export(session: AsyncSession) -> list[Any]:
    return list(
        (
            await session.execute(
                text(
                    "SELECT * FROM audit.audit_log "
                    "WHERE table_name = 'crypto.crypto_keys' AND action = 'export' ORDER BY seq"
                )
            )
        ).mappings()
    )


# Acceso -----------------------------------------------------------------------------------------


async def test_admin_recibe_200_con_el_cbom(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey]
) -> None:
    r = await cliente_admin.get(CBOM_URL)

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["format"] == "apex-cbom/1"
    assert len(cuerpo["keys"]) == 10
    assert set(cuerpo) == {
        "format",
        "generated_at",
        "app_version",
        "provider",
        "keys",
        "fixed_algorithms",
        "tls",
    }


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_socio_reciben_403_y_no_se_audita(
    app_http: Any, session: AsyncSession, usuario_real: CrearUsuario, cabeceras: Cabeceras, rol: str
) -> None:
    quien = await usuario_real(rol)

    r = await app_http.get(CBOM_URL, headers=cabeceras(quien))

    assert r.status_code == 403, r.text
    assert await filas_export(session) == []


async def test_sin_token_401(app_http: Any) -> None:
    r = await app_http.get(CBOM_URL)

    assert r.status_code == 401, r.text


# Cabeceras de la descarga -----------------------------------------------------------------------


async def test_cabeceras_de_descarga(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey], reloj: FrozenClock
) -> None:
    r = await cliente_admin.get(CBOM_URL)

    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/json; charset=utf-8"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["content-disposition"] == "attachment; filename=apex-cbom-2026-10-21.json"


async def test_el_nombre_usa_la_fecha_de_bogota_no_la_de_utc(
    cliente_admin: ClienteAdmin,
    con_llaves: dict[str, CryptoKey],
    reloj: FrozenClock,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    """02:30 UTC del 22 es todavia el 21 en Bogota (UTC-5)."""
    reloj.set(datetime(2026, 10, 22, 2, 30, tzinfo=UTC))
    # el token del T0 vence a los 15 min: un admin nuevo con el reloj ya movido
    cliente_admin = ClienteAdmin(cliente_admin.http, await usuario_real("admin"), cabeceras)

    r = await cliente_admin.get(CBOM_URL)

    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"] == "attachment; filename=apex-cbom-2026-10-21.json"
    assert r.json()["generated_at"].startswith("2026-10-22T02:30")


async def test_el_nombre_cambia_con_el_dia_de_bogota(
    cliente_admin: ClienteAdmin,
    con_llaves: dict[str, CryptoKey],
    reloj: FrozenClock,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    reloj.set(datetime(2026, 10, 22, 5, 0, tzinfo=UTC))
    # el token del T0 vence a los 15 min: un admin nuevo con el reloj ya movido
    cliente_admin = ClienteAdmin(cliente_admin.http, await usuario_real("admin"), cabeceras)

    r = await cliente_admin.get(CBOM_URL)

    assert r.headers["content-disposition"] == "attachment; filename=apex-cbom-2026-10-22.json"


# Contenido --------------------------------------------------------------------------------------


async def test_el_cuerpo_no_trae_material_ni_referencias(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey]
) -> None:
    r = await cliente_admin.get(CBOM_URL)

    assert r.status_code == 200, r.text
    for prohibido in PROHIBIDOS_EN_EL_CUERPO:
        assert prohibido not in r.text, prohibido
    for item in r.json()["keys"]:
        assert "records_count" not in item and "age_days" not in item


async def test_el_cbom_cubre_las_diez_filas_en_orden_estable(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey]
) -> None:
    llaves = (await cliente_admin.get(CBOM_URL)).json()["keys"]

    orden = [(k["data_class"], k["purpose"], k["version"]) for k in llaves]
    assert orden == sorted(orden)
    assert {k["purpose"] for k in llaves} == {"encrypt", "index", "sign"}
    assert {k["state"] for k in llaves} == {"active", "decrypt_only"}


async def test_tls_declared_false_sin_dominio_y_true_con_dominio(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey], api_prueba: FastAPI
) -> None:
    sin = (await cliente_admin.get(CBOM_URL)).json()["tls"]
    api_prueba.state.settings = api_prueba.state.settings.model_copy(
        update={"APEX_DOMAIN": "apex.example.com"}
    )
    con = (await cliente_admin.get(CBOM_URL)).json()["tls"]

    assert sin == {"declared": False, "source": "configuration"}
    assert con == {"declared": True, "source": "configuration"}


async def test_app_version_sale_de_la_configuracion(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey], api_prueba: FastAPI
) -> None:
    api_prueba.state.settings = api_prueba.state.settings.model_copy(
        update={"APP_VERSION": "9f8e7d6"}
    )

    cuerpo = (await cliente_admin.get(CBOM_URL)).json()

    assert cuerpo["app_version"] == "9f8e7d6"
    assert cuerpo["provider"]["names"] == ["local"]


# Auditoria (S6-D52) -----------------------------------------------------------------------------


async def test_la_descarga_deja_una_fila_export_sobre_crypto_keys(
    cliente_admin: ClienteAdmin, session: AsyncSession, con_llaves: dict[str, CryptoKey]
) -> None:
    r = await cliente_admin.get(CBOM_URL)

    assert r.status_code == 200, r.text
    filas = await filas_export(session)
    assert len(filas) == 1
    fila = filas[0]
    assert fila["after"] == {"count": 10, "format": "apex-cbom/1"}
    assert fila["before"] is None
    assert fila["record_id"] is None
    assert fila["user_id"] == cliente_admin.admin.id


async def test_count_de_la_auditoria_es_el_numero_de_llaves_del_cuerpo(
    cliente_admin: ClienteAdmin, session: AsyncSession, con_llaves: dict[str, CryptoKey]
) -> None:
    r = await cliente_admin.get(CBOM_URL)

    (fila,) = await filas_export(session)
    assert fila["after"]["count"] == len(r.json()["keys"])


async def test_la_auditoria_pasa_por_el_escritor_registrado_en_la_misma_sesion(
    cliente_admin: ClienteAdmin,
    session: AsyncSession,
    con_llaves: dict[str, CryptoKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[tuple[AsyncSession, dict[str, Any]]] = []

    async def espia(sesion: AsyncSession, **kwargs: Any) -> Any:
        llamadas.append((sesion, kwargs))
        return await audit.record(sesion, **kwargs)

    monkeypatch.setattr(keys_router, "_audit_writer", espia)

    r = await cliente_admin.get(CBOM_URL)

    assert r.status_code == 200, r.text
    assert len(llamadas) == 1
    sesion, kwargs = llamadas[0]
    assert sesion is session
    assert kwargs["action"] == "export"
    assert kwargs["table_name"] == "crypto.crypto_keys"
    assert kwargs["record_id"] is None
    assert kwargs["before"] is None
    assert kwargs["after"] == {"count": 10, "format": "apex-cbom/1"}
    assert kwargs["user_id"] == cliente_admin.admin.id


async def test_si_la_auditoria_falla_no_se_descarga_nada(
    cliente_admin: ClienteAdmin,
    session: AsyncSession,
    con_llaves: dict[str, CryptoKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La auditoria va ANTES del cuerpo: si falla, el cuerpo no sale (S6-D52, L-5)."""

    async def falla(sesion: AsyncSession, **kwargs: Any) -> Any:
        raise DatabaseBusy()

    monkeypatch.setattr(keys_router, "_audit_writer", falla)

    r = await cliente_admin.get(CBOM_URL)

    assert r.status_code == 503, r.text
    assert r.json()["error"]["code"] == "busy"
    assert "content-disposition" not in r.headers
    assert "apex-cbom/1" not in r.text
    assert "fixed_algorithms" not in r.text
    assert await filas_export(session) == []


async def test_sin_puerta_de_auditoria_503_busy_y_nada_descargado(
    cliente_admin: ClienteAdmin,
    session: AsyncSession,
    con_llaves: dict[str, CryptoKey],
    sin_audit_writer: None,
) -> None:
    r = await cliente_admin.get(CBOM_URL)

    assert r.status_code == 503, r.text
    assert r.json()["error"]["code"] == "busy"
    assert r.headers["retry-after"] == "1"
    assert "content-disposition" not in r.headers
    assert "fixed_algorithms" not in r.text
    assert await filas_export(session) == []


# Cubeta `cbom-export` (S6-D57) ------------------------------------------------------------------


async def test_la_tercera_del_minuto_da_429_en_cbom_export(
    cliente_admin: ClienteAdmin, session: AsyncSession, con_llaves: dict[str, CryptoKey]
) -> None:
    for numero in range(LIMITE_POR_MINUTO):
        r = await cliente_admin.get(CBOM_URL)
        assert r.status_code == 200, (numero, r.text)

    r = await cliente_admin.get(CBOM_URL)

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    assert len(await filas_export(session)) == LIMITE_POR_MINUTO


async def test_el_429_no_deja_cuerpo_de_cbom(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey]
) -> None:
    for _ in range(LIMITE_POR_MINUTO):
        await cliente_admin.get(CBOM_URL)

    r = await cliente_admin.get(CBOM_URL)

    assert "content-disposition" not in r.headers
    assert "fixed_algorithms" not in r.text


async def test_cbom_export_no_gasta_staff_read(
    cliente_admin: ClienteAdmin, con_llaves: dict[str, CryptoKey]
) -> None:
    """Las lecturas de inventario (120/min) no consumen la cubeta del CBOM y viceversa."""
    for _ in range(LIMITE_POR_MINUTO):
        assert (await cliente_admin.get(CBOM_URL)).status_code == 200

    r = await cliente_admin.get("/api/v1/crypto/keys", limit=1)

    assert r.status_code == 200, r.text


# OpenAPI ----------------------------------------------------------------------------------------


def test_el_openapi_declara_la_ruta_y_su_json(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"][CBOM_URL]["get"]

    assert {"200", "401", "403", "429"} <= set(operacion["responses"])
    assert "application/json" in operacion["responses"]["200"]["content"]
