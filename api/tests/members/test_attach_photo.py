"""`POST /api/v1/members/{member_id}/attachments?kind=` (S6-C2, US-148; S6-D59, S6-D73, S6-D84;
E1, E13, M-4, M-6, N-20).

Todo va por ASGI/`httpx` directamente contra el api, sin Nginx (E13), con cuerpo crudo
(`content=bytes` o `content=<iterador>`), sin `files=` ni formulario.

La sesión del api es la de la prueba (savepoint): el router suelta la conexión con
`session.rollback()` tras validar al socio (S6-D114), lo que expira los objetos cargados; cada
prueba desprende (`expunge`) al socio recién creado para seguir leyendo su `id`.

- orden de validación: `kind` (422 de FastAPI), socio (404) y rol por `kind` (403) ANTES de leer un
  solo byte: el cuerpo es un iterador que cuenta (`Contado`) y debe quedar en 0 trozos;
- tope propio por bytes: `Content-Length` mayor que 5 MiB se rechaza sin leer; uno falso (menor, o
  mayor que el cuerpo real) no se cree: el corte es por bytes leídos (413 `file_too_large`,
  `field = "file"`); `Transfer-Encoding: chunked` sin `Content-Length` igual;
- 422 `unsupported_type` (`field = "file"`) por bytes mágicos; el `Content-Type` del cliente no
  cuenta; `sensitive` lo decide el servidor (no hay campos);
- coach: solo `photo` (M-6); socio (rol `member`): 403;
- la foto nueva es la vigente; nada de `tempfile` durante la petición; D84: un cliente que manda un
  trozo y calla da 408 `upload_timeout`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto.keyring import Keyring
from app.modules.attachments import rules
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo import insertar
from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories import files
from tests.factories.members import make_member
from tests.members._apoyo import MEMBERS, ruta_socio

LECTURA_MAXIMA = rules.ATTACHMENT_READ_LIMIT


def ruta_adjuntos(member_id: UUID | str, kind: str | None = "photo", extra: str = "") -> str:
    consulta = [] if kind is None else [f"kind={kind}"]
    if extra:
        consulta.append(extra)
    sufijo = f"?{'&'.join(consulta)}" if consulta else ""
    return f"{MEMBERS}/{member_id}/attachments{sufijo}"


async def _subir(
    app_http: AsyncClient,
    cabeceras: Cabeceras,
    quien: Any,
    url: str,
    contenido: Any,
    **cabecera_extra: str,
) -> Response:
    return await app_http.post(
        url, content=contenido, headers={**cabeceras(quien), **cabecera_extra}
    )


async def _filas(session: AsyncSession) -> int:
    return int(await session.scalar(text("SELECT count(*) FROM attachments.attachments")) or 0)


async def _fila(session: AsyncSession, adjunto_id: str) -> dict[str, Any]:
    r = await session.execute(
        text("SELECT * FROM attachments.attachments WHERE id = :i"), {"i": UUID(adjunto_id)}
    )
    return dict(r.mappings().one())


# 404 y socios de baja (N-20) -----------------------------------------------------------------


async def test_un_socio_inexistente_da_404_member_not_found_sin_leer_un_trozo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    admin = await usuario_real("admin")
    cuerpo = files.Contado(files.jpeg(300_000))
    antes = await _filas(session)
    r = await _subir(app_http, cabeceras, admin, ruta_adjuntos(uuid4()), cuerpo)
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"
    assert cuerpo.trozos == 0
    assert await _filas(session) == antes
    assert list(almacen.root.iterdir()) == []


async def test_un_socio_dado_de_baja_da_404_al_subir_pero_su_listado_sigue(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    """N-20: subir exige un socio vivo; el listado de un dado de baja sigue disponible."""
    socio = await make_member(session, deleted_at=T0 - timedelta(days=1), status="inactive")
    socio_id = socio.id  # el 404 deja el objeto expirado (rollback de la sesión compartida)
    admin = await usuario_real("admin")
    cuerpo = files.Contado(files.jpeg(300_000))
    r = await _subir(app_http, cabeceras, admin, ruta_adjuntos(socio_id), cuerpo)
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"
    assert cuerpo.trozos == 0

    lista = await app_http.get(ruta_adjuntos(socio_id, None), headers=cabeceras(admin))
    assert lista.status_code == 200, lista.text
    assert lista.json()["total"] == 0


# Éxito, tipo y tamaño -------------------------------------------------------------------------


async def test_subir_una_foto_da_201_con_el_adjunto_y_la_guarda_en_claro(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    foto = files.jpeg(2048)
    r = await _subir(app_http, cabeceras, admin, ruta_adjuntos(socio.id), foto)
    assert r.status_code == 201, r.text
    datos = r.json()
    assert (datos["kind"], datos["mime"], datos["size_bytes"], datos["sensitive"]) == (
        "photo",
        "image/jpeg",
        2048,
        False,
    )
    assert (datos["owner_table"], datos["owner_id"]) == ("members", str(socio.id))
    assert datos["uploaded_by"] == str(admin.id)
    fila = await _fila(session, datos["id"])
    assert (almacen.root / fila["filename_random"]).read_bytes() == foto


async def test_un_ejecutable_renombrado_jpg_da_422_unsupported_type_con_field_file(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    antes = await _filas(session)
    r = await _subir(
        app_http, cabeceras, admin, ruta_adjuntos(socio.id), files.elf(4096),
        **{"Content-Type": "image/jpeg"},
    )  # fmt: skip
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "unsupported_type"
    assert r.json()["error"]["field"] == "file"
    assert await _filas(session) == antes
    assert list(almacen.root.iterdir()) == []


async def test_un_cuerpo_de_5_mib_mas_un_byte_da_413_file_too_large_con_field_file(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    antes = await _filas(session)
    r = await _subir(
        app_http, cabeceras, admin, ruta_adjuntos(socio.id), files.jpeg(files.TOPE_MAS_UNO)
    )
    assert r.status_code == 413, r.text
    assert r.json()["error"]["code"] == "file_too_large"
    assert r.json()["error"]["field"] == "file"
    assert await _filas(session) == antes
    assert list(almacen.root.iterdir()) == []


async def test_un_cuerpo_de_exactamente_5_mib_da_201(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    r = await _subir(app_http, cabeceras, admin, ruta_adjuntos(socio.id), files.jpeg(files.TOPE))
    assert r.status_code == 201, r.text
    assert r.json()["size_bytes"] == files.TOPE


async def test_la_foto_nueva_pasa_a_ser_la_vigente(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    """La vigente es la más reciente (`created_at DESC, id DESC`): la anterior se siembra con una
    fecha pasada para que el orden no dependa del `now()` de la transacción de la prueba."""
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    vieja = await insertar(
        session,
        owner=socio.id,
        created_at=datetime.now(UTC) - timedelta(days=1),
        por=admin.id,
    )
    antes = await app_http.get(ruta_socio(socio.id), headers=cabeceras(admin))
    assert antes.json()["photo_attachment_id"] == str(vieja)

    r = await _subir(app_http, cabeceras, admin, ruta_adjuntos(socio.id), files.png(2048))
    assert r.status_code == 201, r.text
    ficha = await app_http.get(ruta_socio(socio.id), headers=cabeceras(admin))
    assert ficha.json()["photo_attachment_id"] == r.json()["id"] != str(vieja)


async def test_el_content_type_del_cliente_se_ignora_el_tipo_lo_deciden_los_bytes(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    r = await _subir(
        app_http, cabeceras, admin, ruta_adjuntos(socio.id), files.jpeg(2048),
        **{"Content-Type": "text/plain"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    assert r.json()["mime"] == "image/jpeg"


async def test_sensitive_lo_decide_el_servidor_no_el_cliente(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    """No existe campo de formulario ni parámetro `sensitive`: aunque el cliente lo mande, la foto
    sale en claro y `consent` cifrado."""
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    foto = await _subir(
        app_http,
        cabeceras,
        admin,
        ruta_adjuntos(socio.id, "photo", "sensitive=true"),
        files.jpeg(2048),
    )
    consentimiento = await _subir(
        app_http,
        cabeceras,
        admin,
        ruta_adjuntos(socio.id, "consent", "sensitive=false"),
        files.pdf(4096),
    )
    assert foto.status_code == 201 and consentimiento.status_code == 201, (
        foto.text,
        consentimiento.text,
    )
    assert foto.json()["sensitive"] is False
    assert consentimiento.json()["sensitive"] is True
    objeto = (
        almacen.root / (await _fila(session, consentimiento.json()["id"]))["filename_random"]
    ).read_bytes()
    assert files.MARCA_PDF not in objeto


# Roles (M-6) ----------------------------------------------------------------------------------


async def test_el_coach_sube_una_foto_y_recibe_201(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    coach = await usuario_real("coach")
    r = await _subir(app_http, cabeceras, coach, ruta_adjuntos(socio.id, "photo"), files.jpeg(2048))
    assert r.status_code == 201, r.text
    assert r.json()["uploaded_by"] == str(coach.id)


@pytest.mark.parametrize("kind", ["consent", "other"])
async def test_el_coach_recibe_403_con_consent_y_other_sin_leer_un_trozo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
    kind: str,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    coach = await usuario_real("coach")
    cuerpo = files.Contado(files.pdf(300_000))
    antes = await _filas(session)
    r = await _subir(app_http, cabeceras, coach, ruta_adjuntos(socio.id, kind), cuerpo)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert cuerpo.trozos == 0
    assert await _filas(session) == antes
    assert list(almacen.root.iterdir()) == []


async def test_el_admin_sube_consent_y_other_cifrados(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    for kind in ("consent", "other"):
        r = await _subir(app_http, cabeceras, admin, ruta_adjuntos(socio.id, kind), files.pdf(4096))
        assert r.status_code == 201, r.text
        assert (r.json()["kind"], r.json()["sensitive"], r.json()["mime"]) == (
            kind,
            True,
            "application/pdf",
        )


async def test_el_rol_member_recibe_403_sin_leer_un_trozo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    miembro = await usuario_real("member")
    cuerpo = files.Contado(files.jpeg(300_000))
    r = await _subir(app_http, cabeceras, miembro, ruta_adjuntos(socio.id), cuerpo)
    assert r.status_code == 403, r.text
    assert cuerpo.trozos == 0


# kind validado antes de leer (E1, M-4) ---------------------------------------------------------


@pytest.mark.parametrize("kind", ["x", None, "PHOTO", ""])
async def test_un_kind_invalido_o_ausente_da_422_de_fastapi_sin_leer_un_trozo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
    kind: str | None,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    cuerpo = files.Contado(files.jpeg(300_000))
    antes = await _filas(session)
    r = await _subir(app_http, cabeceras, admin, ruta_adjuntos(socio.id, kind), cuerpo)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["field"] == "kind"
    assert cuerpo.trozos == 0
    assert await _filas(session) == antes


async def test_un_member_id_que_no_es_uuid_da_422_sin_leer_un_trozo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    admin = await usuario_real("admin")
    cuerpo = files.Contado(files.jpeg(300_000))
    r = await _subir(app_http, cabeceras, admin, ruta_adjuntos("no-es-uuid"), cuerpo)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "member_id"
    assert cuerpo.trozos == 0


async def test_kind_se_valida_contra_el_catalogo_antes_de_llamar_a_las_reglas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    """Nota de C1 (S6-D113): `rules` lanza `ValueError` (500) con un `kind` desconocido; el router
    debe cortar con 422 antes. Un valor fuera del catálogo nunca llega a `rules` ni da 500."""
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    socio_id = (
        socio.id
    )  # una respuesta de error expira el objeto (rollback de la sesión compartida)
    admin = await usuario_real("admin")
    for invalido in ("documento", "Photo", "photo%20", "consent,other", "null"):
        r = await _subir(
            app_http, cabeceras, admin, ruta_adjuntos(socio_id, invalido), files.jpeg(2048)
        )
        assert r.status_code == 422, (invalido, r.status_code, r.text)
        assert r.json()["error"]["field"] == "kind", invalido


# Content-Length y chunked (E13, S6-D84) --------------------------------------------------------


async def test_content_length_mayor_que_el_tope_da_413_sin_leer_un_trozo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    cuerpo = files.Contado(files.jpeg(300_000))
    r = await _subir(
        app_http, cabeceras, admin, ruta_adjuntos(socio.id), cuerpo,
        **{"Content-Length": str(files.TOPE_MAS_UNO)},
    )  # fmt: skip
    assert r.status_code == 413, r.text
    assert (r.json()["error"]["code"], r.json()["error"]["field"]) == ("file_too_large", "file")
    assert cuerpo.trozos == 0
    assert list(almacen.root.iterdir()) == []


async def test_content_length_que_declara_10_y_manda_mas_del_tope_corta_en_el_byte_5242881(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    """La cabecera miente por debajo: no se confía en ella; el iterador no se consume más allá del
    byte 5.242.881 (con trozos de 4 KiB, a lo sumo un trozo de más)."""
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    trozo = 4096
    cuerpo = files.Contado(files.jpeg(8 * 1024 * 1024), trozo)
    r = await _subir(
        app_http, cabeceras, admin, ruta_adjuntos(socio.id), cuerpo, **{"Content-Length": "10"}
    )
    assert r.status_code == 413, r.text
    assert (r.json()["error"]["code"], r.json()["error"]["field"]) == ("file_too_large", "file")
    assert LECTURA_MAXIMA <= cuerpo.bytes_entregados <= LECTURA_MAXIMA + trozo
    assert list(almacen.root.iterdir()) == []


async def test_content_length_que_declara_mas_del_tope_con_un_cuerpo_de_100_bytes_da_413_sin_leer(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    cuerpo = files.Contado(files.jpeg(100))
    r = await _subir(
        app_http, cabeceras, admin, ruta_adjuntos(socio.id), cuerpo,
        **{"Content-Length": str(files.TOPE_MAS_UNO)},
    )  # fmt: skip
    assert r.status_code == 413, r.text
    assert r.json()["error"]["code"] == "file_too_large"
    assert cuerpo.trozos == 0


async def test_chunked_sin_content_length_acepta_5_mib_y_rechaza_5_mib_mas_un_byte(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    exacto = await _subir(
        app_http, cabeceras, admin, ruta_adjuntos(socio.id), files.en_trozos(files.jpeg(files.TOPE))
    )
    assert exacto.request.headers.get("transfer-encoding") == "chunked"
    assert "content-length" not in exacto.request.headers
    assert exacto.status_code == 201, exacto.text

    de_mas = await _subir(
        app_http, cabeceras, admin, ruta_adjuntos(socio.id),
        files.en_trozos(files.jpeg(files.TOPE_MAS_UNO)),
    )  # fmt: skip
    assert de_mas.request.headers.get("transfer-encoding") == "chunked"
    assert de_mas.status_code == 413, de_mas.text
    assert de_mas.json()["error"]["code"] == "file_too_large"


async def test_un_iterador_infinito_se_corta_en_el_tope_y_da_413(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
) -> None:
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    cuerpo = files.Infinito(files.jpeg(64), 65536)
    r = await _subir(app_http, cabeceras, admin, ruta_adjuntos(socio.id), cuerpo)
    assert r.status_code == 413, r.text
    assert LECTURA_MAXIMA <= cuerpo.bytes_entregados <= LECTURA_MAXIMA + 65536


async def test_la_subida_nunca_usa_tempfile(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
    sin_tempfile: None,
) -> None:
    """Sin spool ni `/tmp` (E1): ni en un 201, ni en un 413, ni con `consent` (cifrado)."""
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    ok = await _subir(app_http, cabeceras, admin, ruta_adjuntos(socio.id), files.jpeg(300_000))
    sensible = await _subir(
        app_http, cabeceras, admin, ruta_adjuntos(socio.id, "consent"), files.pdf(300_000)
    )
    grande = await _subir(
        app_http, cabeceras, admin, ruta_adjuntos(socio.id), files.jpeg(files.TOPE_MAS_UNO)
    )
    assert (ok.status_code, sensible.status_code, grande.status_code) == (201, 201, 413)


# D84: tiempo máximo -----------------------------------------------------------------------------


async def test_un_cliente_que_manda_un_trozo_y_calla_da_408_upload_timeout(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    almacen: LocalDiskStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El tiempo máximo se lee de `rules.ATTACHMENT_UPLOAD_TIMEOUT_S` en cada llamada (C1): con
    0,3 s un generador que entrega un trozo y espera 60 s da 408 sin fila, sin objeto y sin
    esperar el segundo trozo."""
    monkeypatch.setattr(rules, "ATTACHMENT_UPLOAD_TIMEOUT_S", 0.3)
    socio = await make_member(session)
    session.expunge(socio)  # S6-D114: el rollback del router expira lo cargado en la sesión
    admin = await usuario_real("admin")
    cuerpo = files.Lento(files.jpeg(512), espera_s=60)
    antes = await _filas(session)
    r = await _subir(app_http, cabeceras, admin, ruta_adjuntos(socio.id), cuerpo)
    assert r.status_code == 408, r.text
    assert r.json()["error"]["code"] == "upload_timeout"
    assert cuerpo.espero_de_mas is False
    assert await _filas(session) == antes
    assert list(almacen.root.iterdir()) == []
