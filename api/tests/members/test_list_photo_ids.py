"""`photo_attachment_id` en la ficha y en la lista de socios (S6-C2, US-148; S6-D20, G-04, E8).

- `GET /members/{id}`: la foto vigente (la más reciente de tipo `photo`; `consent` y `other` no
  cuentan) o `null` sin foto;
- `GET /members`: cada fila lleva su `photo_attachment_id` y la página de 50 socios añade UNA sola
  consulta a `attachments.attachments` (por lote, sin N+1); una página vacía no consulta;
- `MemberDetailOut` y `MemberRowOut` exponen el campo (contrato de `CAMPOS_DETALLE`/`CAMPOS_FILA`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto.keyring import Keyring
from tests.attachments._apoyo import insertar
from tests.conftest import Cabeceras, ContadorDeConsultas, CrearUsuario
from tests.factories.members import make_member, make_members
from tests.members._apoyo import CAMPOS_DETALLE, CAMPOS_FILA, MEMBERS, ruta_socio

TABLA = "attachments.attachments"


async def test_la_ficha_trae_la_foto_vigente_y_null_sin_foto(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    con_foto, sin_foto = await make_member(session), await make_members(session, 1)
    admin = await usuario_real("admin")
    ahora = datetime.now(UTC)
    await insertar(session, owner=con_foto.id, created_at=ahora - timedelta(days=2), por=admin.id)
    vigente = await insertar(
        session, owner=con_foto.id, created_at=ahora - timedelta(days=1), por=admin.id
    )
    # Un `consent` más nuevo no es foto: no desplaza a la vigente.
    await insertar(session, owner=con_foto.id, kind="consent", created_at=ahora, por=admin.id)

    r = await app_http.get(ruta_socio(con_foto.id), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert set(r.json()) == CAMPOS_DETALLE
    assert r.json()["photo_attachment_id"] == str(vigente)

    nulo = await app_http.get(ruta_socio(sin_foto[0].id), headers=cabeceras(admin))
    assert nulo.status_code == 200, nulo.text
    assert nulo.json()["photo_attachment_id"] is None


async def test_la_lista_trae_el_photo_attachment_id_de_cada_fila_o_null(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socios = await make_members(session, 4)
    admin = await usuario_real("admin")
    fotos = {
        socios[0].id: await insertar(session, owner=socios[0].id, por=admin.id),
        socios[2].id: await insertar(session, owner=socios[2].id, por=admin.id),
    }
    r = await app_http.get(MEMBERS, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    filas = {f["id"]: f for f in r.json()["items"]}
    assert len(filas) == 4
    for fila in filas.values():
        assert set(fila) == CAMPOS_FILA
    for socio in socios:
        esperado = fotos.get(socio.id)
        assert filas[str(socio.id)]["photo_attachment_id"] == (
            None if esperado is None else str(esperado)
        )


async def test_la_lista_de_50_socios_hace_una_sola_consulta_de_fotos(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    socios = await make_members(session, 50)
    admin = await usuario_real("admin")
    for socio in socios[::2]:
        await insertar(session, owner=socio.id, por=admin.id)

    with contador_de_consultas.midiendo():
        r = await app_http.get(f"{MEMBERS}?limit=50", headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert len(r.json()["items"]) == 50
    assert contador_de_consultas.de(TABLA) == 1, contador_de_consultas.sentencias
    con_foto = [f for f in r.json()["items"] if f["photo_attachment_id"] is not None]
    assert len(con_foto) == 25


async def test_una_pagina_vacia_no_consulta_adjuntos_y_la_ficha_consulta_una_vez(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    admin = await usuario_real("admin")
    socio = await make_member(session)
    with contador_de_consultas.midiendo():
        vacia = await app_http.get(f"{MEMBERS}?q=zzzz-sin-resultados", headers=cabeceras(admin))
    assert vacia.status_code == 200 and vacia.json()["items"] == [], vacia.text
    assert contador_de_consultas.de(TABLA) == 0

    with contador_de_consultas.midiendo():
        ficha = await app_http.get(ruta_socio(socio.id), headers=cabeceras(admin))
    assert ficha.status_code == 200, ficha.text
    assert contador_de_consultas.de(TABLA) == 1, contador_de_consultas.sentencias
