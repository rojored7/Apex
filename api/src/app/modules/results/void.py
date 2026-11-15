"""Anulación de un resultado por un admin (S8-B3b, S8-D46 b, M-1 de la revisión de B3). Privado.

El coach no tiene salida ante un resultado puesto en el socio o la clase equivocada: el admin lo
anula con motivo. El resultado pasa a `status = voided` y `is_current = false`, SIN sucesor (la
guarda y el trigger diferido de `0040` lo permiten solo para esa transición); un anulado es
terminal y ningún `supersedes_id` puede apuntarle. La marca no se toca: queda en la auditoría
(`update` con el motivo) y en `GET /wods/{id}/results?include_superseded=true`.

Orden de candados (el mismo del registro, S8-D36): socio (`lock_member`) y luego el resultado
`FOR UPDATE`. Se lee el resultado una vez sin candado para conocer al socio; con el candado se
vuelve a leer con datos frescos, así una corrección o anulación concurrente (que ya confirmó)
da 409 y nunca se anula dos veces. El motivo no va al evento ni al log (texto libre, S3-D70).
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import current_clock
from app.core.locks import lock_member
from app.modules.results.events import WodResultVoided
from app.modules.results.exceptions import ResultAlreadyVoided, ResultNotFound, ResultNotVoidable
from app.modules.results.models import WodResult
from app.modules.results.schemas import ResultOut, VoidIn

logger = logging.getLogger("app.results")


async def _locked(session: AsyncSession, result_id: UUID) -> WodResult:
    """El resultado `FOR UPDATE` con datos frescos (404 si no existe)."""
    fila = await session.scalar(
        select(WodResult)
        .where(WodResult.id == result_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if fila is None:
        raise ResultNotFound()
    return fila


async def void_result(
    session: AsyncSession, result_id: UUID, data: VoidIn, *, by: UUID
) -> ResultOut:
    miembro = await session.scalar(select(WodResult.member_id).where(WodResult.id == result_id))
    if miembro is None:
        raise ResultNotFound()
    await lock_member(session, miembro)
    fila = await _locked(session, result_id)
    if fila.status == "voided":
        raise ResultAlreadyVoided()
    if not fila.is_current or fila.status != "validated":
        raise ResultNotVoidable()
    fila.status = "voided"
    fila.is_current = False
    fila.voided_by = by
    fila.voided_at = current_clock().now_utc()
    fila.void_reason = data.reason
    await session.flush()
    await events.emit(
        WodResultVoided(result_id=fila.id, member_id=fila.member_id, wod_id=fila.wod_id), session
    )
    logger.info("results: resultado anulado", extra={"result_id": str(fila.id)})
    return ResultOut.model_validate(fila)
