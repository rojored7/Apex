"""Fachada del service de `athletes` (S9-A1). Lo único que importan los demás módulos."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ColumnElement, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.athletes import derive
from app.modules.athletes.derive import RederiveResult
from app.modules.athletes.events import PersonalRecordSet
from app.modules.athletes.metrics import add_metric, list_metrics, reveal_metric, void_metric
from app.modules.athletes.models import PersonalRecord
from app.modules.athletes.records import add_record, invalidate_manual_record, list_records
from app.modules.wods import service as wods_service


async def _has_live(session: AsyncSession, objetivo: ColumnElement[bool]) -> bool:
    """`EXISTS` de un récord NO invalidado (columna desnuda, S8-D50; índices parciales
    `ix_personal_records_movement` / `_benchmark`, S9-D54): una consulta `EXISTS`.

    La ausencia de TOCTOU con `PATCH` del catálogo depende de READ COMMITTED (el nivel por defecto
    de la base): el `PATCH` espera el `FOR SHARE` del alta y, al despertar, esta consulta ve el
    récord ya confirmado. Con REPEATABLE READ habría que volver a pensarlo (S9-D56)."""
    consulta = select(exists().where(objetivo, PersonalRecord.invalidated_at.is_(None)))
    return bool(await session.scalar(consulta))


class _RecordsProbe:
    """`wods.RecordsProbe` (S9-D9, S9-D54): ¿hay récords vivos de un movimiento o benchmark?"""

    async def movement_has_records(self, session: AsyncSession, movement_id: UUID) -> bool:
        return await _has_live(session, PersonalRecord.movement_id == movement_id)

    async def benchmark_has_records(self, session: AsyncSession, benchmark_id: UUID) -> bool:
        return await _has_live(session, PersonalRecord.benchmark_id == benchmark_id)


async def rederive_member(
    session: AsyncSession, member_id: UUID, *, strict: bool
) -> RederiveResult:
    """Deriva los récords que falten de un socio (S9-D21): ver `derive.rederive_member`."""
    return await derive.rederive_member(session, member_id, strict=strict)


records_probe = _RecordsProbe()
wods_service.set_records_probe(records_probe)
# S9-D7: los handlers de `results` se suscriben al importarse la fachada.
derive.subscribe_handlers()

__all__ = [
    "PersonalRecordSet",
    "RederiveResult",
    "add_metric",
    "add_record",
    "invalidate_manual_record",
    "list_metrics",
    "list_records",
    "records_probe",
    "rederive_member",
    "reveal_metric",
    "void_metric",
]
