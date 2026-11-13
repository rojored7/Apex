"""Consultas de adjuntos (S6-C1; S6-D22, G-04). Solo lectura; SQL de SQLAlchemy con parámetros."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, any_uuids, chunked, paginate
from app.modules.attachments.models import Attachment


async def get_row(session: AsyncSession, attachment_id: UUID) -> Attachment | None:
    return await session.scalar(select(Attachment).where(Attachment.id == attachment_id))


async def current_photo_ids(
    session: AsyncSession, owner_table: str, owner_ids: Sequence[UUID]
) -> dict[UUID, UUID | None]:
    """La foto vigente (`created_at DESC, id DESC`) de cada dueño: UNA consulta por lote de 200.

    Todo id pedido aparece en el resultado (`None` si no tiene foto)."""
    resultado: dict[UUID, UUID | None] = dict.fromkeys(owner_ids)
    for lote in chunked(list(resultado)):
        consulta = (
            select(Attachment.owner_id, Attachment.id)
            .where(
                Attachment.owner_table == owner_table,
                Attachment.kind == "photo",
                Attachment.owner_id == any_uuids(lote),
            )
            .ext(distinct_on(Attachment.owner_id))
            .order_by(Attachment.owner_id, Attachment.created_at.desc(), Attachment.id.desc())
        )
        for dueno, adjunto in (await session.execute(consulta)).all():
            resultado[dueno] = adjunto
    return resultado


async def list_rows(
    session: AsyncSession, owner_table: str, owner_id: UUID, page: PageParams
) -> tuple[list[Attachment], int]:
    consulta = (
        select(Attachment)
        .where(Attachment.owner_table == owner_table, Attachment.owner_id == owner_id)
        .order_by(Attachment.created_at.desc(), Attachment.id.desc())
    )
    return await paginate(session, consulta, page)


async def sensitive_rows_not_with_key(
    session: AsyncSession, active_key_id: UUID, limit: int
) -> list[Attachment]:
    """Sensibles con otra llave que la activa, con `FOR UPDATE SKIP LOCKED` (recifrado).

    Sin `ORDER BY`: con SKIP LOCKED el orden no aporta (cada lote toma lo que quede libre)."""
    consulta = (
        select(Attachment)
        .where(Attachment.sensitive.is_(True), Attachment.key_id != active_key_id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list((await session.scalars(consulta)).all())


async def sensitive_row_keys(session: AsyncSession) -> list[tuple[UUID, str, UUID | None]]:
    """`(id, filename_random, key_id)` de las filas sensibles (solo para `attachments-check`)."""
    consulta = select(Attachment.id, Attachment.filename_random, Attachment.key_id).where(
        Attachment.sensitive.is_(True)
    )
    return [(i, n, k) for i, n, k in (await session.execute(consulta)).all()]


async def row_keys(session: AsyncSession) -> dict[UUID, str]:
    """`{id: filename_random}` de todas las filas (solo para `attachments-check`)."""
    consulta = select(Attachment.id, Attachment.filename_random)
    return {i: nombre for i, nombre in (await session.execute(consulta)).all()}
