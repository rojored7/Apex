"""Semáforo global de descargas sensibles (S6-C4, US-150; S6-D59, S6-D113, M-3). Rojo C4.

`SENSITIVE_SLOTS = 4` cupos sin espera: la quinta descarga sensible concurrente recibe 503 `busy`
con `Retry-After: 1` y las cuatro restantes terminan bien; al liberarse un cupo entra otra. La
concurrencia real se prueba en el service con una sesión por llamada (commit real); la traducción
a HTTP (503 `busy`, `Retry-After: 1`, sin fila) con el semáforo ya lleno sobre la sesión de la
prueba, porque `app_http` comparte una sola sesión.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import DatabaseBusy
from app.modules.attachments import service
from app.modules.attachments.exceptions import AttachmentNotFound
from app.modules.attachments.schemas import AttachmentBody
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo import fila, filas_de_auditoria, subir, subir_real
from tests.attachments.conftest import Fabrica
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories import files

PDF = files.pdf(6000)


class Esperando(LocalDiskStorage):
    """`get` espera un evento: mantiene ocupado el cupo mientras la prueba lanza las demás."""

    def __init__(self, raiz: Path) -> None:
        super().__init__(raiz)
        self.liberar = asyncio.Event()
        self.dentro = 0

    async def get(self, key: str) -> bytes:
        self.dentro += 1
        await self.liberar.wait()
        return await super().get(key)


@pytest.fixture
def esperando(tmp_path: Path) -> Iterator[Esperando]:
    raiz = tmp_path / "esperando"
    raiz.mkdir()
    almacen = Esperando(raiz)
    service.configure_storage(almacen)
    try:
        yield almacen
    finally:
        service.configure_storage(None)


async def _abrir(real: Fabrica, adjunto_id: UUID, por: UUID) -> AttachmentBody:
    async with real() as sesion:
        return await service.open_attachment(sesion, adjunto_id, by=por)


async def _liberador(almacen: Esperando, cupos: int) -> None:
    """Espera a que `cupos` descargas estén dentro del `get` y da unos ciclos a la excedente."""
    for _ in range(2000):
        if almacen.dentro >= cupos:
            break
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.1)
    almacen.liberar.set()


async def _bajadas(real: Fabrica) -> int:
    async with real() as sesion:
        return len(await filas_de_auditoria(sesion, "download"))


async def test_cinco_descargas_sensibles_concurrentes_una_recibe_busy_y_cuatro_terminan(
    real: Fabrica, esperando: Esperando, por: UUID
) -> None:
    adjunto = await subir_real(real, por, "consent", PDF)

    resultados = await asyncio.gather(
        *[_abrir(real, adjunto.id, por) for _ in range(5)],
        _liberador(esperando, service.SENSITIVE_SLOTS),
        return_exceptions=True,
    )

    descargas = resultados[:5]
    fallos = [r for r in descargas if isinstance(r, BaseException)]
    buenas = [r for r in descargas if isinstance(r, AttachmentBody)]
    assert len(fallos) == 1 and isinstance(fallos[0], DatabaseBusy), descargas
    assert (fallos[0].status, fallos[0].code) == (503, "busy")
    assert len(buenas) == 4 and all(b.data == PDF for b in buenas)
    assert esperando.dentro == 4  # la excedente ni llegó a leer el almacén
    assert await _bajadas(real) == 4  # y no dejó fila


async def test_al_liberarse_un_cupo_una_sexta_descarga_entra(
    real: Fabrica, esperando: Esperando, por: UUID
) -> None:
    adjunto = await subir_real(real, por, "other", PDF)
    await asyncio.gather(
        *[_abrir(real, adjunto.id, por) for _ in range(5)],
        _liberador(esperando, service.SENSITIVE_SLOTS),
        return_exceptions=True,
    )

    sexta = await _abrir(real, adjunto.id, por)

    assert sexta.data == PDF
    assert await _bajadas(real) == 5


async def test_un_objeto_ausente_dentro_del_cupo_no_lo_deja_tomado(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    """Un objeto ausente (404) dentro del cupo no lo deja tomado: seis intentos fallidos seguidos
    y luego una descarga buena entra."""
    malo = await subir_real(real, por, "consent", PDF)
    bueno = await subir_real(real, por, "consent", PDF)
    async with real() as sesion:
        nombre = (await fila(sesion, malo.id))["filename_random"]
    (almacen.root / nombre).unlink()

    for _ in range(service.SENSITIVE_SLOTS + 2):
        with pytest.raises(AttachmentNotFound):
            await _abrir(real, malo.id, por)

    assert (await _abrir(real, bueno.id, por)).data == PDF


async def test_con_el_semaforo_lleno_la_ruta_responde_503_busy_retry_after_1_sin_fila(
    api_prueba: FastAPI,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adjunto_id = (await subir(session, por, "consent", PDF)).id
    admin = await usuario_real("admin")
    lleno = asyncio.Semaphore(0)  # los cuatro cupos ya están tomados
    monkeypatch.setattr(service, "_slots", lleno)

    r = await app_http.get(f"/api/v1/attachments/{adjunto_id}", headers=cabeceras(admin))

    assert r.status_code == 503, r.text
    assert r.json()["error"]["code"] == "busy"
    assert r.headers["retry-after"] == "1"
    assert await filas_de_auditoria(session, "download") == []


async def test_la_foto_no_usa_el_semaforo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    almacen: LocalDiskStorage,
    por: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adjunto_id = (await subir(session, por, "photo", files.jpeg(5000))).id
    admin = await usuario_real("admin")
    monkeypatch.setattr(service, "_slots", asyncio.Semaphore(0))

    r = await app_http.get(f"/api/v1/attachments/{adjunto_id}", headers=cabeceras(admin))

    assert r.status_code == 200, r.text
