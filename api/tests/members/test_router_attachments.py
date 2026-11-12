"""Rutas HTTP de adjuntos del socio (S6-C2, US-148; S6-D57, S6-D59, D27, M2, M-6).

- `POST /members/{member_id}/attachments?kind=`: cuerpo crudo por `httpx` (`content=bytes` y
  `content=<generador>`), 201 `AttachmentOut` sin `filename_random`, `key_id` ni
  `storage_provider`, `Cache-Control: no-store`, cubeta `attachments-upload` (10 por minuto: la
  11.ª da 429 con `Retry-After`), 401 sin token;
- `GET /members/{member_id}/attachments`: `Page[AttachmentOut]` con `limit`/`offset` y sin `q`
  (exclusión anotada en `test_list_routes_use_page_params`), admin y coach listan, `member` 403,
  sin token 401, socio inexistente 404 y `member_id` inválido 422; no mezcla socios.
El 408 y el 413 en el OpenAPI los comprueba `tests/architecture/test_error_responses_in_openapi.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto.keyring import Keyring
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo import insertar
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories import files
from tests.factories.members import make_member, unique_document
from tests.members._apoyo import MEMBERS
from tests.members.test_attach_photo import ruta_adjuntos

CAMPOS_ADJUNTO = frozenset(
    {
        "id",
        "owner_table",
        "owner_id",
        "kind",
        "mime",
        "size_bytes",
        "sensitive",
        "uploaded_by",
        "created_at",
    }
)
SECRETOS = ("filename_random", "key_id", "storage_provider")
LIMITE_DE_SUBIDAS = 10


async def test_el_cuerpo_crudo_acepta_bytes_y_generador_y_responde_el_adjunto_sin_secretos(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    admin = await usuario_real("admin")
    url = ruta_adjuntos(socio.id)
    con_bytes = await app_http.post(url, content=files.jpeg(2048), headers=cabeceras(admin))
    con_generador = await app_http.post(
        url, content=files.en_trozos(files.png(4096), 512), headers=cabeceras(admin)
    )
    for r in (con_bytes, con_generador):
        assert r.status_code == 201, r.text
        assert set(r.json()) == CAMPOS_ADJUNTO
        for secreto in SECRETOS:
            assert secreto not in r.text, secreto
        assert r.headers["cache-control"] == "no-store"
    assert con_bytes.json()["mime"] == "image/jpeg"
    assert con_generador.json()["mime"] == "image/png"
    assert con_bytes.json()["id"] != con_generador.json()["id"]


async def test_la_subida_11_en_un_minuto_da_429_con_retry_after(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    """Cubeta `attachments-upload` (S6-D57): 10 por usuario y minuto; no se comparte."""
    socio = await make_member(session)
    admin = await usuario_real("admin")
    otro = await usuario_real("coach")
    url = ruta_adjuntos(socio.id)
    for _ in range(LIMITE_DE_SUBIDAS):
        ok = await app_http.post(url, content=files.jpeg(512), headers=cabeceras(admin))
        assert ok.status_code == 201, ok.text
    cuerpo = files.Contado(files.jpeg(300_000))
    excedida = await app_http.post(url, content=cuerpo, headers=cabeceras(admin))
    assert excedida.status_code == 429, excedida.text
    assert excedida.json()["error"]["code"] == "rate_limited"
    assert int(excedida.headers["retry-after"]) >= 1
    assert cuerpo.trozos == 0  # revisión de seguridad de C2: la cubeta se decide antes de leer
    ajeno = await app_http.post(url, content=files.jpeg(512), headers=cabeceras(otro))
    assert ajeno.status_code == 201, ajeno.text


async def test_la_subida_sin_token_da_401(
    app_http: AsyncClient, session: AsyncSession, bus_listo: Keyring, almacen: LocalDiskStorage
) -> None:
    socio = await make_member(session)
    cuerpo = files.Contado(files.jpeg(2048))
    r = await app_http.post(ruta_adjuntos(socio.id), content=cuerpo)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"
    assert cuerpo.trozos == 0


# GET ------------------------------------------------------------------------------------------


async def test_el_listado_pagina_con_limit_y_offset_del_mas_nuevo_al_mas_viejo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    admin = await usuario_real("admin")
    ahora = datetime.now(UTC)
    ids = [
        await insertar(session, owner=socio.id, created_at=ahora - timedelta(hours=n), por=admin.id)
        for n in range(5)  # n = 0 es el más nuevo
    ]
    url = ruta_adjuntos(socio.id, None)

    primera = await app_http.get(f"{url}?limit=2&offset=0", headers=cabeceras(admin))
    segunda = await app_http.get(f"{url}?limit=2&offset=2", headers=cabeceras(admin))
    assert primera.status_code == segunda.status_code == 200, (primera.text, segunda.text)
    assert (primera.json()["total"], primera.json()["limit"], primera.json()["offset"]) == (5, 2, 0)
    assert segunda.json()["offset"] == 2
    assert [i["id"] for i in primera.json()["items"]] == [str(i) for i in ids[:2]]
    assert [i["id"] for i in segunda.json()["items"]] == [str(i) for i in ids[2:4]]
    for item in primera.json()["items"]:
        assert set(item) == CAMPOS_ADJUNTO
    for secreto in SECRETOS:
        assert secreto not in primera.text
    assert primera.headers["cache-control"] == "no-store"


async def test_el_listado_no_acepta_q_y_limit_tiene_maximo_200(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    admin = await usuario_real("admin")
    for _ in range(3):
        await insertar(session, owner=socio.id, por=admin.id)
    url = ruta_adjuntos(socio.id, None)
    con_q = await app_http.get(f"{url}?q=zzz-no-existe", headers=cabeceras(admin))
    assert con_q.status_code == 200, con_q.text
    assert con_q.json()["total"] == 3  # `q` no existe: no filtra
    demasiado = await app_http.get(f"{url}?limit=201", headers=cabeceras(admin))
    assert demasiado.status_code == 422, demasiado.text
    assert demasiado.json()["error"]["field"] == "limit"


async def test_el_listado_solo_trae_los_adjuntos_del_socio(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    uno, otro = await make_member(session), await make_member(session, document=unique_document())
    admin = await usuario_real("admin")
    suyo = await insertar(session, owner=uno.id, por=admin.id)
    await insertar(session, owner=otro.id, por=admin.id)
    r = await app_http.get(ruta_adjuntos(uno.id, None), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert [i["id"] for i in r.json()["items"]] == [str(suyo)]


async def test_admin_y_coach_listan_incluidos_los_sensibles_y_member_recibe_403(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    miembro = await usuario_real("member")
    await insertar(session, owner=socio.id, kind="photo", por=admin.id)
    await insertar(session, owner=socio.id, kind="consent", por=admin.id)
    url = ruta_adjuntos(socio.id, None)
    for quien in (admin, coach):
        r = await app_http.get(url, headers=cabeceras(quien))
        assert r.status_code == 200, r.text
        assert sorted(i["kind"] for i in r.json()["items"]) == ["consent", "photo"]
    prohibido = await app_http.get(url, headers=cabeceras(miembro))
    assert prohibido.status_code == 403, prohibido.text
    assert prohibido.json()["error"]["code"] == "forbidden"
    sin_token = await app_http.get(url)
    assert sin_token.status_code == 401, sin_token.text


async def test_el_listado_de_un_socio_inexistente_da_404_y_un_id_invalido_422(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    admin = await usuario_real("admin")
    inexistente = await app_http.get(ruta_adjuntos(uuid4(), None), headers=cabeceras(admin))
    assert inexistente.status_code == 404, inexistente.text
    assert inexistente.json()["error"]["code"] == "member_not_found"
    invalido = await app_http.get(f"{MEMBERS}/no-es-uuid/attachments", headers=cabeceras(admin))
    assert invalido.status_code == 422, invalido.text
    assert invalido.json()["error"]["field"] == "member_id"
