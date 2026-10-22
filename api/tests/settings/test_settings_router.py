"""Router de settings con el api real (US-054 T9; S2-D15; kit `app_http` de S2-B1).

Admin 200 en GET y PATCH; sin token 401 y coach o member 403 en las ocho rutas; secciones de
versiones futuras 404 `section_not_available`; versión vieja 409 `version_conflict`; valor
inválido 422 con `field` sin tocar la fila; auditoría `insert` y `update` con el actor real.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.settings._apoyo import (
    API,
    CUERPOS,
    DESCONOCIDAS,
    GYM_DEFAULTS,
    GYM_OK,
    NO_HABILITADAS,
    RUTAS,
    TABLA,
    fila,
    filas_de_auditoria,
)

MENSAJE_CONFLICTO = "Otra persona cambió esta sección. Recarga para ver los cambios."


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


@pytest.fixture
async def coach(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("coach")


async def _pedir(
    cliente: AsyncClient,
    metodo: str,
    ruta: str,
    cabeceras: dict[str, str] | None = None,
    cuerpo: dict[str, Any] | None = None,
) -> Response:
    return await cliente.request(metodo, f"{API}{ruta}", headers=cabeceras or {}, json=cuerpo)


def _cuerpo(metodo: str, ruta: str) -> dict[str, Any] | None:
    return CUERPOS[ruta] if metodo == "PATCH" else None


async def test_admin_lee_gym_con_defaults_en_version_0(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _pedir(app_http, "GET", "/settings/gym", cabeceras(admin))
    assert r.status_code == 200
    assert r.json() == {
        "key": "gym",
        "value": GYM_DEFAULTS,
        "version": 0,
        "updated_at": None,
        "updated_by": None,
    }


async def test_admin_guarda_y_lee_lo_guardado(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _pedir(app_http, "PATCH", "/settings/gym", cabeceras(admin), CUERPOS["/settings/gym"])
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["key"] == "gym" and cuerpo["version"] == 1 and cuerpo["value"] == GYM_OK
    assert cuerpo["updated_by"] == str(admin.id) and cuerpo["updated_at"] is not None

    leido = (await _pedir(app_http, "GET", "/settings/gym", cabeceras(admin))).json()
    assert leido == cuerpo


@pytest.mark.parametrize(("metodo", "ruta"), RUTAS)
async def test_sin_token_401_en_las_ocho_rutas(
    app_http: AsyncClient, metodo: str, ruta: str
) -> None:
    r = await _pedir(app_http, metodo, ruta, cuerpo=_cuerpo(metodo, ruta))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(("metodo", "ruta"), RUTAS)
async def test_coach_403_en_las_ocho_rutas(
    app_http: AsyncClient,
    coach: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    metodo: str,
    ruta: str,
) -> None:
    r = await _pedir(app_http, metodo, ruta, cabeceras(coach), _cuerpo(metodo, ruta))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"
    assert await filas_de_auditoria(session) == []  # el 403 no escribe nada


async def test_member_403_en_gym(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    r = await _pedir(app_http, "GET", "/settings/gym", cabeceras(socio))
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("clave", [*NO_HABILITADAS, *DESCONOCIDAS])
@pytest.mark.parametrize("metodo", ["GET", "PATCH"])
async def test_secciones_no_habilitadas_dan_404_section_not_available(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, metodo: str, clave: str
) -> None:
    cuerpo = {"value": {}, "version": 0} if metodo == "PATCH" else None
    r = await _pedir(app_http, metodo, f"/settings/{clave}", cabeceras(admin), cuerpo)
    assert r.status_code == 404
    error = r.json()["error"]
    assert error["code"] == "section_not_available"
    assert "field" not in error


async def test_version_vieja_da_409_version_conflict(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    primero = await _pedir(
        app_http, "PATCH", "/settings/gym", cabeceras(admin), {"value": GYM_OK, "version": 0}
    )
    assert primero.status_code == 200
    r = await _pedir(
        app_http,
        "PATCH",
        "/settings/gym",
        cabeceras(admin),
        {"value": {**GYM_OK, "name": "Otro"}, "version": 0},
    )
    assert r.status_code == 409
    assert r.json() == {"error": {"code": "version_conflict", "message": MENSAJE_CONFLICTO}}
    guardada = await fila(session, "gym")
    assert guardada is not None and guardada["version"] == 1 and guardada["value"] == GYM_OK


async def test_valor_invalido_da_422_con_field_y_no_toca_la_fila(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    await _pedir(app_http, "PATCH", "/settings/gym", cabeceras(admin), CUERPOS["/settings/gym"])
    antes = await filas_de_auditoria(session)
    r = await _pedir(
        app_http,
        "PATCH",
        "/settings/gym",
        cabeceras(admin),
        {"value": {**GYM_OK, "name": ""}, "version": 1},
    )
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "validation_error" and error["field"] == "value.name"
    assert set(error) == {"code", "message", "field"}
    guardada = await fila(session, "gym")
    assert guardada is not None and guardada["version"] == 1 and guardada["value"] == GYM_OK
    assert await filas_de_auditoria(session) == antes


@pytest.mark.parametrize(
    ("cuerpo", "campo"),
    [
        ({"value": GYM_OK, "version": -1}, "version"),
        ({"value": GYM_OK}, "version"),
        ({"value": GYM_OK, "version": 0, "extra": 1}, "extra"),
    ],
    ids=["version-negativa", "sin-version", "campo-extra"],
)
async def test_cuerpo_mal_formado_da_422(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    cuerpo: dict[str, Any],
    campo: str,
) -> None:
    r = await _pedir(app_http, "PATCH", "/settings/gym", cabeceras(admin), cuerpo)
    assert r.status_code == 422 and r.json()["error"]["field"] == campo


async def test_dos_patch_auditan_insert_y_update_con_el_actor_real(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    await _pedir(
        app_http, "PATCH", "/settings/gym", cabeceras(admin), {"value": GYM_OK, "version": 0}
    )
    r = await _pedir(
        app_http,
        "PATCH",
        "/settings/gym",
        cabeceras(admin),
        {"value": {**GYM_OK, "name": "APEX Sabaneta"}, "version": 1},
    )
    assert r.status_code == 200 and r.json()["version"] == 2
    auditoria = await filas_de_auditoria(session)
    assert [f["action"] for f in auditoria] == ["insert", "update"]
    assert all(f["table_name"] == TABLA for f in auditoria)
    assert all(f["user_id"] == admin.id for f in auditoria)
    assert all(f["subject_member_id"] is None for f in auditoria)
    assert auditoria[1]["after"]["value"]["name"] == "APEX Sabaneta"
