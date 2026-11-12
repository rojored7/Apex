"""`GET /api/v1/attachments/{attachment_id}` (S6-C4, US-150; S6-D24, S6-D37, S6-D45, S6-D57,
S6-D59, M-3, M-5, M-6, N-20, ADR-007). Rojo C4.

Todo va por ASGI/`httpx` directamente contra el api, sin Nginx. La sesión del api es la de la
prueba (savepoint): los adjuntos se suben con `service.store` sobre esa misma sesión.

- roles: admin descarga `consent`, `other` y `photo`; coach solo `photo` (403 `forbidden` en
  sensibles, ANTES de descifrar y sin fila); socio 403; sin token 401; id inexistente 404
  `attachment_not_found`; id mal formado 422;
- cabeceras: `no-store`, `nosniff`, CSP `default-src 'none'; sandbox`, `Content-Type` del `mime`
  guardado y `Content-Disposition: attachment; filename="adjunto-<8 hex>.<ext>"` (nunca
  `filename_random` ni el id completo). El Rojo acepta la cabecera con o sin comillas porque
  `file_download` hoy la arma sin ellas (ver `tests/core/test_http.py`);
- auditoría (M-3): el sensible deja UNA fila `download` y un `decrypt`, confirmadas (commit) antes
  del primer mensaje de la respuesta; con el custodio sellado, 503 `crypto_unavailable` con
  `Retry-After: 30` y sin fila; la foto no deja fila ni `crypto_ops` y se sirve sellado;
- cubetas (M-5): sensibles `attachments-download` (30/min, 31.ª 429) y `-hour`, foto
  `attachments-photo`; son contadores distintos y se consumen ANTES de descifrar;
- N-20: un socio de baja sigue descargable; un PDF con JavaScript se sirve igual, como adjunto.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.ratelimit import USER_LIMITS
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo import fila, filas_de_auditoria, ops_de, pedir_asgi, subir
from tests.conftest import T0, Cabeceras, CrearUsuario, UsuarioPrueba
from tests.factories import files
from tests.factories.members import make_member

RUTA = "/api/v1/attachments"
PDF = files.pdf(6000)
JPG = files.jpeg(70_000)
PNG = files.png(3000)
CSP = "default-src 'none'; sandbox"
# Un PDF con JavaScript embebido pasa los bytes mágicos (nota de C1): se sirve como adjunto.
PDF_CON_JS = (
    b"%PDF-1.7\n1 0 obj\n<< /Type /Action /S /JavaScript /JS (app.alert('apex')) >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
)


async def _bajar(
    app_http: AsyncClient, cabeceras: Cabeceras, quien: UsuarioPrueba, adjunto_id: UUID | str
) -> Response:
    return await app_http.get(f"{RUTA}/{adjunto_id}", headers=cabeceras(quien))


async def _bajadas(session: AsyncSession) -> int:
    return len(await filas_de_auditoria(session, "download"))


async def _descifrados(session: AsyncSession, adjunto_id: UUID) -> int:
    return len(await ops_de(session, "decrypt", adjunto_id))


def _tipo(r: Response) -> str:
    return r.headers["content-type"].split(";")[0].strip()


# Éxito: contenido y tipo -------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["consent", "other"])
async def test_el_admin_descarga_un_sensible_descifrado_con_su_mime_y_deja_una_fila(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
    kind: str,
) -> None:
    dueno = uuid4()
    adjunto = await subir(session, por, kind, PDF, dueno=dueno)
    adjunto_id = adjunto.id
    admin = await usuario_real("admin")

    r = await _bajar(app_http, cabeceras, admin, adjunto_id)

    assert r.status_code == 200, r.text
    assert _tipo(r) == "application/pdf"
    assert r.content == PDF
    (bajada,) = await filas_de_auditoria(session, "download")
    assert bajada["record_id"] == adjunto_id
    assert bajada["user_id"] == admin.id
    assert bajada["subject_member_id"] == dueno
    assert bajada["after"] == {"kind": kind, "sensitive": True, "owner_id": str(dueno)}
    assert await _descifrados(session, adjunto_id) == 1


@pytest.mark.parametrize(
    ("datos", "mime"), [(JPG, "image/jpeg"), (PNG, "image/png")], ids=["jpeg", "png"]
)
async def test_el_admin_descarga_la_foto_con_su_mime(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
    datos: bytes,
    mime: str,
) -> None:
    adjunto_id = (await subir(session, por, "photo", datos)).id
    admin = await usuario_real("admin")

    r = await _bajar(app_http, cabeceras, admin, adjunto_id)

    assert r.status_code == 200, r.text
    assert _tipo(r) == mime
    assert r.content == datos


# Roles -------------------------------------------------------------------------------------------


async def test_el_coach_descarga_la_foto(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    adjunto_id = (await subir(session, por, "photo", JPG)).id
    coach = await usuario_real("coach")

    r = await _bajar(app_http, cabeceras, coach, adjunto_id)

    assert r.status_code == 200, r.text
    assert r.content == JPG


@pytest.mark.parametrize("kind", ["consent", "other"])
async def test_el_coach_recibe_403_en_un_sensible_sin_descifrar_ni_dejar_fila(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
    kind: str,
) -> None:
    """M-6: el 403 sale antes de descifrar: ni `crypto_ops` ni fila `download`."""
    adjunto_id = (await subir(session, por, kind, PDF)).id
    coach = await usuario_real("coach")

    r = await _bajar(app_http, cabeceras, coach, adjunto_id)

    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert PDF[:20] not in r.content
    assert await _bajadas(session) == 0
    assert await _descifrados(session, adjunto_id) == 0


@pytest.mark.parametrize(
    ("kind", "datos"),
    [("photo", JPG), ("consent", PDF), ("other", PDF)],
    ids=["photo", "consent", "other"],
)
async def test_un_socio_recibe_403_en_cualquier_adjunto(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
    kind: str,
    datos: bytes,
) -> None:
    adjunto_id = (await subir(session, por, kind, datos)).id
    socio = await usuario_real("member")

    r = await _bajar(app_http, cabeceras, socio, adjunto_id)

    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert await _bajadas(session) == 0


async def test_sin_token_es_401(
    app_http: AsyncClient,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    bus_listo: Keyring,
    por: UUID,
) -> None:
    adjunto_id = (await subir(session, por, "consent", PDF)).id

    r = await app_http.get(f"{RUTA}/{adjunto_id}")

    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"
    assert await _bajadas(session) == 0


# No encontrado -----------------------------------------------------------------------------------


async def test_un_id_inexistente_es_404_attachment_not_found(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    almacen: LocalDiskStorage,
) -> None:
    admin = await usuario_real("admin")

    r = await _bajar(app_http, cabeceras, admin, uuid4())

    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "attachment_not_found"


async def test_un_id_mal_formado_es_422(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    almacen: LocalDiskStorage,
) -> None:
    admin = await usuario_real("admin")

    r = await _bajar(app_http, cabeceras, admin, "no-es-un-uuid")

    assert r.status_code == 422, r.text


# Cabeceras ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "datos", "mime", "extension"),
    [
        ("consent", PDF, "application/pdf", "pdf"),
        ("other", PDF, "application/pdf", "pdf"),
        ("photo", JPG, "image/jpeg", "jpe?g"),
        ("photo", PNG, "image/png", "png"),
    ],
    ids=["consent", "other", "photo-jpeg", "photo-png"],
)
async def test_las_cabeceras_de_descarga_no_filtran_el_nombre_del_objeto(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
    kind: str,
    datos: bytes,
    mime: str,
    extension: str,
) -> None:
    adjunto = await subir(session, por, kind, datos)
    adjunto_id = adjunto.id
    nombre_objeto = (await fila(session, adjunto_id))["filename_random"]
    admin = await usuario_real("admin")

    r = await _bajar(app_http, cabeceras, admin, adjunto_id)

    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"] == CSP
    assert _tipo(r) == mime
    disposicion = r.headers["content-disposition"]
    assert re.fullmatch(
        rf'attachment; filename="?adjunto-[0-9a-f]{{8}}\.{extension}"?', disposicion
    ), disposicion
    for valor in r.headers.values():
        assert nombre_objeto not in valor
        assert str(adjunto_id) not in valor and adjunto_id.hex not in valor
    assert "set-cookie" not in r.headers


# Auditoría y orden (M-3) -------------------------------------------------------------------------


@pytest.fixture
def secuencia(engine: AsyncEngine, session: AsyncSession) -> Iterator[list[str]]:
    """Anota 'audit' (INSERT en `audit.audit_log`) y 'commit' (`session.commit()`), en orden."""
    eventos: list[str] = []

    def anotar(_c: object, _cur: object, sql: str, *_a: object) -> None:
        if "INSERT INTO audit.audit_log" in sql:
            eventos.append("audit")

    original = session.commit

    async def commit_anotado() -> None:
        eventos.append("commit")
        await original()

    event.listen(engine.sync_engine, "before_cursor_execute", anotar)
    session.commit = commit_anotado  # type: ignore[method-assign]
    try:
        yield eventos
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", anotar)
        session.commit = original  # type: ignore[method-assign]


async def test_la_fila_download_esta_confirmada_antes_del_primer_mensaje_de_la_respuesta(
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
    secuencia: list[str],
) -> None:
    """M-3: DESCIFRAR -> fila `download` -> COMMIT -> respuesta. Cuando el api empieza a mandar
    (las cabeceras), la fila ya se insertó y el commit ya ocurrió."""
    adjunto_id = (await subir(session, por, "consent", PDF)).id
    admin = await usuario_real("admin")
    secuencia.clear()
    vistos: dict[str, object] = {}

    async def al_empezar() -> None:
        vistos["eventos"] = list(secuencia)
        vistos["filas"] = await _bajadas(session)
        vistos["decrypt"] = await _descifrados(session, adjunto_id)

    capturada = await pedir_asgi(
        api_prueba,
        f"{RUTA}/{adjunto_id}",
        cabeceras(admin),
        en_primer_mensaje=al_empezar,
    )

    assert capturada.status == 200
    eventos = vistos["eventos"]
    assert isinstance(eventos, list)
    assert "audit" in eventos, eventos
    assert "commit" in eventos[eventos.index("audit") :], eventos
    assert vistos["filas"] == 1 and vistos["decrypt"] == 1
    assert capturada.cuerpo == PDF


async def test_si_el_cliente_corta_tras_las_cabeceras_queda_una_sola_fila_download(
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    adjunto_id = (await subir(session, por, "other", PDF)).id
    admin = await usuario_real("admin")

    capturada = await pedir_asgi(
        api_prueba, f"{RUTA}/{adjunto_id}", cabeceras(admin), cortar_tras_cabeceras=True
    )

    assert capturada.status == 200
    assert await _bajadas(session) == 1
    assert await _descifrados(session, adjunto_id) == 1


async def test_cada_descarga_deja_su_propia_fila_download(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    adjunto_id = (await subir(session, por, "consent", PDF)).id
    admin = await usuario_real("admin")

    for esperadas in (1, 2, 3):
        assert (await _bajar(app_http, cabeceras, admin, adjunto_id)).status_code == 200
        assert await _bajadas(session) == esperadas


async def test_la_foto_no_deja_fila_download_ni_crypto_ops(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    """M-5 / ADR-007: ver una foto no se audita por vista y no pasa por el bus de cifrado."""
    adjunto_id = (await subir(session, por, "photo", JPG)).id
    admin = await usuario_real("admin")

    for _ in range(3):
        r = await _bajar(app_http, cabeceras, admin, adjunto_id)
        assert r.status_code == 200, r.text

    assert await _bajadas(session) == 0
    assert await _descifrados(session, adjunto_id) == 0
    assert await ops_de(session, "encrypt", adjunto_id) == []


# Custodio sellado --------------------------------------------------------------------------------


async def test_con_el_custodio_sellado_el_sensible_da_503_crypto_unavailable_sin_fila(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    adjunto_id = (await subir(session, por, "consent", PDF)).id
    admin = await usuario_real("admin")
    configure_keyring(None)  # el custodio se selló: no hay llaves en memoria

    r = await _bajar(app_http, cabeceras, admin, adjunto_id)

    assert r.status_code == 503, r.text
    assert r.json()["error"]["code"] == "crypto_unavailable"
    assert r.headers["retry-after"] == "30"
    assert PDF[:20] not in r.content
    assert await _bajadas(session) == 0
    assert await _descifrados(session, adjunto_id) == 0


async def test_con_el_custodio_sellado_la_foto_se_sigue_sirviendo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    adjunto_id = (await subir(session, por, "photo", JPG)).id
    admin = await usuario_real("admin")
    configure_keyring(None)

    r = await _bajar(app_http, cabeceras, admin, adjunto_id)

    assert r.status_code == 200, r.text
    assert r.content == JPG


# Cubetas (M-5) -----------------------------------------------------------------------------------


def _topes(app: FastAPI, **cambios: tuple[int, int]) -> None:
    """Reemplaza los topes por usuario de ESTA app (E10): lo que no se cambia queda como estaba."""
    app.state.user_limits = {**app.state.user_limits, **cambios}


async def test_los_topes_por_defecto_de_la_app_son_los_del_catalogo(api_prueba: FastAPI) -> None:
    topes = api_prueba.state.user_limits
    assert topes["attachments-download"] == (30, 60) == USER_LIMITS["attachments-download"]
    assert topes["attachments-download-hour"] == (200, 3600)
    assert topes["attachments-photo"] == (600, 60)


async def test_la_descarga_sensible_31_en_un_minuto_es_429_y_no_descifra(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    adjunto_id = (await subir(session, por, "consent", PDF)).id
    admin = await usuario_real("admin")

    for numero in range(30):
        r = await _bajar(app_http, cabeceras, admin, adjunto_id)
        assert r.status_code == 200, (numero, r.text)
    r = await _bajar(app_http, cabeceras, admin, adjunto_id)

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    # La cubeta se consume ANTES de descifrar: el rechazado no dejó fila ni `decrypt`.
    assert await _bajadas(session) == 30
    assert await _descifrados(session, adjunto_id) == 30


async def test_la_descarga_sensible_tiene_tambien_tope_por_hora(
    api_prueba: FastAPI,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    """La 201.ª en una hora es 429 con el tope real (200/h); aquí el tope se inyecta en 3 (con el
    minuto alto) para no hacer 201 descargas: la prueba fija que la ventana de la HORA corta."""
    adjunto_id = (await subir(session, por, "other", PDF)).id
    admin = await usuario_real("admin")
    _topes(
        api_prueba,
        **{"attachments-download": (1000, 60), "attachments-download-hour": (3, 3600)},
    )

    for _ in range(3):
        assert (await _bajar(app_http, cabeceras, admin, adjunto_id)).status_code == 200
    r = await _bajar(app_http, cabeceras, admin, adjunto_id)

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert await _bajadas(session) == 3


async def test_la_foto_tiene_su_propia_cubeta_attachments_photo(
    api_prueba: FastAPI,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    """La 601.ª foto en un minuto es 429 con el tope real (600/min); aquí se inyecta 3 para no hacer
    601 peticiones. Y la cubeta de la foto y la de los sensibles son contadores distintos."""
    foto = (await subir(session, por, "photo", JPG)).id
    sensible = (await subir(session, por, "consent", PDF)).id
    admin = await usuario_real("admin")
    _topes(api_prueba, **{"attachments-photo": (3, 60), "attachments-download": (2, 60)})

    for _ in range(3):
        assert (await _bajar(app_http, cabeceras, admin, foto)).status_code == 200
    agotada = await _bajar(app_http, cabeceras, admin, foto)
    assert agotada.status_code == 429, agotada.text
    assert agotada.json()["error"]["code"] == "rate_limited"

    # La foto agotada no gasta la cubeta de los sensibles: dos entran y la tercera no.
    for _ in range(2):
        assert (await _bajar(app_http, cabeceras, admin, sensible)).status_code == 200
    assert (await _bajar(app_http, cabeceras, admin, sensible)).status_code == 429
    # Y los sensibles agotados no gastan la de la foto: sigue agotada por lo suyo, no por la otra.
    assert (await _bajar(app_http, cabeceras, admin, foto)).status_code == 429


async def test_los_topes_son_por_usuario(
    api_prueba: FastAPI,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    adjunto_id = (await subir(session, por, "consent", PDF)).id
    uno = await usuario_real("admin")
    otro = await usuario_real("admin")
    _topes(api_prueba, **{"attachments-download": (1, 60)})

    assert (await _bajar(app_http, cabeceras, uno, adjunto_id)).status_code == 200
    assert (await _bajar(app_http, cabeceras, uno, adjunto_id)).status_code == 429
    assert (await _bajar(app_http, cabeceras, otro, adjunto_id)).status_code == 200


# Socio de baja (N-20) y PDF con JavaScript -------------------------------------------------------


async def test_los_adjuntos_de_un_socio_de_baja_siguen_descargables(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    """N-20: subir exige un socio vivo; descargar lo ya guardado no."""
    socio = await make_member(session, deleted_at=T0, status="inactive")
    socio_id = socio.id
    session.expunge(socio)
    sensible = (await subir(session, por, "consent", PDF, dueno=socio_id)).id
    foto = (await subir(session, por, "photo", JPG, dueno=socio_id)).id
    admin = await usuario_real("admin")

    assert (await _bajar(app_http, cabeceras, admin, sensible)).content == PDF
    assert (await _bajar(app_http, cabeceras, admin, foto)).content == JPG


async def test_un_pdf_con_javascript_se_sirve_igual_pero_como_adjunto_y_con_la_csp(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    """Nota de C1: los bytes mágicos no filtran contenido activo; la defensa es `attachment`,
    `nosniff` y la CSP con `sandbox`, no rechazar el archivo."""
    adjunto_id = (await subir(session, por, "other", PDF_CON_JS)).id
    admin = await usuario_real("admin")

    r = await _bajar(app_http, cabeceras, admin, adjunto_id)

    assert r.status_code == 200, r.text
    assert r.content == PDF_CON_JS and b"/JS" in r.content
    assert _tipo(r) == "application/pdf"
    assert r.headers["content-disposition"].startswith("attachment;")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["cache-control"] == "no-store"
