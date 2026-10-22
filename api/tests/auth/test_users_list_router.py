"""`GET /api/v1/users` por HTTP (S2-B3; US-045; regla de datos 6, D2, M-8, US-018).

Solo admin (coach y socio 403), `Cache-Control: no-store`, `Page[UserRow]` con `limit` de 1 a
200 (25 por defecto), `offset >= 0`, `q` hasta 100 caracteres y filtros `role` y `status`
validados (422 con `field`). La respuesta no trae `password_hash` ni tokens y el `q` buscado
no aparece en los logs (la línea de acceso lleva la plantilla de la ruta, sin query).
"""

from __future__ import annotations

import logging

import pytest
from httpx import AsyncClient

from app.core.context import SYSTEM_USER_ID
from tests.auth._cuentas import CAMPOS_USER_ROW, USERS, etiqueta
from tests.conftest import Cabeceras, CrearUsuario


async def test_el_admin_recibe_la_pagina_con_el_contrato(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.get(USERS, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.json()
    assert set(cuerpo) == {"items", "total", "limit", "offset"}
    assert (cuerpo["limit"], cuerpo["offset"]) == (25, 0)
    assert cuerpo["total"] >= 1
    ids = {fila["id"] for fila in cuerpo["items"]}
    assert str(admin.id) in ids
    assert str(SYSTEM_USER_ID) not in ids
    for fila in cuerpo["items"]:
        assert set(fila) == CAMPOS_USER_ROW
    assert "password_hash" not in r.text and "$argon2" not in r.text
    assert admin.token not in r.text


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_socio_reciben_403(
    rol: str, app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    usuario = await usuario_real(rol)
    r = await app_http.get(USERS, headers=cabeceras(usuario))
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


async def test_sin_token_da_401(app_http: AsyncClient) -> None:
    r = await app_http.get(USERS)
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    ("query", "campo"),
    [
        ("limit=500", "limit"),
        ("limit=201", "limit"),
        ("limit=0", "limit"),
        ("offset=-1", "offset"),
        ("q=" + "x" * 101, "q"),
        ("role=root", "role"),
        ("status=dormido", "status"),
    ],
    ids=["limit-500", "limit-201", "limit-0", "offset-negativo", "q-largo", "rol", "estado"],
)
async def test_parametros_invalidos_dan_422_con_el_campo(
    query: str,
    campo: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.get(f"{USERS}?{query}", headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["field"] == campo


@pytest.mark.parametrize("query", ["q=a%00b", "q=%00", "q=a%1Fb"], ids=["nul", "solo-nul", "us"])
async def test_un_q_con_caracteres_de_control_da_422_con_field_q_y_no_500(
    query: str, app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    """Deuda de S2-B8 (MEDIUM-1, `DECISIONES.md`): el NUL llegaba a PostgreSQL como parámetro del
    `ILIKE` sobre el correo y daba 500. `core/pagination.SearchQuery` rechaza los caracteres de
    control en el contrato común de todas las listas (S2-B9)."""
    admin = await usuario_real("admin")
    r = await app_http.get(f"{USERS}?{query}", headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["field"] == "q"


async def test_limit_200_es_valido(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.get(f"{USERS}?limit=200", headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.json()["limit"] == 200


async def test_q_rol_y_estado_filtran(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    tag = etiqueta()
    admin = await usuario_real("admin")
    coach = await usuario_real("coach", email=f"coach-{tag}@test.apex")
    pendiente = await usuario_real("coach", email=f"nuevo-{tag}@test.apex", password=None)
    await usuario_real("admin", email=f"otro-{tag}@test.apex")
    r = await app_http.get(USERS, params={"q": tag, "role": "coach"}, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert [f["id"] for f in r.json()["items"]] == [str(coach.id), str(pendiente.id)]
    r = await app_http.get(
        USERS,
        params={"q": tag, "status": "pending_activation"},
        headers=cabeceras(admin),
    )
    assert [f["id"] for f in r.json()["items"]] == [str(pendiente.id)]
    assert r.json()["items"][0]["status"] == "pending_activation"


async def test_q_con_guion_bajo_va_escapado(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    tag = etiqueta()
    admin = await usuario_real("admin")
    exacto = await usuario_real("coach", email=f"x_y-{tag}@test.apex")
    await usuario_real("coach", email=f"xay-{tag}@test.apex")
    r = await app_http.get(USERS, params={"q": f"x_y-{tag}"}, headers=cabeceras(admin))
    assert [f["id"] for f in r.json()["items"]] == [str(exacto.id)]


async def test_el_termino_buscado_no_aparece_en_los_logs(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """M-8 y US-018: el `q` puede ser un correo; el log de acceso lleva solo la plantilla."""
    admin = await usuario_real("admin")
    buscado = f"buscado-{etiqueta()}"
    caplog.set_level(logging.DEBUG)
    r = await app_http.get(USERS, params={"q": buscado}, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    texto = caplog.text + " ".join(str(rec.__dict__) for rec in caplog.records)
    assert buscado not in texto
