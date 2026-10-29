"""`GET /api/v1/audit/{seq}` (S4A-B4, US-103; S4A-D17, S4A-D45, S4A-D46, S4A-D52).

Contrato:
- admin: 200 `AuditDetail` (`CAMPOS_DETAIL` exactos; `changes` con `CAMPOS_CHANGE`) y
  `Cache-Control: no-store`; el cuerpo nunca contiene `apx1.` ni el teléfono o el correo en claro;
- 404 `audit_entry_not_found` para un `seq` que no existe, también `MAX_SEQ` (2**63 - 1);
- 422 `validation_error` con `field="seq"` si no es entero, es 0 o negativo, o pasa de `MAX_SEQ`
  (`2**63` y `99999999999999999999`): nunca 500 (S4A-D46);
- coach y member 403; sin token 401;
- `GET /audit/verify/last` no cae en `{seq}` (200, `null` sin verificaciones);
- `staff-read`: la 121.ª lectura del minuto da 429 y la 121.ª de otro admin pasa;
- OpenAPI: 404, 422 y 429 declarados; `seq` entero entre 1 y `MAX_SEQ`.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from tests.audit._apoyo import (
    CAMPOS_CHANGE,
    CAMPOS_DETAIL,
    CORREO_NUEVO,
    TELEFONO_NUEVO,
    VERIFY_LAST,
    Actividad,
    ruta_entrada,
    sembrar_actividad,
)
from tests.audit.conftest import CadenaDePrueba
from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.factories.members import KNOWN_NORMALIZED

LIMITE_DE_LECTURAS = 120
MAX_SEQ = 2**63 - 1


@pytest.fixture
async def actividad(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
) -> Actividad:
    return await sembrar_actividad(session, ana=ana, juan=juan)


async def test_admin_recibe_el_detalle_sin_blobs(
    app_http: AsyncClient, actividad: Actividad, ana: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await app_http.get(ruta_entrada(5), headers=cabeceras(ana))

    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.json()
    assert set(cuerpo) == CAMPOS_DETAIL
    assert (cuerpo["seq"], cuerpo["action"], cuerpo["user_name"]) == (5, "update", "juan.rios")
    assert [c["field"] for c in cuerpo["changes"]] == ["email", "phone"]
    assert all(set(c) == CAMPOS_CHANGE for c in cuerpo["changes"])
    telefono = next(c for c in cuerpo["changes"] if c["field"] == "phone")
    assert telefono["encrypted"] is True
    assert set(telefono["before"]) == {"encrypted", "key_id", "alg"}
    assert cuerpo["before"]["phone_idx"] == "***"
    assert "apx1." not in r.text
    for valor in (*KNOWN_NORMALIZED, TELEFONO_NUEVO, CORREO_NUEVO):
        assert valor not in r.text, valor


async def test_el_insert_de_la_socia_tampoco_lleva_blobs(
    app_http: AsyncClient, actividad: Actividad, ana: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await app_http.get(ruta_entrada(4), headers=cabeceras(ana))
    assert r.status_code == 200, r.text
    assert r.json()["after"]["document"]["encrypted"] is True
    assert "apx1." not in r.text


@pytest.mark.parametrize("seq", [12, 999, MAX_SEQ])
async def test_seq_que_no_existe_da_404(
    app_http: AsyncClient,
    actividad: Actividad,
    ana: UsuarioPrueba,
    cabeceras: Cabeceras,
    seq: int,
) -> None:
    r = await app_http.get(ruta_entrada(seq), headers=cabeceras(ana))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "audit_entry_not_found"


@pytest.mark.parametrize(
    "seq",
    ["abc", "0", "-1", "1.5", str(2**63), "99999999999999999999"],
    ids=["texto", "cero", "negativo", "decimal", "dos-a-la-63", "veinte-nueves"],
)
async def test_seq_invalido_da_422_y_nunca_500(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    ana: UsuarioPrueba,
    cabeceras: Cabeceras,
    seq: str,
) -> None:
    r = await app_http.get(ruta_entrada(seq), headers=cabeceras(ana))
    assert r.status_code == 422, (seq, r.status_code, r.text)
    assert (r.json()["error"]["code"], r.json()["error"]["field"]) == ("validation_error", "seq")


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_member_reciben_403(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    r = await app_http.get(ruta_entrada(1), headers=cabeceras(quien))
    assert r.status_code == 403, r.text


async def test_sin_token_401(app_http: AsyncClient) -> None:
    r = await app_http.get(ruta_entrada(1))
    assert r.status_code == 401, r.text


async def test_verify_last_no_cae_en_seq(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    ana: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    r = await app_http.get(VERIFY_LAST, headers=cabeceras(ana))
    assert r.status_code == 200, r.text
    assert r.json() is None


async def test_la_121_del_minuto_da_429_y_otro_admin_pasa(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    ana: UsuarioPrueba,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    otro = await usuario_real("admin")
    for numero in range(LIMITE_DE_LECTURAS):
        r = await app_http.get(ruta_entrada(1), headers=cabeceras(ana))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(ruta_entrada(1), headers=cabeceras(ana))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    r = await app_http.get(ruta_entrada(1), headers=cabeceras(otro))
    assert r.status_code == 200, r.text


async def test_un_404_tambien_consume_la_cubeta(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    ana: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    """Recorrer `seq` inexistentes no es un barrido gratis (como `members-detail`, M-2)."""
    for numero in range(LIMITE_DE_LECTURAS):
        r = await app_http.get(ruta_entrada(500_000 + numero), headers=cabeceras(ana))
        assert r.status_code == 404, (numero, r.text)
    r = await app_http.get(ruta_entrada(1), headers=cabeceras(ana))
    assert r.status_code == 429, r.text


def test_openapi_declara_404_422_429_y_el_rango_de_seq(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"]["/api/v1/audit/{seq}"]["get"]
    assert {"401", "403", "404", "422", "429"} <= set(operacion["responses"])
    [parametro] = [p for p in operacion["parameters"] if p["name"] == "seq"]
    esquema = parametro["schema"]
    assert (esquema["type"], esquema["minimum"], esquema["maximum"]) == ("integer", 1, MAX_SEQ)
