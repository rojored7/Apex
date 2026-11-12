"""`GET /audit/signatures/latest` y los campos de firmas de `POST /audit/verify` y
`GET /audit/verify/last` (S6-A3, US-142; S6-D10, S6-D36, S6-D62). Rojo A3.

Contrato:
- `GET /audit/signatures/latest` (admin): 200 `{latest, last_valid, is_late, state}`; `latest` y
  `last_valid` son `null` o `{through_seq, signed_at, algorithm}` (nunca hash, firma ni llave);
  `latest` es la última fila de `audit.signatures`; `last_valid` sale de la última verificación
  (nulo sin verificaciones); `state` es el de esa verificación (`none` sin verificaciones, `ok` o
  `invalid`); `is_late` es verdadero cuando hay filas sin firmar desde hace más de 48 h (a las 49 h
  sí, a las 47 h no); `Cache-Control: no-store`; coach y socio 403, sin token 401; consume la
  cubeta `staff-read` (la 121.ª del minuto da 429); no cae en `GET /audit/{seq}` (ruta declarada
  antes);
- `POST /audit/verify` y `GET /audit/verify/last` ampliados con las seis columnas de firmas:
  valores con firmas, `signatures_checked = 0` sin ellas y todos nulos para verificaciones viejas
  (guardadas antes de `0022`).
La cadena y las firmas viven en la transacción de la prueba; `app_http` comparte esa sesión.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import ZERO_HASH
from app.core.audit_verify import AuditVerification
from app.core.clock import FrozenClock, current_clock
from app.core.context import SYSTEM_USER_ID
from tests.audit._apoyo import CAMPOS_FIRMAS, CAMPOS_RESULTADO, VERIFY, VERIFY_LAST
from tests.audit.conftest import CadenaDePrueba
from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.factories.signatures import cadena_con_firmas, firmar_hasta

LATEST = "/api/v1/audit/signatures/latest"
CAMPOS_LATEST = {"latest", "last_valid", "is_late", "state", "verified_at"}
CAMPOS_FIRMA = {"through_seq", "signed_at", "algorithm"}
LIMITE_DE_LECTURAS = 120

pytestmark = pytest.mark.usefixtures("firmador")


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


async def _latest(app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras) -> Any:
    r = await app_http.get(LATEST, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    return r.json()


# Acceso y forma ----------------------------------------------------------------------------------


async def test_admin_recibe_200_con_la_forma_exacta_y_no_store(
    app_http: AsyncClient,
    session: AsyncSession,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(5)
    ultimo = await audit_chain_factory.last_seq()
    await firmar_hasta(session, ultimo)

    r = await app_http.get(LATEST, headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.json()
    assert set(cuerpo) == CAMPOS_LATEST
    assert set(cuerpo["latest"]) == CAMPOS_FIRMA
    assert cuerpo["latest"]["through_seq"] == ultimo and cuerpo["latest"]["algorithm"] == "Ed25519"
    assert "apx1." not in r.text and "hash" not in r.text and "key_id" not in r.text


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_socio_reciben_403(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, rol: str
) -> None:
    quien = await usuario_real(rol)

    r = await app_http.get(LATEST, headers=cabeceras(quien))

    assert r.status_code == 403, r.text


async def test_sin_token_401(app_http: AsyncClient) -> None:
    r = await app_http.get(LATEST)
    assert r.status_code == 401, r.text


async def test_no_cae_en_el_detalle_por_seq(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await app_http.get(LATEST, headers=cabeceras(admin))
    assert r.status_code == 200, r.text  # si cayera en `/audit/{seq}` sería 422


async def test_la_121_del_minuto_da_429_en_staff_read(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    for numero in range(LIMITE_DE_LECTURAS):
        r = await app_http.get(LATEST, headers=cabeceras(admin))
        assert r.status_code == 200, (numero, r.text)

    r = await app_http.get(LATEST, headers=cabeceras(admin))

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1


def test_openapi_declara_la_ruta_con_401_403_y_429(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"]["/api/v1/audit/signatures/latest"]["get"]
    assert {"200", "401", "403", "429"} <= set(operacion["responses"])


# Sin firmas y sin verificaciones -----------------------------------------------------------------


async def test_sin_firmas_ni_verificaciones_todo_es_nulo_y_el_estado_none(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    cuerpo = await _latest(app_http, admin, cabeceras)

    assert cuerpo == {
        "latest": None,
        "last_valid": None,
        "is_late": False,
        "state": "none",
        "verified_at": None,
    }


async def test_con_firmas_pero_sin_verificaciones_last_valid_es_nulo(
    app_http: AsyncClient,
    session: AsyncSession,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(4)
    await firmar_hasta(session, await audit_chain_factory.last_seq())

    cuerpo = await _latest(app_http, admin, cabeceras)

    assert cuerpo["latest"] is not None
    assert cuerpo["last_valid"] is None
    assert cuerpo["state"] == "none"


# Después de verificar ----------------------------------------------------------------------------


async def test_tras_verificar_last_valid_y_state_ok(
    app_http: AsyncClient,
    session: AsyncSession,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(3)
    await cadena_con_firmas(session, (3, 4))
    ultimo = await audit_chain_factory.last_seq()  # antes: la verificación agrega su fila `verify`
    verificar = await app_http.post(VERIFY, headers=cabeceras(admin))
    assert verificar.status_code == 200, verificar.text

    cuerpo = await _latest(app_http, admin, cabeceras)

    assert cuerpo["state"] == "ok" and cuerpo["is_late"] is False
    assert set(cuerpo["last_valid"]) == CAMPOS_FIRMA
    assert cuerpo["last_valid"]["through_seq"] == cuerpo["latest"]["through_seq"] == ultimo
    assert cuerpo["last_valid"]["algorithm"] == "Ed25519"


async def test_tras_verificar_una_cadena_reescrita_el_estado_es_invalid(
    app_http: AsyncClient,
    session: AsyncSession,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(3)
    await cadena_con_firmas(session, (3, 4))
    primera_firma = (await _latest(app_http, admin, cabeceras))["latest"]["through_seq"]
    assert primera_firma > 0
    await audit_chain_factory.tamper(
        await audit_chain_factory.last_seq(), "after", {"n": 0, "alterado": True}, rehash=True
    )
    verificar = await app_http.post(VERIFY, headers=cabeceras(admin))
    assert verificar.status_code == 200, verificar.text

    cuerpo = await _latest(app_http, admin, cabeceras)

    assert verificar.json()["ok"] is False
    assert cuerpo["state"] == "invalid"


# is_late -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(("horas", "atrasada"), [(47, False), (49, True)])
async def test_is_late_con_filas_sin_firmar_pasadas_las_48_horas(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    audit_chain_factory: CadenaDePrueba,
    reloj: FrozenClock,
    horas: int,
    atrasada: bool,
) -> None:
    admin = await usuario_real("admin")  # su token se emite ahora y dura 15 minutos
    reloj.advance(hours=-horas)  # las filas nacen `horas` antes de «ahora»
    await audit_chain_factory.make(3)
    await firmar_hasta(session, await audit_chain_factory.last_seq())
    await audit_chain_factory.make(2)  # filas nuevas, sin firmar
    reloj.advance(hours=horas)  # de vuelta a «ahora»: el token sigue vigente

    cuerpo = await _latest(app_http, admin, cabeceras)

    assert cuerpo["is_late"] is atrasada


# POST /audit/verify y GET /audit/verify/last -----------------------------------------------------


async def test_post_verify_trae_las_seis_columnas_de_firmas(
    app_http: AsyncClient,
    session: AsyncSession,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(3)
    await cadena_con_firmas(session, (3, 4, 5))
    ultimo = await audit_chain_factory.last_seq()  # antes: la verificación agrega su fila `verify`

    r = await app_http.post(VERIFY, headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == CAMPOS_RESULTADO and CAMPOS_FIRMAS <= set(cuerpo)
    assert (cuerpo["signatures_checked"], cuerpo["signatures_valid"]) == (3, 3)
    assert cuerpo["first_invalid_signature_seq"] is None
    assert cuerpo["last_valid_signature_seq"] == ultimo
    assert cuerpo["last_valid_signature_algorithm"] == "Ed25519"
    assert cuerpo["last_valid_signature_at"] is not None
    assert "apx1." not in r.text


async def test_get_verify_last_devuelve_los_mismos_campos_que_el_post(
    app_http: AsyncClient,
    session: AsyncSession,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(3)
    await cadena_con_firmas(session, (3, 4))
    post = (await app_http.post(VERIFY, headers=cabeceras(admin))).json()

    r = await app_http.get(VERIFY_LAST, headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    ultimo = r.json()
    assert {k: ultimo[k] for k in CAMPOS_FIRMAS} == {k: post[k] for k in CAMPOS_FIRMAS}
    assert ultimo["signatures_checked"] == 2


async def test_sin_firmas_el_post_dice_checked_cero(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(3)

    r = await app_http.post(VERIFY, headers=cabeceras(admin))

    cuerpo = r.json()
    assert r.status_code == 200 and cuerpo["ok"] is True
    assert (cuerpo["signatures_checked"], cuerpo["signatures_valid"]) == (0, 0)
    assert cuerpo["last_valid_signature_seq"] is None


async def test_una_verificacion_vieja_muestra_las_seis_columnas_nulas(
    app_http: AsyncClient,
    session: AsyncSession,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    ahora = current_clock().now_utc()
    session.add(
        AuditVerification(
            started_at=ahora,
            finished_at=ahora,
            through_seq=10,
            through_hash=ZERO_HASH,
            rows_checked=10,
            ok=True,
            triggered_by=SYSTEM_USER_ID,
            source="api",
            created_by=SYSTEM_USER_ID,
        )
    )
    await session.flush()

    r = await app_http.get(VERIFY_LAST, headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == CAMPOS_RESULTADO
    assert {k: cuerpo[k] for k in CAMPOS_FIRMAS} == dict.fromkeys(CAMPOS_FIRMAS)
    cuerpo_latest = await _latest(app_http, admin, cabeceras)
    assert cuerpo_latest["last_valid"] is None and cuerpo_latest["state"] == "none"


async def test_verified_at_es_la_fecha_de_la_verificacion_de_la_que_sale_el_estado(
    app_http: AsyncClient,
    session: AsyncSession,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    audit_chain_factory: CadenaDePrueba,
) -> None:
    await audit_chain_factory.make(3)
    await cadena_con_firmas(session, (3,))
    assert (await _latest(app_http, admin, cabeceras))["verified_at"] is None
    verificar = await app_http.post(VERIFY, headers=cabeceras(admin))

    cuerpo = await _latest(app_http, admin, cabeceras)

    assert cuerpo["verified_at"] == verificar.json()["finished_at"]
