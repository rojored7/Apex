"""Pendientes de recifrado de una clase (S6-B1; S6-D14, G-09), parte de `core/crypto/service.py`.

Cuenta lo que aún no usa la llave activa: por el puerto `Reencryptor` si la clase lo registró
(gana sobre las columnas) o por las columnas `Encrypted` que el registro declara. Una clase
que cifra y no tiene ni columnas ni puerto no se puede rotar (`rotation_not_supported`).
Sin `core/audit` ni `app.modules`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto.discovery import ColumnRef, encrypted_columns
from app.core.crypto.errors import CryptoError
from app.core.crypto.reencryptor import get_reencryptor
from app.core.db import Base


def blob_key(ref: ColumnRef) -> Any:
    """Segundo campo del blob `apx1.<key_id>.<alg>...`, como texto."""
    return func.split_part(ref.column, ".", 2)


async def count_where(session: AsyncSession, ref: ColumnRef, condition: Any) -> int:
    stmt = select(func.count()).select_from(ref.table).where(condition)
    return int(await session.scalar(stmt) or 0)


def require_rotatable(data_class: str) -> None:
    """`CryptoError(rotation_not_supported)` sin puerto ni columnas (no crea job ni llave)."""
    if get_reencryptor(data_class) is None and not encrypted_columns(Base.metadata, data_class):
        raise CryptoError("rotation_not_supported", f"la clase {data_class} no admite rotación")


async def pending_total(session: AsyncSession, data_class: str, active_id: UUID) -> int:
    """Registros de la clase cuyo blob no es de la llave activa."""
    if (puerto := get_reencryptor(data_class)) is not None:
        return await puerto.count_pending(session, active_id)
    refs = encrypted_columns(Base.metadata, data_class)
    return sum([await count_where(session, r, blob_key(r) != str(active_id)) for r in refs])
