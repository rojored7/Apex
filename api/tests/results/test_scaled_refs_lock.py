"""Un WOD con resultados no pierde un movimiento que un resultado escalado referencia (S8-B1d, L-9).

`scaled_movement_ids` apunta a movimientos del WOD; quitar uno de la lista dejaría una referencia
colgante. `update_wod` lo niega con 422 `locked_by_results` (`field = "movements"`).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.wods import service as wods_service
from app.modules.wods.exceptions import LockedByResults
from app.modules.wods.schemas import WodPatch
from tests.factories.wods import cuerpo_wod
from tests.results._apoyo import Escena, escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def _quitar_de_la_lista(session: AsyncSession, e: Escena, dejar: list[UUID]) -> None:
    patch = WodPatch.model_validate({"movements": cuerpo_wod(dejar)["movements"]})
    with actor_scope(e.coach):
        await wods_service.update_wod(session, e.wod_id, patch, e.coach)


async def test_no_se_quita_un_movimiento_referenciado_por_un_resultado_escalado(
    session: AsyncSession,
) -> None:
    e = await escena(session)
    uno, dos = e.movimientos
    await registrar(session, e, level="scaled", scaled_movement_ids=[dos])
    with pytest.raises(LockedByResults) as error:
        await _quitar_de_la_lista(session, e, [uno])
    assert error.value.field == "movements"
    despues = await wods_service.get_wod(session, e.wod_id)
    assert [m.movement_id for m in despues.movements] == [uno, dos]


async def test_se_quita_un_movimiento_que_ningun_resultado_referencia(
    session: AsyncSession,
) -> None:
    e = await escena(session)
    uno, _dos = e.movimientos
    await registrar(session, e, level="scaled", scaled_movement_ids=[uno])
    await _quitar_de_la_lista(session, e, [uno])
    despues = await wods_service.get_wod(session, e.wod_id)
    assert [m.movement_id for m in despues.movements] == [uno]


async def test_un_resultado_corregido_ya_no_referencia_el_movimiento(session: AsyncSession) -> None:
    """Solo cuenta el resultado VIGENTE: tras corregirlo sin el movimiento, se puede quitar."""
    e = await escena(session)
    uno, dos = e.movimientos
    primero = await registrar(session, e, level="scaled", scaled_movement_ids=[dos])
    await registrar(session, e, level="rx", scaled_movement_ids=[], supersedes_id=primero.id)
    await _quitar_de_la_lista(session, e, [uno])
    despues = await wods_service.get_wod(session, e.wod_id)
    assert [m.movement_id for m in despues.movements] == [uno]
