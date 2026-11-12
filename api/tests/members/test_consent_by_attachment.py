"""Subir la autorización (`kind=consent`) fija la autorización de datos (S6-C3, US-149; S6-D46,
S6-D19 invertida, S6-D114).

- `consent` sobre un socio SIN autorización: fija `data_consent_at` con el reloj y copia la versión
  vigente de la política; deja una fila `update` del socio con antes y después;
- con autorización previa no cambia nada (ni fecha, ni versión, ni fila `update`);
- `photo` y `other` no tocan el consentimiento;
- sin política publicada, `consent` sobre un socio sin autorización da 409
  `privacy_version_missing` ANTES de leer el cuerpo (0 trozos), sin adjunto ni objeto guardado.
Todo va por ASGI con cuerpo crudo; el socio se desprende de la sesión (S6-D114).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto.keyring import Keyring
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.conftest import T0, Cabeceras, CrearUsuario, UsuarioPrueba
from tests.factories import files
from tests.factories.members import make_member
from tests.members._apoyo import auditoria_del_socio, fila_socio
from tests.members._consentimiento import HOY, VERSION, publicar_politica, quitar_version
from tests.members.test_attach_photo import ruta_adjuntos


@pytest.fixture
async def admin(usuario_real: CrearUsuario, bus_listo: Keyring) -> UsuarioPrueba:
    return await usuario_real("admin")


async def _subir(
    app_http: AsyncClient, cabeceras: Cabeceras, quien: UsuarioPrueba, socio_id: UUID, kind: str,
    contenido: Any,
) -> Response:  # fmt: skip
    return await app_http.post(
        ruta_adjuntos(socio_id, kind), content=contenido, headers=cabeceras(quien)
    )


async def _adjuntos(session: AsyncSession) -> int:
    return int(await session.scalar(text("SELECT count(*) FROM attachments.attachments")) or 0)


async def test_subir_la_autorizacion_fija_la_fecha_y_la_version_y_audita_update(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
) -> None:
    await publicar_politica(session, admin.id, corte=HOY)
    socio = await make_member(session, data_consent_at=None)
    socio_id = socio.id
    session.expunge(socio)  # S6-D114

    r = await _subir(app_http, cabeceras, admin, socio_id, "consent", files.pdf(4096))

    assert r.status_code == 201, r.text
    fila = await fila_socio(session, socio_id)
    assert fila["data_consent_at"] == T0
    assert fila["data_consent_version"] == VERSION
    (update,) = await auditoria_del_socio(session, socio_id, "update")
    assert set(update["after"]) == {"data_consent_at", "data_consent_version"}
    assert update["after"]["data_consent_version"] == VERSION
    assert update["before"] is not None
    assert update["before"].get("data_consent_at") is None
    assert update["before"].get("data_consent_version") is None
    assert update["user_id"] == admin.id


async def test_subir_la_autorizacion_de_un_socio_ya_autorizado_no_cambia_nada(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
) -> None:
    await publicar_politica(session, admin.id, corte=HOY)
    original = T0 - timedelta(days=30)
    socio = await make_member(session, data_consent_at=original, data_consent_version="2025-01")
    socio_id = socio.id
    session.expunge(socio)
    antes = await fila_socio(session, socio_id)

    r = await _subir(app_http, cabeceras, admin, socio_id, "consent", files.pdf(4096))

    assert r.status_code == 201, r.text
    assert await fila_socio(session, socio_id) == antes
    assert await auditoria_del_socio(session, socio_id, "update") == []


@pytest.mark.parametrize(
    ("kind", "contenido"),
    [("photo", files.jpeg(2048)), ("other", files.pdf(2048))],
    ids=["foto", "otro"],
)
async def test_la_foto_y_otro_no_tocan_la_autorizacion(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    kind: str,
    contenido: bytes,
) -> None:
    await publicar_politica(session, admin.id, corte=HOY)
    socio = await make_member(session, data_consent_at=None)
    socio_id = socio.id
    session.expunge(socio)

    r = await _subir(app_http, cabeceras, admin, socio_id, kind, contenido)

    assert r.status_code == 201, r.text
    fila = await fila_socio(session, socio_id)
    assert fila["data_consent_at"] is None and fila["data_consent_version"] is None
    assert await auditoria_del_socio(session, socio_id, "update") == []


async def test_sin_politica_publicada_subir_la_autorizacion_da_409_sin_leer_el_cuerpo(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
) -> None:
    # corte vigente sin version publicada (S6-C3 regla 2); sin corte la subida sigue dando 201
    await publicar_politica(session, admin.id, corte=HOY)
    await quitar_version(session)
    socio = await make_member(session, data_consent_at=None)
    socio_id = socio.id
    session.expunge(socio)
    cuerpo = files.Contado(files.pdf(300_000))
    antes = await fila_socio(session, socio_id)
    adjuntos = await _adjuntos(session)

    r = await _subir(app_http, cabeceras, admin, socio_id, "consent", cuerpo)

    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "privacy_version_missing"
    assert cuerpo.trozos == 0
    assert await _adjuntos(session) == adjuntos
    assert list(almacen.root.iterdir()) == []
    assert await fila_socio(session, socio_id) == antes
