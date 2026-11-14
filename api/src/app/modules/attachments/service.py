"""Fachada de `attachments` (S6-C1, US-147; S6-D18, S6-D22, S6-D59, S6-D75, S6-D84).

Lo único que importan los demás módulos (regla de módulos 2).

- `store(...)`: consume `chunks` (en el router de `members`, `request.stream()`) acumulando hasta
  `ATTACHMENT_MAX_BYTES`: al byte 5.242.881 lanza `FileTooLarge` sin seguir leyendo; un cliente que
  no manda el siguiente trozo antes del tiempo máximo TOTAL (`ATTACHMENT_UPLOAD_TIMEOUT_S`, que se
  lee en cada llamada) da `UploadTimeout`. El tipo lo deciden los bytes mágicos. Un sensible se
  cifra por `files._encrypt_file` con `aad_for(id)`; el objeto se guarda ANTES del `flush` y se
  borra si el `flush` falla (compensación, sin nombre de archivo en el log).
- Las operaciones sensibles (subir y abrir) toman uno de `SENSITIVE_SLOTS` cupos globales sin
  esperar: la quinta concurrente da 503 `busy` con `Retry-After: 1` (M-3, D59). La foto no los usa.
- `authorize(...)`: fila (404) y rol (403) antes de cobrar cubeta y de descifrar (S6-C4).
- `open(...)`: DESCIFRA -> `audit.record("download")` -> COMMIT -> cuerpo (M-3): con el custodio
  sellado no queda una fila `download` falsa. La foto (`audit=False`) se sirve por `stream`.
- `configure_storage(storage)`: lo llaman `main.py` y `cli_base.py`; `None` lo vuelve a derivar.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing, asynccontextmanager
from dataclasses import replace
from typing import Final, cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit as _audit
from app.core.context import actor_scope
from app.core.crypto.reencryptor import reencryptor_registered
from app.core.crypto.reencryptor import register_reencryptor as _register_port
from app.core.db import DatabaseBusy
from app.core.errors import ForbiddenError
from app.core.pagination import Page, PageParams, to_page
from app.modules.attachments import files, queries, rules
from app.modules.attachments.exceptions import (
    AttachmentNotFound,
    FileTooLarge,
    StorageUnavailable,
    UnsupportedType,
    UploadTimeout,
)
from app.modules.attachments.models import Attachment
from app.modules.attachments.reencrypt import AttachmentReencryptor
from app.modules.attachments.schemas import AttachmentBody, AttachmentOut
from app.modules.attachments.storage import current_storage, set_current_storage
from app.modules.attachments.storage.base import StorageProvider

logger = logging.getLogger("app.attachments")

SENSITIVE_SLOTS: Final = 4
DATA_CLASS: Final = files.DATA_CLASS
AUDIT_TABLE: Final = "attachments.attachments"
MAGIC_BYTES: Final = 16
_BLOB_HEADER_BYTES: Final = (
    64  # cubre `apx1.<uuid>.` (41 bytes) para leer la cabecera sin descifrar
)

_slots = asyncio.Semaphore(SENSITIVE_SLOTS)


def configure_storage(storage: StorageProvider | None) -> None:
    set_current_storage(storage)


def register_reencryptor() -> None:
    """Registra el puerto de recifrado de `attachment.sensitive` (idempotente)."""
    if not reencryptor_registered(DATA_CLASS):
        _register_port(DATA_CLASS, AttachmentReencryptor())


@asynccontextmanager
async def _sensitive_slot() -> AsyncIterator[None]:
    """Un cupo global sin esperar: el excedente es 503 `busy` (no encola memoria de 5 MiB)."""
    if _slots.locked():
        raise DatabaseBusy
    await _slots.acquire()
    try:
        yield
    finally:
        _slots.release()


def ensure_declared_size(content_length: str | None) -> None:
    """413 sin leer el cuerpo si el `Content-Length` declarado supera el tope (S6-D84, S6-C2)."""
    if content_length is not None and content_length.isdigit():
        if int(content_length) > rules.ATTACHMENT_MAX_BYTES:
            raise FileTooLarge


async def _read_body(chunks: AsyncIterator[bytes]) -> bytes:
    """Acumula hasta el tope; corta al cruzar `ATTACHMENT_READ_LIMIT` y al agotar el tiempo."""
    limite = time.monotonic() + rules.ATTACHMENT_UPLOAD_TIMEOUT_S
    acumulado = bytearray()
    siguiente = chunks.__aiter__().__anext__
    while True:
        restante = limite - time.monotonic()
        if restante <= 0:
            raise UploadTimeout
        try:
            trozo = await asyncio.wait_for(siguiente(), restante)
        except StopAsyncIteration:
            break
        except TimeoutError:
            raise UploadTimeout from None
        acumulado += trozo
        if len(acumulado) >= rules.ATTACHMENT_READ_LIMIT:
            raise FileTooLarge
    datos = bytes(acumulado)
    acumulado.clear()
    return datos


async def _put_object(storage: StorageProvider, name: str, payload: bytes) -> None:
    try:
        await storage.put(name, payload)
    except StorageUnavailable:
        raise
    except Exception as error:
        logger.error("no se pudo guardar un adjunto (%s)", type(error).__name__)
        raise StorageUnavailable from error


async def _compensate(storage: StorageProvider, name: str) -> None:
    """Borra el objeto huérfano tras un `flush` fallido; el log no lleva el nombre del archivo."""
    try:
        await storage.delete_object(name)
    except Exception as error:
        logger.error("no se pudo compensar un objeto huérfano (%s)", type(error).__name__)
    else:
        logger.warning("flush fallido: se borró el objeto recién guardado")


async def store(
    session: AsyncSession,
    *,
    owner_table: str,
    owner_id: UUID,
    kind: str,
    chunks: AsyncIterator[bytes],
    by: UUID,
) -> Attachment:
    sensitive = rules.kind_is_sensitive(kind)
    datos = await _read_body(chunks)
    mime = rules.detect_mime(datos[:MAGIC_BYTES])
    if mime is None:
        raise UnsupportedType
    rules.validate_upload(len(datos), mime, kind)
    if not sensitive:
        return await _save(session, owner_table, owner_id, kind, mime, datos, False, by)
    async with _sensitive_slot():
        return await _save(session, owner_table, owner_id, kind, mime, datos, sensitive, by)


async def _save(
    session: AsyncSession,
    owner_table: str,
    owner_id: UUID,
    kind: str,
    mime: str,
    datos: bytes,
    sensitive: bool,
    by: UUID,
) -> Attachment:
    adjunto_id, nombre, size = uuid4(), uuid4().hex, len(datos)
    key_id: UUID | None = None
    payload = datos
    if sensitive:
        # hasta 5 MiB: fuera del event loop; `to_thread` copia el actor y el buffer de `crypto_ops`
        payload = await asyncio.to_thread(files._encrypt_file, datos, adjunto_id)
        key_id = files.blob_key_id(payload)
    del datos
    storage = current_storage()
    await _put_object(storage, nombre, payload)
    adjunto = Attachment(
        id=adjunto_id,
        owner_table=owner_table,
        owner_id=owner_id,
        kind=kind,
        filename_random=nombre,
        mime=mime,
        size_bytes=size,
        sensitive=sensitive,
        key_id=key_id,
        storage_provider=_provider_name(storage),
        uploaded_by=by,
        created_by=by,
    )
    session.add(adjunto)
    try:
        await session.flush()
    except BaseException:
        await _compensate(storage, nombre)
        raise
    return adjunto


def _provider_name(storage: StorageProvider) -> str:
    return storage.name


def can_upload(role: str, kind: str) -> bool:
    return rules.can_upload(role, kind)


async def authorize(session: AsyncSession, attachment_id: UUID, *, role: str) -> AttachmentOut:
    """Fila (404) y luego rol (403), ANTES de cobrar cubeta y de descifrar (S6-C4, M-6). Devuelve
    los metadatos para que el router elija la cubeta (sensible o foto)."""
    fila = await queries.get_row(session, attachment_id)
    if fila is None:
        raise AttachmentNotFound
    if not rules.can_download(role, fila.sensitive):
        raise ForbiddenError
    return AttachmentOut.model_validate(fila)


async def open_attachment(
    session: AsyncSession, attachment_id: UUID, *, by: UUID, audit: bool = True
) -> AttachmentBody:
    fila = await queries.get_row(session, attachment_id)
    if fila is None:
        raise AttachmentNotFound
    meta = AttachmentOut.model_validate(fila)
    storage = current_storage()
    if not fila.sensitive:
        if not await storage.exists(fila.filename_random):
            # Decidido antes de enviar cabeceras; el huérfano lo lista `attachments-check`.
            logger.warning("adjunto %s sin objeto en el almacenamiento", attachment_id)
            raise AttachmentNotFound
        if audit:
            with actor_scope(by):
                await _record_download(session, fila, by)
        return AttachmentBody(meta=meta, stream=_guarded(storage.stream(fila.filename_random)))
    async with _sensitive_slot():
        try:
            blob = await storage.get(fila.filename_random)
        except FileNotFoundError:
            logger.warning("adjunto %s sin objeto en el almacenamiento", attachment_id)
            raise AttachmentNotFound from None
        with actor_scope(by):  # el `decrypt` de `crypto_ops` y la fila `download` llevan al actor
            datos = await asyncio.to_thread(files._decrypt_file, blob, fila.id)
            del blob
            await _record_download(session, fila, by)
    return AttachmentBody(meta=meta, data=datos)


async def _guarded(stream: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    """Cuerpo de la foto: un fallo del almacén tras enviar las cabeceras corta la respuesta con UNA
    línea WARNING (sin nombre de archivo) en vez de lanzar hacia el servidor (S6-C4)."""
    try:
        async for trozo in stream:
            yield trozo
    except Exception as error:
        logger.warning("descarga de foto cortada a mitad (%s)", type(error).__name__)
    finally:
        cerrar = getattr(stream, "aclose", None)
        if cerrar is not None:
            await cerrar()


async def _record_download(session: AsyncSession, fila: Attachment, by: UUID) -> None:
    """Fila `download` (sin nombre de archivo ni llave) y COMMIT antes de devolver el cuerpo."""
    await _audit.record(
        session,
        action="download",
        table_name=AUDIT_TABLE,
        record_id=fila.id,
        before=None,
        after={"kind": fila.kind, "sensitive": fila.sensitive, "owner_id": str(fila.owner_id)},
        user_id=by,
        subject_member_id=fila.owner_id,
    )
    await session.commit()


async def current_photo_id(
    session: AsyncSession, owner_table: str, owner_ids: list[UUID]
) -> dict[UUID, UUID | None]:
    return await queries.current_photo_ids(session, owner_table, owner_ids)


async def list_for_owner(
    session: AsyncSession, owner_table: str, owner_id: UUID, page: PageParams
) -> Page[AttachmentOut]:
    filas, total = await queries.list_rows(session, owner_table, owner_id, page)
    return to_page([AttachmentOut.model_validate(f) for f in filas], total, page)


async def orphan_report(session: AsyncSession) -> rules.OrphanReport:
    """Filas sin objeto y objetos sin fila (`attachments-check`, S6-D22): solo lectura."""
    almacen = current_storage()
    claves = [clave async for clave in almacen.list_keys()]
    informe = rules.find_orphans(await queries.row_keys(session), claves)
    presentes = set(claves)
    distintos: list[UUID] = []
    for id_, nombre, key_id in await queries.sensitive_row_keys(session):
        if nombre in presentes and await _head_key_id(almacen, nombre) != key_id:
            distintos.append(id_)
    return replace(informe, key_mismatch=tuple(sorted(distintos)))


async def _head_key_id(almacen: StorageProvider, nombre: str) -> UUID | None:
    """`key_id` de la cabecera del objeto: lee solo los primeros bytes, sin descifrar."""
    cabecera = b""
    try:
        async with aclosing(
            cast("AsyncGenerator[bytes, None]", almacen.stream(nombre, _BLOB_HEADER_BYTES))
        ) as trozos:
            async for trozo in trozos:
                cabecera += trozo
                if len(cabecera) >= _BLOB_HEADER_BYTES:
                    break
    except FileNotFoundError:  # desapareció entre el listado y la lectura
        return None
    return files.peek_key_id(cabecera[:_BLOB_HEADER_BYTES])
