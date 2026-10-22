"""Texto seguro en `POST /members` y `offset` acotado en `GET /members` (revisión del Sprint 2:
seguridad N-2 y Python H2).

Un NUL en el nombre daba 500 (asyncpg), un U+200B pasaba el CHECK `btrim(...) <> ''` y se
mostraba en la lista, y una tilde combinada no se normalizaba. Ahora los nombres (y el del
contacto de emergencia) usan `SafeText`: NFC, sin `Cc` ni `Cf` y con algo visible.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import unique_document
from tests.members._apoyo import MEMBERS, cuantos_socios, cuerpo, fila_socio


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("first_name", "a\x00b"),
        ("first_name", "\u200b"),
        ("last_name", "Pe\u202ena"),
        ("last_name", "\x07"),
    ],
    ids=["nul", "solo-zwsp", "rlo", "bel"],
)
async def test_nombre_con_control_o_formato_da_422_y_no_crea_nada(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    campo: str,
    valor: str,
) -> None:
    admin = await usuario_real("admin")
    antes = await cuantos_socios(session)
    r = await app_http.post(
        MEMBERS, headers=cabeceras(admin), json=cuerpo(document=unique_document(), **{campo: valor})
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == campo
    assert await cuantos_socios(session) == antes


async def test_contacto_de_emergencia_con_nul_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    contacto: dict[str, Any] = {"name": "Ana\x00", "phone": "3001234567"}
    r = await app_http.post(
        MEMBERS,
        headers=cabeceras(admin),
        json=cuerpo(document=unique_document(), emergency_contact=contacto),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "emergency_contact.name"


async def test_tilde_combinada_se_guarda_en_nfc(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(
        MEMBERS,
        headers=cabeceras(admin),
        json=cuerpo(document=unique_document(), first_name="Jose\u0301", last_name="Pen\u0303a"),
    )
    assert r.status_code == 201, r.text
    assert (r.json()["first_name"], r.json()["last_name"]) == ("José", "Peña")
    fila = await fila_socio(session, r.json()["id"])
    assert (fila["first_name"], fila["last_name"]) == ("José", "Peña")


async def test_offset_fuera_de_rango_en_members_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(
        MEMBERS, headers=cabeceras(coach), params={"offset": "99999999999999999999"}
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "offset"
