"""`Reencryptor` de `attachment.sensitive` (S6-C1; S6-D26, S6-D107, G-09, L-3).

El puerto cuenta por la columna `key_id` (sin leer archivos). `reencrypt_batch` toma, con
`FOR UPDATE SKIP LOCKED`, las filas sensibles con otra llave que la activa, descifra con la llave
del propio blob (`decrypt_only` incluida), cifra con la activa, REEMPLAZA el objeto de forma atómica
(misma clave) y después actualiza `key_id`. Un corte entre el objeto y el `UPDATE` es inocuo: el
siguiente lote lo recifra otra vez. Procesa de a un objeto (cada uno ocupa hasta 5 MiB en memoria).
"""

from __future__ import annotations

import asyncio
from typing import Final
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attachments import files, queries
from app.modules.attachments.models import Attachment
from app.modules.attachments.storage import current_storage

# Lotes de 10 (S6-D111, revisión de base de datos de C1): los candados de fila de `FOR UPDATE SKIP
# LOCKED` se sostienen durante la E/S de cada objeto (hasta 5 MiB), y con S3 cada uno es un viaje.
BATCH_SIZE: Final = 10


class AttachmentReencryptor:
    async def count_total(self, session: AsyncSession) -> int:
        consulta = (
            select(func.count()).select_from(Attachment).where(Attachment.sensitive.is_(True))
        )
        return int(await session.scalar(consulta) or 0)

    async def count_pending(self, session: AsyncSession, active_key_id: UUID) -> int:
        consulta = (
            select(func.count())
            .select_from(Attachment)
            .where(Attachment.sensitive.is_(True), Attachment.key_id != active_key_id)
        )
        return int(await session.scalar(consulta) or 0)

    async def count_by_key(self, session: AsyncSession, key_id: UUID) -> int:
        consulta = select(func.count()).select_from(Attachment).where(Attachment.key_id == key_id)
        return int(await session.scalar(consulta) or 0)

    async def reencrypt_batch(
        self, session: AsyncSession, active_key_id: UUID, batch_size: int
    ) -> int:
        filas = await queries.sensitive_rows_not_with_key(
            session, active_key_id, min(batch_size, BATCH_SIZE)
        )
        if not filas:
            return 0
        almacen = current_storage()
        with files.batch():
            for fila in filas:
                blob = await almacen.get(fila.filename_random)
                nuevo = await asyncio.to_thread(files._reencrypt_blob, blob, fila.id)
                await almacen.put(fila.filename_random, nuevo)
                await session.execute(
                    update(Attachment)
                    .where(Attachment.id == fila.id)
                    .values(key_id=files.blob_key_id(nuevo), updated_at=func.now())
                    .execution_options(synchronize_session=False)
                )
        return len(filas)
