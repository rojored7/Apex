"""`/settings/memberships` con el api real (US-058 T5; S2-D15)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.settings._apoyo import API, MEMBERSHIPS_DEFAULTS, MEMBERSHIPS_OK

RUTA = f"{API}/settings/memberships"


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


async def test_sin_fila_devuelve_los_defaults(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await app_http.get(RUTA, headers=cabeceras(admin))
    assert r.status_code == 200
    assert r.json()["value"] == MEMBERSHIPS_DEFAULTS and r.json()["version"] == 0


async def test_181_dias_de_congelacion_da_422_con_su_field(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    valor = {**MEMBERSHIPS_OK, "max_freeze_days_per_membership": 181}
    r = await app_http.patch(RUTA, headers=cabeceras(admin), json={"value": valor, "version": 0})
    assert r.status_code == 422
    assert r.json()["error"]["field"] == "value.max_freeze_days_per_membership"


async def test_0_dias_de_congelacion_da_200(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    valor = {**MEMBERSHIPS_OK, "max_freeze_days_per_membership": 0}
    r = await app_http.patch(RUTA, headers=cabeceras(admin), json={"value": valor, "version": 0})
    assert r.status_code == 200 and r.json()["version"] == 1
    assert r.json()["value"]["max_freeze_days_per_membership"] == 0


@pytest.mark.parametrize("valor", ["7", 7.5], ids=["texto", "decimal"])
async def test_no_enteros_dan_422_en_json(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, valor: object
) -> None:
    cuerpo = {"value": {**MEMBERSHIPS_OK, "expiring_days": valor}, "version": 0}
    r = await app_http.patch(RUTA, headers=cabeceras(admin), json=cuerpo)
    assert r.status_code == 422 and r.json()["error"]["field"] == "value.expiring_days"


@pytest.mark.parametrize("metodo", ["GET", "PATCH"])
async def test_coach_recibe_403(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, metodo: str
) -> None:
    coach = await usuario_real("coach")
    cuerpo = {"value": MEMBERSHIPS_OK, "version": 0} if metodo == "PATCH" else None
    r = await app_http.request(metodo, RUTA, headers=cabeceras(coach), json=cuerpo)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
