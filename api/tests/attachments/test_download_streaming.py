"""Streaming de la foto y memoria del sensible en `GET /attachments/{id}` (S6-C4, US-150; S6-D24,
S6-D45, S6-D110, S6-D113, ADR-007). Rojo C4.

- la foto sale por `stream`: el service nunca llama `storage.get`;
- objeto de una foto que falta (S6-C4, decisión 2 del orquestador): el service lo detecta ANTES de
  devolver el cuerpo (no hay cabeceras enviadas todavía) y lanza `AttachmentNotFound` (404
  `attachment_not_found`, como el sensible de C1), sin fila `download`, no un 200 cortado;
- decisión del Rojo sobre un fallo A MITAD del `stream` (cabeceras ya enviadas): la respuesta se
  corta sin que la excepción llegue al servidor ASGI ni quede un registro con traceback;
- memoria: pico de la descarga de un sensible de 5 MiB medido con `tracemalloc` (tope = medido +
  2 MiB, ver `TOPE_MEMORIA`).
"""

from __future__ import annotations

import logging
import tracemalloc
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Final
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attachments import rules, service
from app.modules.attachments.exceptions import AttachmentNotFound
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo import fila, filas_de_auditoria, pedir_asgi, subir, subir_real
from tests.attachments.conftest import Fabrica
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories import files

RUTA = "/api/v1/attachments"
JPG = files.jpeg(200_000)  # 4 trozos de 64 KiB
MIB: Final = 1024 * 1024
TOPE_MEMORIA: Final = 35.5 * MIB  # medido en service.open_attachment: 33.42 MiB + 2 MiB
# Descarga HTTP completa (incluye las copias del cliente de prueba): 34.26 MiB + 2 MiB, medida con
# una implementación desechable de la ruta.
TOPE_MEMORIA_HTTP: Final = 36.5 * MIB


