"""Escrituras y búsquedas de la importación (privado de `app.imports`; S4B-D34, D36).

Todo pasa por `members.service` y `core.audit`: nada de SQL propio. Una transacción por socio.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.cli_session import read_only_session
from app.core import audit
from app.imports.results import ImportResult
from app.modules.members import service as members_service
from app.modules.members.exceptions import MemberDocumentDuplicated
from app.modules.members.schemas import MemberCreate

SUMMARY_TABLE = "members.import_runs"
"""`table_name` lógico: no es un modelo auditado por el hook (S4B-D36, S4B-D74)."""


async def document_exists(session_factory: Any, document: str) -> bool:
    """El documento ya es de un socio vivo (índice ciego; sin escribir ni dejar `crypto_ops`)."""
    async with read_only_session(session_factory) as session:
        return await members_service.id_by_document(session, document) is not None


async def create_member(session_factory: Any, data: MemberCreate) -> bool:
    """Alta en su propia transacción; `False` si otro proceso ya dio de alta ese documento."""
    try:
        async with session_factory() as session, session.begin():
            await members_service.create(session, data)
    except MemberDocumentDuplicated:
        return False
    return True


async def write_summary(
    session_factory: Any, result: ImportResult, rows: int, *, partial: bool = False
) -> UUID:
    """Entrada resumen de la corrida (S4B-D36): hash del archivo y conteos, nunca su nombre."""
    corrida = uuid4()
    despues = {
        "file_sha256": result.file_sha256,
        "rows": rows,
        "created": result.created,
        "skipped_existing": result.skipped_existing,
        "rejected": result.rejected,
        "consent_missing": result.consent_missing,
        "notes_ignored": result.notes_ignored,
        "contacts_omitted": result.contacts_omitted,
        "partial": partial,
    }
    async with session_factory() as session, session.begin():
        await audit.record(
            session,
            action="insert",
            table_name=SUMMARY_TABLE,
            record_id=corrida,
            before=None,
            after=despues,
        )
    return corrida
