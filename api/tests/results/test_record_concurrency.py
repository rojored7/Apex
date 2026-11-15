"""Registro concurrente de resultados (S8-B1, US-169; S8-D36, M-6; revisión de A4, M-2 y M-3).

Dos conexiones reales con commit. Orden único de candados: socio, sesión (`FOR SHARE`), WOD
(`FOR SHARE`), resultado (`FOR UPDATE`).
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.errors import DomainError
from app.modules.classes import service as classes_service
from app.modules.classes.exceptions import LockedByResults
from app.modules.classes.schemas import SessionPatch
from app.modules.results import record
from app.modules.results.exceptions import ResultExists
from app.modules.wods import service as wods_service
from app.modules.wods.schemas import WodPatch
from tests.factories.wods import make_movement, make_wod
from tests.results._apoyo import Escena, escena, registrar
from tests.results.test_locked_by_results import Pausa, _registrar_pausado

pytestmark = pytest.mark.usefixtures("reloj", "bus_confirmado")


async def _registrar_y_confirmar(session: AsyncSession, e: Escena, **cambios: Any) -> Any:
    try:
        salida = await registrar(session, e, **cambios)
        await session.commit()
        return salida
    except BaseException:
        await session.rollback()
        raise


async def _otro_wod(session: AsyncSession, e: Escena) -> UUID:
    mov = await make_movement(session, e.coach, name="Mov otro wod", unit="kg")
    return (await make_wod(session, e.coach, [mov.id], date="2026-10-19")).id


async def test_reasignar_wod_y_registrar_a_la_vez_no_deja_resultado_de_otro_wod(
    dos_sesiones: tuple[AsyncSession, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """M-6 (y M-1 de la revisión de B1): el registro toma la sesión `FOR SHARE` por sí mismo
    (`session_for_result`); se pausa dentro de `scoring_for`, ya con la sesión tomada. El `PATCH`
    pide `FOR UPDATE` y espera; cuando el resultado confirma ve resultados vigentes y da 409
    (M-2): el resultado queda con el WOD que la clase tenía."""
    una, otra = dos_sesiones
    e = await escena(una)
    assert e.clase is not None
    nuevo = await _otro_wod(una, e)
    pausa = Pausa(monkeypatch)
    registro = await _registrar_pausado(una, e, pausa)

    async def reasignar() -> Any:
        datos = SessionPatch.model_validate({"wod_id": nuevo})
        try:
            with actor_scope(e.coach):
                return await classes_service.assign_wod(otra, e.clase.id, datos, by=e.coach)  # type: ignore[union-attr]
        finally:
            await otra.rollback()

    tarea = asyncio.create_task(reasignar())
    await asyncio.sleep(0.5)
    assert not tarea.done(), "el PATCH debe esperar al FOR SHARE que toma el registro"
    pausa.seguir.set()
    salida = await asyncio.wait_for(registro, timeout=30)
    with pytest.raises(LockedByResults):
        await asyncio.wait_for(tarea, timeout=30)
    assert salida.wod_id == e.wod_id
    asignado = await una.scalar(
        text("SELECT wod_id FROM classes.class_sessions WHERE id = :s"), {"s": e.clase.id}
    )
    assert asignado is None


async def test_registrar_despues_de_reasignar_da_422_session_id(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    una, otra = dos_sesiones
    e = await escena(una)
    assert e.clase is not None
    nuevo = await _otro_wod(una, e)
    with actor_scope(e.coach):
        datos = SessionPatch.model_validate({"wod_id": nuevo})
        await classes_service.assign_wod(otra, e.clase.id, datos, by=e.coach)
        await otra.commit()
    with pytest.raises(DomainError) as info:
        await registrar(una, e)
    assert (info.value.status, info.value.field) == (422, "session_id")


async def test_doble_registro_simultaneo_uno_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """L-4: el primer registro se pausa con el candado del socio tomado; el segundo ESPERA (sin
    `lock_member` ni `FOR UPDATE` correría en paralelo) y al confirmar el primero recibe 409."""
    una, otra = dos_sesiones
    e = await escena(una)
    pausa = Pausa(monkeypatch)
    primero = await _registrar_pausado(una, e, pausa, seconds=300)
    segundo = asyncio.create_task(_registrar_y_confirmar(otra, e, seconds=290))
    await asyncio.sleep(0.5)
    assert not segundo.done(), "el segundo registro debe esperar al candado del socio"
    pausa.seguir.set()
    await asyncio.wait_for(primero, timeout=30)
    with pytest.raises(ResultExists):
        await asyncio.wait_for(segundo, timeout=30)
    vigentes = await una.scalar(text("SELECT count(*) FROM results.wod_results WHERE is_current"))
    assert vigentes == 1


async def test_23505_traducido(
    dos_sesiones: tuple[AsyncSession, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si no se viera el vigente, el único parcial lo decide: 409 y sesión usable."""
    una, _otra = dos_sesiones
    e = await escena(una)
    primero = await _registrar_y_confirmar(una, e)

    async def ciego(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(record, "_current", ciego)
    with pytest.raises(ResultExists) as info:
        await registrar(una, e, seconds=200)
    assert info.value.existing_id == primero.id
    await una.rollback()
    assert await una.scalar(text("SELECT 1")) == 1


async def test_el_wod_cambia_de_fecha_entre_la_lectura_de_la_sesion_y_su_candado(
    dos_sesiones: tuple[AsyncSession, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """M-3 de la revisión de A4: el WOD heredado se lee sin candado; si su fecha cambia antes del
    `FOR SHARE`, se recomprueba y da 422 `field = "session_id"`."""
    una, otra = dos_sesiones
    e = await escena(una)
    original = wods_service.scoring_for

    async def con_cambio(sesion: AsyncSession, wod_id: UUID) -> Any:
        with actor_scope(e.coach):
            await wods_service.update_wod(
                otra, wod_id, WodPatch.model_validate({"date": date(2026, 10, 18)}), e.coach
            )
            await otra.commit()
        return await original(sesion, wod_id)

    monkeypatch.setattr(wods_service, "scoring_for", con_cambio)
    with pytest.raises(DomainError) as info:
        await registrar(una, e)
    assert (info.value.status, info.value.field) == (422, "session_id")
