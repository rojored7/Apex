"""`GET` y `PATCH /api/v1/members/{member_id}/channels` por HTTP (S5-B5, US-123; S5-D31, S5-D81,
N-20, N-33). # Rojo B5

- admin y coach: 200 con `ChannelsOut` (`member_id`, `channels`, `effective`, `has_consent`) y
  `Cache-Control: no-store`; sin filas y con autorización, `effective == ["whatsapp_link"]`;
- `member` 403 `forbidden` y sin token 401 en las dos rutas; id inexistente 404 `member_not_found`;
- un socio dado de baja: `GET` 200 y `PATCH` 409 `member_deleted` (N-20);
- 422: canal desconocido, `active` que no es booleano, campo extra, cuerpo sin `items`;
- el `PATCH` consume `notifications-write` (30 por minuto): el 31 en un minuto da 429
  `rate_limited` con `Retry-After`; el `GET` consume `staff-read` (120 por minuto);
- ninguna respuesta lleva teléfono, correo ni blobs.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories.members import KNOWN, KNOWN_NORMALIZED, make_member, unique_document
from tests.members._apoyo import MEMBERS, ruta_socio

WA = "whatsapp_link"
CORREO = "email"
CAMPOS_CANALES = {"member_id", "channels", "effective", "has_consent"}
LIMITE_DE_ESCRITURAS = 30  # notifications-write (S5-D81)
LIMITE_DE_LECTURAS = 120  # staff-read


def ruta_canales(member_id: object) -> str:
    return f"{ruta_socio(member_id)}/channels"


async def socio_consentido(session: AsyncSession, **cambios: Any) -> Any:
    valores: dict[str, Any] = {"data_consent_at": T0 - timedelta(days=1)}
    valores.update(cambios)
    socio = await make_member(session, **valores)
    return socio.id


# GET ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_leen_los_canales_del_socio(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    rol: str,
) -> None:
    socio_id = await socio_consentido(session)
    quien = await usuario_real(rol)
    r = await app_http.get(ruta_canales(socio_id), headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_CANALES
    assert datos["member_id"] == str(socio_id)
    assert datos["channels"] == []
    assert datos["effective"] == [WA]
    assert datos["has_consent"] is True
    assert r.headers["cache-control"] == "no-store"
    for valor in (*KNOWN_NORMALIZED, *KNOWN.values(), "apx1."):
        assert str(valor) not in r.text, valor


async def test_un_socio_sin_autorizacion_no_tiene_canales_efectivos(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
) -> None:
    socio = await make_member(session)
    quien = await usuario_real("coach")
    r = await app_http.get(ruta_canales(socio.id), headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    assert (r.json()["effective"], r.json()["has_consent"]) == ([], False)


async def test_el_get_responde_200_sobre_un_dado_de_baja(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
) -> None:
    socio_id = await socio_consentido(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    admin = await usuario_real("admin")
    r = await app_http.get(ruta_canales(socio_id), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.json()["member_id"] == str(socio_id)


async def test_el_get_de_un_id_inexistente_da_404_member_not_found(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    bus_listo: Keyring,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(ruta_canales(uuid4()), headers=cabeceras(coach))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"


# PATCH -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_fijan_los_canales_y_reciben_el_estado_nuevo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    rol: str,
) -> None:
    socio_id = await socio_consentido(session)
    quien = await usuario_real(rol)
    r = await app_http.patch(
        ruta_canales(socio_id),
        json={"items": [{"channel": CORREO, "active": True}]},
        headers=cabeceras(quien),
    )
    assert r.status_code == 200, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_CANALES
    assert datos["channels"] == [{"channel": CORREO, "active": True}]
    assert sorted(datos["effective"]) == sorted([WA, CORREO])
    lectura = await app_http.get(ruta_canales(socio_id), headers=cabeceras(quien))
    assert lectura.json() == datos


async def test_el_patch_de_un_dado_de_baja_da_409_member_deleted(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
) -> None:
    socio_id = await socio_consentido(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    admin = await usuario_real("admin")
    r = await app_http.patch(
        ruta_canales(socio_id),
        json={"items": [{"channel": CORREO, "active": True}]},
        headers=cabeceras(admin),
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "member_deleted"


async def test_el_patch_de_un_id_inexistente_da_404_member_not_found(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    bus_listo: Keyring,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.patch(
        ruta_canales(uuid4()),
        json={"items": [{"channel": WA, "active": False}]},
        headers=cabeceras(coach),
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"


# Roles y sesión ----------------------------------------------------------------------------------


@pytest.mark.parametrize("metodo", ["get", "patch"])
async def test_el_rol_member_recibe_403_en_las_dos_rutas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    metodo: str,
) -> None:
    socio_id = await socio_consentido(session)
    miembro = await usuario_real("member")
    cuerpo = {"items": [{"channel": CORREO, "active": True}]} if metodo == "patch" else None
    r = await app_http.request(
        metodo.upper(), ruta_canales(socio_id), json=cuerpo, headers=cabeceras(miembro)
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("metodo", ["get", "patch"])
async def test_sin_token_da_401_en_las_dos_rutas(
    app_http: AsyncClient, bus_listo: Keyring, reloj: FrozenClock, metodo: str
) -> None:
    cuerpo = {"items": []} if metodo == "patch" else None
    r = await app_http.request(metodo.upper(), ruta_canales(uuid4()), json=cuerpo)
    assert r.status_code == 401, r.text


# 422 ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"items": [{"channel": "sms", "active": True}]},
        {"items": [{"channel": "EMAIL", "active": True}]},
        {"items": [{"channel": CORREO, "active": "si"}]},
        {"items": [{"channel": CORREO, "active": None}]},
        {"items": [{"channel": CORREO}]},
        {"items": [{"channel": CORREO, "active": True, "extra": 1}]},
        {"items": [], "otro": True},
        {},
    ],
    ids=[
        "canal-desconocido",
        "canal-en-mayusculas",
        "active-texto",
        "active-null",
        "sin-active",
        "campo-extra-en-item",
        "campo-extra-en-cuerpo",
        "sin-items",
    ],
)
async def test_un_cuerpo_invalido_da_422_y_no_escribe(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    cuerpo: dict[str, Any],
) -> None:
    socio_id = await socio_consentido(session)
    coach = await usuario_real("coach")
    r = await app_http.patch(ruta_canales(socio_id), json=cuerpo, headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    lectura = await app_http.get(ruta_canales(socio_id), headers=cabeceras(coach))
    assert lectura.json()["channels"] == []


# Cubeta notifications-write -----------------------------------------------------------------------


async def test_el_patch_31_en_un_minuto_da_429_y_las_lecturas_no_cuentan_en_su_cubeta(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    socio_id = await socio_consentido(session, document=unique_document())
    ruta = ruta_canales(socio_id)  # el 429 revierte la sesión y expira el objeto
    for numero in range(LIMITE_DE_ESCRITURAS):
        activo = numero % 2 == 0
        r = await app_http.patch(
            ruta,
            json={"items": [{"channel": CORREO, "active": activo}]},
            headers=cabeceras(coach),
        )
        assert r.status_code == 200, (numero, r.text)
    for _ in range(3):  # las lecturas no cuentan
        assert (await app_http.get(ruta, headers=cabeceras(coach))).status_code == 200
    r = await app_http.patch(
        ruta, json={"items": [{"channel": CORREO, "active": True}]}, headers=cabeceras(coach)
    )
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1


async def test_el_patch_no_comparte_cubeta_con_la_edicion_del_socio(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
) -> None:
    """`notifications-write` es propia: agotar `members-write` (60) no la toca."""
    coach = await usuario_real("coach")
    socio_id = await socio_consentido(session)
    ruta = ruta_socio(socio_id)
    for numero in range(60):
        r = await app_http.patch(ruta, json={"first_name": f"N{numero}"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    assert (
        await app_http.patch(ruta, json={"first_name": "x"}, headers=cabeceras(coach))
    ).status_code == 429
    r = await app_http.patch(
        f"{MEMBERS}/{socio_id}/channels",
        json={"items": [{"channel": WA, "active": False}]},
        headers=cabeceras(coach),
    )
    assert r.status_code == 200, r.text


async def test_el_get_121_en_un_minuto_da_429_por_staff_read(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
) -> None:
    """Revisión de seguridad de B5 (LOW): la lectura consume `staff-read` como las demás."""
    coach = await usuario_real("coach")
    ruta = ruta_canales(await socio_consentido(session))
    for numero in range(LIMITE_DE_LECTURAS):
        r = await app_http.get(ruta, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(ruta, headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"


# Consentimiento y duplicados (revisión de B5: S5-D211, LOW de base de datos) ----------------------


async def test_el_patch_de_correo_activo_sin_consentimiento_da_422_consent_required(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
) -> None:
    socio_id = await socio_consentido(session, data_consent_at=None)
    admin = await usuario_real("admin")
    r = await app_http.patch(
        ruta_canales(socio_id),
        json={"items": [{"channel": CORREO, "active": True}]},
        headers=cabeceras(admin),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "consent_required"
    lectura = await app_http.get(ruta_canales(socio_id), headers=cabeceras(admin))
    assert lectura.json()["channels"] == []


async def test_el_patch_puede_desactivar_canales_sin_consentimiento(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
) -> None:
    socio_id = await socio_consentido(session, data_consent_at=None)
    admin = await usuario_real("admin")
    r = await app_http.patch(
        ruta_canales(socio_id),
        json={"items": [{"channel": WA, "active": False}, {"channel": CORREO, "active": False}]},
        headers=cabeceras(admin),
    )
    assert r.status_code == 200, r.text
    assert r.json()["effective"] == []


async def test_canales_repetidos_en_items_dan_422(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
) -> None:
    socio_id = await socio_consentido(session)
    admin = await usuario_real("admin")
    r = await app_http.patch(
        ruta_canales(socio_id),
        json={"items": [{"channel": CORREO, "active": True}, {"channel": CORREO, "active": False}]},
        headers=cabeceras(admin),
    )
    assert r.status_code == 422, r.text
