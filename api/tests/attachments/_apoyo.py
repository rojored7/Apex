"""Ayudas comunes de las pruebas de `attachments` (S6-C1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.context import actor_scope
from app.modules.attachments import service
from app.modules.attachments.models import Attachment
from tests.factories.files import en_trozos


async def subir(
    session: AsyncSession,
    por: UUID,
    kind: str,
    data: bytes,
    *,
    dueno: UUID | None = None,
    tam: int = 65536,
) -> Attachment:
    """`service.store` bajo el actor `por`, con el cuerpo en trozos de `tam`."""
    with actor_scope(por):
        adjunto = await service.store(
            session,
            owner_table="members",
            owner_id=dueno or uuid4(),
            kind=kind,
            chunks=en_trozos(data, tam),
            by=por,
        )
        await session.flush()
    return adjunto


async def fila(session: AsyncSession, adjunto_id: UUID) -> dict[str, Any]:
    """La fila cruda de la tabla (con `filename_random` y `key_id`)."""
    resultado = await session.execute(
        text("SELECT * FROM attachments.attachments WHERE id = :id"), {"id": adjunto_id}
    )
    return dict(resultado.mappings().one())


async def filas_de_auditoria(session: AsyncSession, accion: str) -> list[dict[str, Any]]:
    resultado = await session.execute(
        text(
            "SELECT * FROM audit.audit_log WHERE action = :a "
            "AND table_name = 'attachments.attachments' ORDER BY seq"
        ),
        {"a": accion},
    )
    return [dict(f) for f in resultado.mappings().all()]


async def ops_de(session: AsyncSession, verbo: str, record_id: UUID) -> list[dict[str, Any]]:
    resultado = await session.execute(
        text(
            "SELECT * FROM crypto.crypto_ops WHERE data_class = 'attachment.sensitive' "
            "AND verb = :v AND record_id = :r ORDER BY at"
        ),
        {"v": verbo, "r": record_id},
    )
    return [dict(f) for f in resultado.mappings().all()]


async def subir_real(
    fabrica: async_sessionmaker[AsyncSession],
    por: UUID,
    kind: str,
    data: bytes,
    *,
    dueno: UUID | None = None,
) -> Attachment:
    """`service.store` con commit real en su propia sesión (las filas de `crypto_ops` y de
    auditoría salen en el commit)."""
    with actor_scope(por):
        async with fabrica() as sesion, sesion.begin():
            return await service.store(
                sesion,
                owner_table="members",
                owner_id=dueno or uuid4(),
                kind=kind,
                chunks=en_trozos(data),
                by=por,
            )


async def insertar(
    session: AsyncSession,
    *,
    owner: UUID,
    kind: str = "photo",
    created_at: datetime | None = None,
    id_: UUID | None = None,
    por: UUID | None = None,
    nombre: str | None = None,
) -> UUID:
    """Una fila cruda válida (CHECKs de D25) con `created_at` e `id` a gusto de la prueba."""
    identificador = id_ or uuid4()
    sensible = kind != "photo"
    await session.execute(
        text(
            "INSERT INTO attachments.attachments (id, owner_table, owner_id, kind, "
            "filename_random, mime, size_bytes, sensitive, key_id, storage_provider, "
            "uploaded_by, created_at, updated_at, created_by) VALUES (:id, 'members', :owner, "
            ":kind, :nombre, :mime, 100, :sensible, :llave, 'local', :por, "
            "COALESCE(CAST(:creada AS timestamptz), now()), "
            "COALESCE(CAST(:creada AS timestamptz), now()), :por)"
        ),
        {
            "id": identificador,
            "owner": owner,
            "kind": kind,
            "nombre": nombre or uuid4().hex,
            "mime": "application/pdf" if sensible else "image/jpeg",
            "sensible": sensible,
            "llave": uuid4() if sensible else None,
            "por": por or uuid4(),
            "creada": created_at,
        },
    )
    return identificador
