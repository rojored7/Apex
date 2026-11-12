"""Adjuntos del socio (S6-C2, US-148; S6-D18, S6-D20, S6-D59, S6-D84). Privado de `members`: solo
lo importa `members/service.py`, que reexporta `attach`, `list_attachments` y `current_photo`.

- `attach(session, member_id, *, kind, chunks, by)`: valida el socio vivo (404 también para uno
  dado de baja, N-20) ANTES de leer un trozo y guarda por `attachments.service.store` (arista
  `members -> attachments`); devuelve el `AttachmentOut` sin `filename_random`.
- `list_attachments(session, member_id, page)`: adjuntos del socio, también dado de baja (N-20).
- `current_photo(session, member_ids)`: `{socio: foto vigente | None}` en UNA consulta por lote.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, PageParams
from app.modules.attachments import service as attachments_service
from app.modules.attachments.schemas import AttachmentOut
from app.modules.members.exceptions import MemberNotFound
from app.modules.members.models import Member

OWNER_TABLE = "members"

ensure_declared_size = attachments_service.ensure_declared_size

__all__ = [
    "OWNER_TABLE",
    "attach",
    "attachments_service",
    "current_photo",
    "ensure_declared_size",
    "list_attachments",
]


async def _ensure(session: AsyncSession, member_id: UUID, *, include_deleted: bool) -> None:
    consulta = select(Member.id).where(Member.id == member_id)
    if not include_deleted:
        consulta = consulta.where(Member.deleted_at.is_(None))
    if await session.scalar(consulta) is None:
        raise MemberNotFound()


async def attach(
    session: AsyncSession,
    member_id: UUID,
    *,
    kind: Literal["photo", "consent", "other"],
    chunks: AsyncIterator[bytes],
    by: UUID,
) -> AttachmentOut:
    """Sube un adjunto del socio. El router ya validó al socio vivo (404 antes de leer un solo
    trozo) y soltó la conexión (S6-D114): aquí no se repite el `SELECT`."""
    fila = await attachments_service.store(
        session, owner_table=OWNER_TABLE, owner_id=member_id, kind=kind, chunks=chunks, by=by
    )
    return AttachmentOut.model_validate(fila)


async def list_attachments(
    session: AsyncSession, member_id: UUID, page: PageParams
) -> Page[AttachmentOut]:
    """Adjuntos del socio, también dado de baja (N-20); `MemberNotFound` si no existe."""
    await _ensure(session, member_id, include_deleted=True)
    return await attachments_service.list_for_owner(session, OWNER_TABLE, member_id, page)


async def current_photo(
    session: AsyncSession, member_ids: Sequence[UUID]
) -> dict[UUID, UUID | None]:
    """`{socio: foto vigente | None}`: UNA consulta por lote de 200 (E8, sin N+1)."""
    if not member_ids:
        return {}
    return await attachments_service.current_photo_id(session, OWNER_TABLE, list(member_ids))
