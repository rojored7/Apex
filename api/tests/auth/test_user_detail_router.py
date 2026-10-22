"""`GET`, `PATCH` y `DELETE /api/v1/users/{user_id}` por HTTP (S2-B5; US-049; US-018).

Solo admin (coach y socio 403, sin token 401), `Cache-Control: no-store` en las respuestas de
éxito (los 4xx no conservan las cabeceras de las dependencias). `GET` devuelve `UserOut` y
también las cuentas borradas con `status = "deleted"`; el técnico e inexistentes 404
`user_not_found`. `PATCH` 200 `UserOut`; 404 sobre una borrada; 409 `email_taken` (con
`field` y `existing_id`) y `last_admin`; 422 con un campo de más (`extra="forbid"`), un rol o un
correo inválidos, o un socio sin ficha. `DELETE` 204 sin cuerpo; una segunda baja da 404 (no
es idempotente: la cuenta ya no está viva); 409 `last_admin`. Un token emitido antes de un
cambio de rol o de una baja ya ve el estado nuevo: el cargador lee la base.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from tests.auth._ciclo import ruta
from tests.auth._cuentas import CAMPOS_USER_OUT, ME, USERS, avanzar, etiqueta, fila_usuario
from tests.conftest import T0, Cabeceras, CrearUsuario

# GET ---------------------------------------------------------------------------------------


async def test_get_devuelve_user_out_sin_cache(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    r = await app_http.get(ruta(coach.id), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    datos = r.json()
    assert set(datos) == CAMPOS_USER_OUT
    assert datos["id"] == str(coach.id)
    assert (datos["email"], datos["role"], datos["status"]) == (coach.email, "coach", "active")
    assert "password_hash" not in r.text


@pytest.mark.parametrize(
    ("estado", "esperado"),
    [
        ({"borrado": True}, "deleted"),
        ({"bloqueado": True}, "locked"),
        ({"activo": False}, "inactive"),
        ({"password": None}, "pending_activation"),
    ],
)
async def test_get_trae_cualquier_estado_incluida_la_baja(
    estado: dict[str, object],
    esperado: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("coach", **estado)  # type: ignore[arg-type]
    r = await app_http.get(ruta(otro.id), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == esperado


@pytest.mark.parametrize("objetivo", [SYSTEM_USER_ID, uuid4()], ids=["tecnico", "inexistente"])
async def test_get_del_tecnico_o_inexistente_da_404(
    objetivo: object, app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.get(ruta(objetivo), headers=cabeceras(admin))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "user_not_found"


async def test_un_id_mal_formado_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    for metodo in ("GET", "PATCH", "DELETE"):
        r = await app_http.request(metodo, ruta("no-es-uuid"), headers=cabeceras(admin), json={})
        assert r.status_code == 422, (metodo, r.text)
        assert r.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_socio_reciben_403_en_las_tres(
    rol: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    usuario = await usuario_real(rol)
    otro = await usuario_real("coach")
    for metodo, cuerpo in (("GET", None), ("PATCH", {"role": "admin"}), ("DELETE", None)):
        r = await app_http.request(metodo, ruta(otro.id), headers=cabeceras(usuario), json=cuerpo)
        assert r.status_code == 403, (metodo, r.text)
        assert r.json()["error"]["code"] == "forbidden"
    fila = await fila_usuario(session, otro.id)  # el otro sigue intacto
    assert (fila["role"], fila["deleted_at"]) == ("coach", None)


async def test_sin_token_da_401(app_http: AsyncClient, usuario_real: CrearUsuario) -> None:
    otro = await usuario_real("coach")
    for metodo in ("GET", "PATCH", "DELETE"):
        r = await app_http.request(metodo, ruta(otro.id), json={})
        assert r.status_code == 401, (metodo, r.text)


# PATCH -------------------------------------------------------------------------------------


async def test_patch_cambia_correo_y_rol_y_devuelve_user_out(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    tag = etiqueta()
    r = await app_http.patch(
        ruta(coach.id),
        headers=cabeceras(admin),
        json={"email": f" Cambio-{tag}@TEST.apex", "role": "admin"},
    )
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    datos = r.json()
    assert set(datos) == CAMPOS_USER_OUT
    assert (datos["email"], datos["role"]) == (f"cambio-{tag}@test.apex", "admin")
    fila = await fila_usuario(session, coach.id)
    assert (fila["email"], fila["role"]) == (f"cambio-{tag}@test.apex", "admin")


async def test_patch_vacio_no_cambia_nada(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    r = await app_http.patch(ruta(coach.id), headers=cabeceras(admin), json={})
    assert r.status_code == 200, r.text
    assert (r.json()["email"], r.json()["role"]) == (coach.email, "coach")


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"is_active": False},
        {"password_hash": "x"},
        {"member_id": str(uuid4())},
        {"role": "superadmin"},
        {"email": "no-es-correo"},
    ],
)
async def test_patch_con_un_campo_de_mas_o_invalido_da_422(
    cuerpo: dict[str, object],
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    r = await app_http.patch(ruta(coach.id), headers=cabeceras(admin), json=cuerpo)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"


async def test_patch_a_socio_sin_ficha_da_422_member_id_required(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    r = await app_http.patch(ruta(coach.id), headers=cabeceras(admin), json={"role": "member"})
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("member_id_required", "member_id")


async def test_patch_con_un_correo_tomado_da_409_con_el_id_existente(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    otro = await usuario_real("coach")
    r = await app_http.patch(ruta(coach.id), headers=cabeceras(admin), json={"email": otro.email})
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"], error["existing_id"]) == (
        "email_taken",
        "email",
        str(otro.id),
    )


async def test_el_ultimo_admin_no_se_degrada_a_si_mismo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.patch(ruta(admin.id), headers=cabeceras(admin), json={"role": "coach"})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "last_admin"


@pytest.mark.parametrize("objetivo", ["borrado", "tecnico", "inexistente"])
async def test_patch_sobre_una_borrada_o_el_tecnico_da_404(
    objetivo: str, app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    borrado = await usuario_real("coach", borrado=True)
    destino = {"borrado": borrado.id, "tecnico": SYSTEM_USER_ID, "inexistente": uuid4()}[objetivo]
    r = await app_http.patch(ruta(destino), headers=cabeceras(admin), json={"role": "admin"})
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "user_not_found"


async def test_un_admin_degradado_pierde_users_con_su_token_anterior(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    """El cambio de rol surte efecto inmediato: el token (con `role=admin` en el claim) sigue
    firmado y vigente, pero el `Principal` sale de la base."""
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    assert (await app_http.get(USERS, headers=cabeceras(otro))).status_code == 200
    r = await app_http.patch(ruta(otro.id), headers=cabeceras(admin), json={"role": "coach"})
    assert r.status_code == 200, r.text
    despues = await app_http.get(USERS, headers=cabeceras(otro))
    assert despues.status_code == 403, despues.text
    me = await app_http.get(ME, headers=cabeceras(otro))
    assert me.status_code == 200 and me.json()["role"] == "coach"


# DELETE ------------------------------------------------------------------------------------


async def test_delete_da_204_sin_cuerpo_y_deja_la_baja(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    avanzar(reloj, 1)
    r = await app_http.delete(ruta(coach.id), headers=cabeceras(admin))
    assert r.status_code == 204, r.text
    assert r.content == b""
    assert r.headers["cache-control"] == "no-store"
    fila = await fila_usuario(session, coach.id)
    assert fila["deleted_at"] == T0 + timedelta(seconds=1)
    detalle = await app_http.get(ruta(coach.id), headers=cabeceras(admin))
    assert detalle.status_code == 200 and detalle.json()["status"] == "deleted"


async def test_la_segunda_baja_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    assert (await app_http.delete(ruta(coach.id), headers=cabeceras(admin))).status_code == 204
    r = await app_http.delete(ruta(coach.id), headers=cabeceras(admin))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "user_not_found"


async def test_el_ultimo_admin_no_se_da_de_baja(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.delete(ruta(admin.id), headers=cabeceras(admin))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "last_admin"


@pytest.mark.parametrize("objetivo", [SYSTEM_USER_ID, uuid4()], ids=["tecnico", "inexistente"])
async def test_delete_del_tecnico_o_inexistente_da_404(
    objetivo: object, app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.delete(ruta(objetivo), headers=cabeceras(admin))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "user_not_found"


async def test_un_token_de_la_cuenta_borrada_da_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    assert (await app_http.get(ME, headers=cabeceras(coach))).status_code == 200
    assert (await app_http.delete(ruta(coach.id), headers=cabeceras(admin))).status_code == 204
    r = await app_http.get(ME, headers=cabeceras(coach))
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"