class Contado(LocalDiskStorage):
    """Almacén local que cuenta cuántas veces se usó `get` y `stream`."""

    def __init__(self, raiz: Path) -> None:
        super().__init__(raiz)
        self.gets = 0
        self.streams = 0

    async def get(self, key: str) -> bytes:
        self.gets += 1
        return await super().get(key)

    def stream(self, key: str, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        self.streams += 1
        return super().stream(key, chunk_size)


class CortaAMitad(LocalDiskStorage):
    """`stream` entrega un trozo y luego falla como si el objeto desapareciera del disco."""

    def stream(self, key: str, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        return self._corta(key, chunk_size)

    async def _corta(self, key: str, chunk_size: int) -> AsyncIterator[bytes]:
        async for trozo in super().stream(key, chunk_size):
            yield trozo
            raise FileNotFoundError(key)


@pytest.fixture
def contado(tmp_path: Path) -> Iterator[Contado]:
    yield from _instalar(Contado, tmp_path)


@pytest.fixture
def corta(tmp_path: Path) -> Iterator[CortaAMitad]:
    yield from _instalar(CortaAMitad, tmp_path)


def _instalar[T: LocalDiskStorage](clase: type[T], tmp_path: Path) -> Iterator[T]:
    raiz = tmp_path / clase.__name__
    raiz.mkdir()
    almacen = clase(raiz)
    service.configure_storage(almacen)
    try:
        yield almacen
    finally:
        service.configure_storage(None)


# La foto sale por stream -------------------------------------------------------------------------


async def test_la_foto_se_descarga_por_stream_y_el_service_nunca_llama_get(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    contado: Contado,
    por: UUID,
) -> None:
    adjunto_id = (await subir(session, por, "photo", JPG)).id
    admin = await usuario_real("admin")

    r = await app_http.get(f"{RUTA}/{adjunto_id}", headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    assert r.content == JPG
    assert (contado.gets, contado.streams) == (0, 1)
    assert await filas_de_auditoria(session, "download") == []


async def test_el_sensible_se_lee_con_get_y_nunca_por_stream(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    contado: Contado,
    por: UUID,
) -> None:
    adjunto_id = (await subir(session, por, "consent", files.pdf(5000))).id
    admin = await usuario_real("admin")

    r = await app_http.get(f"{RUTA}/{adjunto_id}", headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    assert (contado.gets, contado.streams) == (1, 0)


# Objeto ausente ----------------------------------------------------------------------------------


async def test_una_foto_sin_objeto_falla_en_el_service_antes_de_devolver_el_cuerpo(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:

    foto = await subir_real(real, por, "photo", JPG)
    async with real() as sesion:
        nombre = (await fila(sesion, foto.id))["filename_random"]
    (almacen.root / nombre).unlink()

    async with real() as sesion:
        with pytest.raises(AttachmentNotFound) as error:
            await service.open_attachment(sesion, foto.id, by=por, audit=False)

    assert (error.value.status, error.value.code) == (404, "attachment_not_found")


async def test_una_foto_sin_objeto_responde_404_attachment_not_found_sin_enviar_cuerpo(
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    adjunto = await subir(session, por, "photo", JPG)
    adjunto_id = adjunto.id
    nombre = (await fila(session, adjunto_id))["filename_random"]
    (almacen.root / nombre).unlink()
    admin = await usuario_real("admin")

    capturada = await pedir_asgi(api_prueba, f"{RUTA}/{adjunto_id}", cabeceras(admin))

    assert capturada.status == 404
    assert b"image" not in capturada.cabeceras.get("content-type", "").encode()
    assert capturada.cuerpo.count(b"attachment_not_found") == 1
    assert await filas_de_auditoria(session, "download") == []


async def test_un_fallo_a_mitad_del_stream_corta_la_respuesta_sin_excepcion_ni_traceback(
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    corta: CortaAMitad,
    por: UUID,
    caplog: pytest.LogCaptureFixture,
) -> None:
    adjunto_id = (await subir(session, por, "photo", JPG)).id
    admin = await usuario_real("admin")

    with caplog.at_level(logging.DEBUG):
        capturada = await pedir_asgi(api_prueba, f"{RUTA}/{adjunto_id}", cabeceras(admin))

    # Las cabeceras ya salieron con 200; el cuerpo quedó incompleto y NADA lanzó hacia el servidor.
    assert capturada.status == 200
    assert 0 < len(capturada.cuerpo) < len(JPG)
    con_traza = [r for r in caplog.records if r.exc_info]
    assert con_traza == [], [r.getMessage() for r in con_traza]
    assert not [r for r in caplog.records if "Exception in ASGI" in r.getMessage()]


# Memoria -----------------------------------------------------------------------------------------


async def test_el_pico_de_memoria_del_service_al_abrir_un_sensible_de_5_mib_queda_acotado(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    """Se sube fuera de la medida; el pico es solo el de `service.open_attachment` (blob, descifrado
    y fila `download`) con el cuerpo de 5 MiB exactos."""

    datos = files.pdf(rules.ATTACHMENT_MAX_BYTES)
    adjunto = await subir_real(real, por, "consent", datos)
    async with real() as sesion:
        tracemalloc.start()
        try:
            tracemalloc.reset_peak()
            base = tracemalloc.get_traced_memory()[0]
            cuerpo = await service.open_attachment(sesion, adjunto.id, by=por)
            pico = tracemalloc.get_traced_memory()[1] - base
        finally:
            tracemalloc.stop()
    assert cuerpo.data == datos
    print(f"MEDIDA service.open_attachment sensible 5 MiB: pico {pico / MIB:.2f} MiB")
    assert pico < TOPE_MEMORIA, f"{pico / MIB:.2f} MiB"


async def test_el_pico_de_memoria_de_la_descarga_http_de_un_sensible_de_5_mib_queda_acotado(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
) -> None:
    """Incluye las copias del cliente de prueba (cuerpo entero en memoria): es una cota superior."""
    datos = files.pdf(rules.ATTACHMENT_MAX_BYTES)
    adjunto_id = (await subir(session, por, "other", datos)).id
    admin = await usuario_real("admin")
    cabecera = cabeceras(admin)
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        base = tracemalloc.get_traced_memory()[0]
        r = await app_http.get(f"{RUTA}/{adjunto_id}", headers=cabecera)
        pico = tracemalloc.get_traced_memory()[1] - base
    finally:
        tracemalloc.stop()
    assert r.status_code == 200 and len(r.content) == len(datos)
    print(f"MEDIDA GET http sensible 5 MiB: pico {pico / MIB:.2f} MiB")
    assert pico < TOPE_MEMORIA_HTTP, f"{pico / MIB:.2f} MiB"
