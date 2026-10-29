"""`POST /audit/verify` y `GET /audit/verify/last` (S4A-B3, US-104; S4A-D14, S4A-D47).

Contrato:
- admin: 200 `VerifyResultOut` (forma exacta, sin `before`, `after` ni `through_hash`), `source =
  "api"` y `triggered_by` del admin; con `SYNC_VERIFY_MAX_ROWS` bajo, 202 `VerifyStartedOut
  {status: "running", last}` con `Cache-Control: no-store`; 409 `verification_running` con el
  candado tomado;
- `audit-verify`: la 4.ª petición del minuto da 429; `audit-verify-hour`: con `reloj.advance` de
  2 min cada tres, la 21.ª de la hora da 429;
- `GET /audit/verify/last`: 200 `null` sin verificaciones, la última después; sin 429;
- coach 403, sin token 401 (las dos rutas); el 202, el 409 y el 429 están en el OpenAPI del
  `POST` y el `GET` no declara 429 ni 422; `/audit/99` aún no existe (404 de FastAPI).
La cadena vive en la transacción de la prueba (`audit_chain_factory`); `app_http` comparte esa
sesión.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.clock import FrozenClock
from tests.audit._apoyo import CAMPOS_RESULTADO, VERIFY, VERIFY_LAST
from tests.audit.conftest import CadenaDePrueba, audit_service
from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba


@pytest.fixture
async def sin_tareas_pendientes(app_http: AsyncClient) -> AsyncIterator[None]:
    """Cancela una tarea 202 antes de que `api_prueba` cierre el engine."""
    try:
        yield
    finally:
        await audit_service.cancel_background_verifications()


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


def _forma(cuerpo: dict[str, Any]) -> None:
    assert set(cuerpo) == CAMPOS_RESULTADO, cuerpo
    assert "before" not in cuerpo and "after" not in cuerpo and "through_hash" not in cuerpo


async def test_admin_verifica_y_recibe_200_con_el_resultado(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    ultimo = await audit_chain_factory.make(40)

    r = await app_http.post(VERIFY, headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    _forma(cuerpo)
    assert cuerpo["ok"] is True and cuerpo["broken_at_seq"] is None
    assert cuerpo["through_seq"] == cuerpo["rows_checked"] >= ultimo
    assert (cuerpo["source"], cuerpo["triggered_by"]) == ("api", str(admin.id))
    assert r.headers["cache-control"] == "no-store"


async def test_cadena_rota_responde_200_con_ok_false_y_el_seq(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    await audit_chain_factory.make(40)
    await audit_chain_factory.tamper(17, "after", {"n": "alterado"})

    r = await app_http.post(VERIFY, headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    assert (r.json()["ok"], r.json()["broken_at_seq"]) == (False, 17)


@pytest.mark.usefixtures("umbral_bajo", "sin_tareas_pendientes")
async def test_por_encima_del_umbral_responde_202_con_la_ultima(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    await audit_chain_factory.make(3)
    primera = await app_http.post(VERIFY, headers=cabeceras(admin))
    assert primera.status_code == 200, primera.text
    await audit_chain_factory.make(20)

    r = await app_http.post(VERIFY, headers=cabeceras(admin))

    assert r.status_code == 202, r.text
    assert r.json() == {"status": "running", "last": primera.json()}
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.usefixtures("candado_tomado")
async def test_con_otra_verificacion_en_curso_responde_409(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    await audit_chain_factory.make(5)

    r = await app_http.post(VERIFY, headers=cabeceras(admin))

    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "verification_running"


# Cubetas (M-3) ---------------------------------------------------------------------------------


async def test_la_cuarta_peticion_del_minuto_da_429(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    await audit_chain_factory.make(5)
    for _ in range(3):
        assert (await app_http.post(VERIFY, headers=cabeceras(admin))).status_code == 200

    r = await app_http.post(VERIFY, headers=cabeceras(admin))

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert "retry-after" in r.headers
    assert (await app_http.get(VERIFY_LAST, headers=cabeceras(admin))).status_code == 200


async def test_la_peticion_21_de_la_hora_da_429(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    reloj: FrozenClock,
) -> None:
    await audit_chain_factory.make(5)
    for i in range(20):
        if i and i % 3 == 0:
            reloj.advance(minutes=2)  # nueva ventana de minuto, misma hora
        r = await app_http.post(VERIFY, headers=cabeceras(admin))
        assert r.status_code == 200, (i, r.text)

    # 20 en 6 avances de 2 min: la del minuto lleva 2 (18 y 19), la de la hora 20.
    r = await app_http.post(VERIFY, headers=cabeceras(admin))

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"


# GET /audit/verify/last --------------------------------------------------------------------------


async def test_last_sin_verificaciones_es_null_y_despues_la_ultima_sin_429(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    await audit_chain_factory.make(5)
    vacia = await app_http.get(VERIFY_LAST, headers=cabeceras(admin))
    assert vacia.status_code == 200, vacia.text
    assert vacia.json() is None

    hecha = await app_http.post(VERIFY, headers=cabeceras(admin))
    for _ in range(10):
        r = await app_http.get(VERIFY_LAST, headers=cabeceras(admin))
        assert r.status_code == 200, r.text

    assert r.json() == hecha.json()
    _forma(r.json())
    assert r.headers["cache-control"] == "no-store"


# Roles y contrato --------------------------------------------------------------------------------


@pytest.mark.parametrize(("metodo", "ruta"), [("post", VERIFY), ("get", VERIFY_LAST)])
async def test_coach_recibe_403_y_sin_token_401(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    metodo: str,
    ruta: str,
) -> None:
    coach = await usuario_real("coach")

    prohibido = await app_http.request(metodo.upper(), ruta, headers=cabeceras(coach))
    anonimo = await app_http.request(metodo.upper(), ruta)

    assert prohibido.status_code == 403, prohibido.text
    assert anonimo.status_code == 401, anonimo.text


def test_el_openapi_declara_202_409_y_429_en_el_post_y_nada_de_eso_en_el_get(
    api_prueba: Any,
) -> None:
    esquema = api_prueba.openapi()
    post = esquema["paths"][VERIFY]["post"]["responses"]
    assert {"200", "202", "409", "429", "401", "403"} <= set(post)
    assert "422" not in post
    assert post["202"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/VerifyStartedOut"
    )
    assert post["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/VerifyResultOut")
    get = esquema["paths"][VERIFY_LAST]["get"]["responses"]
    assert {"200", "401", "403"} <= set(get)
    assert not {"422", "429", "409"} & set(get)


async def test_verify_last_no_cae_en_una_ruta_de_seq_que_aun_no_existe(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await app_http.get("/api/v1/audit/99", headers=cabeceras(admin))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "not_found"
