"""`attachments.service.open` (S6-C1, US-147/US-150; S6-D24, S6-D45, S6-D53, M-3, ADR-007).

Orden fijado por M-3: DESCIFRAR -> `audit.record("download", ...)` -> COMMIT -> cuerpo. Un 503 por
custodio sellado no deja una fila `download` falsa. La foto no se audita por vista (`audit=False`) y
se sirve con `stream`, nunca con `get`.

Contratos que el Rojo asume (el Verde puede discutirlos):
- `open` confirma la fila `download` él mismo antes de devolver el cuerpo (otra sesión la ve en
  cuanto `open` retorna, sin que el llamador haya hecho commit);
- `audit=False` solo vale para `kind = photo`: con un sensible se audita igual;
- `open` de un id inexistente lanza `AttachmentNotFound` (404 `attachment_not_found`);
- descifrar un blob que no es de esa fila (AAD distinto) lanza `CryptoError` y no audita.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.keyring import configure_keyring
from app.modules.attachments import files, service
from app.modules.attachments.exceptions import AttachmentNotFound
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo import fila, filas_de_auditoria, ops_de, subir_real
from tests.attachments.conftest import Fabrica
from tests.factories import files as arch

PDF = arch.pdf(6000)
JPG = arch.jpeg(70_000)


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


@pytest.fixture
def contado(tmp_path: Path) -> Iterator[Contado]:
    raiz = tmp_path / "contado"
    raiz.mkdir()
    almacen = Contado(raiz)
    service.configure_storage(almacen)
    try:
        yield almacen
    finally:
        service.configure_storage(None)


@pytest.fixture
def secuencia(engine: AsyncEngine) -> Iterator[list[str]]:
    """Anota 'audit' cuando se inserta en `audit.audit_log` (el resto lo anotan los espías)."""
    eventos: list[str] = []

    def anotar(_c: object, _cur: object, sql: str, *_a: object) -> None:
        if "INSERT INTO audit.audit_log" in sql:
            eventos.append("audit")

    event.listen(engine.sync_engine, "before_cursor_execute", anotar)
    try:
        yield eventos
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", anotar)


async def _bajadas(real: Fabrica) -> list[dict[str, Any]]:
    async with real() as sesion:
        return await filas_de_auditoria(sesion, "download")


# Sensible ---------------------------------------------------------------------------------------


async def test_un_sensible_se_devuelve_descifrado_en_memoria_con_su_metadato(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    dueno = uuid4()
    adjunto = await subir_real(real, por, "consent", PDF, dueno=dueno)

    async with real() as sesion:
        cuerpo = await service.open(sesion, adjunto.id, by=por)

    assert cuerpo.data == PDF and cuerpo.stream is None
    assert (cuerpo.meta.id, cuerpo.meta.kind, cuerpo.meta.mime) == (
        adjunto.id,
        "consent",
        "application/pdf",
    )
    assert (cuerpo.meta.owner_id, cuerpo.meta.sensitive, cuerpo.meta.size_bytes) == (
        dueno,
        True,
        len(PDF),
    )
    assert "filename_random" not in cuerpo.meta.model_dump()


async def test_el_orden_es_descifrar_luego_fila_download_luego_cuerpo(
    real: Fabrica,
    almacen: LocalDiskStorage,
    por: UUID,
    secuencia: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adjunto = await subir_real(real, por, "other", PDF)
    secuencia.clear()
    original = files._decrypt_file

    def espia(blob: bytes, attachment_id: UUID) -> bytes:
        secuencia.append("decrypt")
        return original(blob, attachment_id)

    monkeypatch.setattr(files, "_decrypt_file", espia)

    async with real() as sesion:
        cuerpo = await service.open(sesion, adjunto.id, by=por)
        secuencia.append("cuerpo")
        # Otra sesión ya ve la fila: `open` la confirmó antes de devolver el cuerpo (M-3).
        assert len(await _bajadas(real)) == 1
    assert cuerpo.data == PDF
    assert secuencia == ["decrypt", "audit", "cuerpo"], secuencia


async def test_la_fila_download_lleva_id_sujeto_actor_y_exactamente_kind_sensitive_owner(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    dueno = uuid4()
    adjunto = await subir_real(real, por, "consent", PDF, dueno=dueno)
    async with real() as sesion:
        await service.open(sesion, adjunto.id, by=por)

    (bajada,) = await _bajadas(real)
    assert bajada["record_id"] == adjunto.id
    assert bajada["subject_member_id"] == dueno
    assert bajada["user_id"] == por
    assert bajada["before"] is None
    assert bajada["after"] == {"kind": "consent", "sensitive": True, "owner_id": str(dueno)}
    assert bajada["table_name"] == "attachments.attachments"


async def test_cada_open_deja_una_sola_fila_download_y_un_solo_crypto_ops_decrypt(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    adjunto = await subir_real(real, por, "consent", PDF)
    async with real() as sesion:
        await service.open(sesion, adjunto.id, by=por)
    assert len(await _bajadas(real)) == 1
    async with real() as sesion:
        assert len(await ops_de(sesion, "decrypt", adjunto.id)) == 1
        await service.open(sesion, adjunto.id, by=por)
    assert len(await _bajadas(real)) == 2
    async with real() as sesion:
        assert len(await ops_de(sesion, "decrypt", adjunto.id)) == 2


async def test_con_el_custodio_sellado_da_crypto_unavailable_y_ninguna_fila_download(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    adjunto = await subir_real(real, por, "consent", PDF)
    configure_keyring(None)  # el custodio se selló: no hay llaves en memoria

    async with real() as sesion:
        with pytest.raises(CryptoUnavailable):
            await service.open(sesion, adjunto.id, by=por)
        await sesion.rollback()

    assert await _bajadas(real) == []
    async with real() as sesion:
        assert await ops_de(sesion, "decrypt", adjunto.id) == []


async def test_un_objeto_corrupto_no_ascii_falla_con_crypto_error_y_no_audita(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    """Revisión de seguridad de C1: un objeto sobrescrito con bytes que no son ASCII no puede
    terminar en `UnicodeDecodeError` (500) sino en `CryptoError`, sin fila `download`."""
    a = await subir_real(real, por, "consent", PDF)
    async with real() as sesion:
        fa = await fila(sesion, a.id)
    (almacen.root / fa["filename_random"]).write_bytes(b"\xff\xfe basura \x80" * 100)

    async with real() as sesion:
        with pytest.raises(CryptoError) as exc:
            await service.open(sesion, a.id, by=por)
        await sesion.rollback()

    assert exc.value.code == "blob_invalid"
    assert await _bajadas(real) == []


async def test_un_blob_que_no_es_de_esa_fila_falla_al_descifrar_y_no_audita(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    a = await subir_real(real, por, "consent", PDF)
    b = await subir_real(real, por, "consent", arch.pdf(3000))
    async with real() as sesion:
        fa, fb = await fila(sesion, a.id), await fila(sesion, b.id)
    (almacen.root / fa["filename_random"]).write_bytes(
        (almacen.root / fb["filename_random"]).read_bytes()
    )

    async with real() as sesion:
        with pytest.raises(CryptoError):
            await service.open(sesion, a.id, by=por)
        await sesion.rollback()

    assert await _bajadas(real) == []


async def test_audit_false_no_desactiva_la_auditoria_de_un_sensible(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    adjunto = await subir_real(real, por, "other", PDF)
    async with real() as sesion:
        await service.open(sesion, adjunto.id, by=por, audit=False)

    assert len(await _bajadas(real)) == 1


# Foto --------------------------------------------------------------------------------------------


async def test_la_foto_con_audit_false_se_sirve_por_stream_sin_fila_ni_crypto_ops(
    real: Fabrica, contado: Contado, por: UUID
) -> None:
    adjunto = await subir_real(real, por, "photo", JPG)

    async with real() as sesion:
        cuerpo = await service.open(sesion, adjunto.id, by=por, audit=False)
        assert cuerpo.data is None and cuerpo.stream is not None
        recibido = b"".join([t async for t in cuerpo.stream])

    assert recibido == JPG
    assert (contado.gets, contado.streams) == (0, 1)
    assert await _bajadas(real) == []
    async with real() as sesion:
        assert await ops_de(sesion, "decrypt", adjunto.id) == []


async def test_la_foto_se_sirve_aunque_el_custodio_este_sellado(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    adjunto = await subir_real(real, por, "photo", JPG)
    configure_keyring(None)

    async with real() as sesion:
        cuerpo = await service.open(sesion, adjunto.id, by=por, audit=False)
        assert cuerpo.stream is not None
        assert b"".join([t async for t in cuerpo.stream]) == JPG


async def test_el_stream_de_la_foto_entrega_trozos_de_a_lo_sumo_64_kib(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    adjunto = await subir_real(real, por, "photo", JPG)
    async with real() as sesion:
        cuerpo = await service.open(sesion, adjunto.id, by=por, audit=False)
        assert cuerpo.stream is not None
        trozos = [t async for t in cuerpo.stream]
    assert [len(t) for t in trozos] == [65536, len(JPG) - 65536]


# No encontrado -----------------------------------------------------------------------------------


async def test_un_id_inexistente_es_404_attachment_not_found(
    real: Fabrica, almacen: LocalDiskStorage, por: UUID
) -> None:
    async with real() as sesion:
        with pytest.raises(AttachmentNotFound) as error:
            await service.open(sesion, uuid4(), by=por)
    assert (error.value.status, error.value.code) == (404, "attachment_not_found")
    assert await _bajadas(real) == []
