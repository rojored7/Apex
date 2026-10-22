"""`/settings/privacy` con el api real (US-057 T5; S2-D15)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.settings._apoyo import API, PRIVACY_DEFAULTS, PRIVACY_OK

RUTA = f"{API}/settings/privacy"


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


async def test_sin_fila_la_politica_no_esta_publicada(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await app_http.get(RUTA, headers=cabeceras(admin))
    assert r.status_code == 200
    assert r.json()["value"] == PRIVACY_DEFAULTS and r.json()["version"] == 0


async def test_admin_publica_y_la_version_sube_de_a_uno(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await app_http.patch(
        RUTA, headers=cabeceras(admin), json={"value": PRIVACY_OK, "version": 0}
    )
    assert r.status_code == 200 and r.json()["version"] == 1
    assert r.json()["value"] == PRIVACY_OK
    r = await app_http.patch(
        RUTA,
        headers=cabeceras(admin),
        json={"value": {**PRIVACY_OK, "policy_version": "2026-11"}, "version": 1},
    )
    assert r.status_code == 200 and r.json()["version"] == 2
    assert r.json()["value"]["policy_version"] == "2026-11"


async def test_sin_texto_da_422_value_policy_text(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    sin_texto = {k: v for k, v in PRIVACY_OK.items() if k != "policy_text"}
    r = await app_http.patch(
        RUTA, headers=cabeceras(admin), json={"value": sin_texto, "version": 0}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["field"] == "value.policy_text"


@pytest.mark.parametrize("metodo", ["GET", "PATCH"])
async def test_coach_recibe_403(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, metodo: str
) -> None:
    coach = await usuario_real("coach")
    cuerpo = {"value": PRIVACY_OK, "version": 0} if metodo == "PATCH" else None
    r = await app_http.request(metodo, RUTA, headers=cabeceras(coach), json=cuerpo)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
