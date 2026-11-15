"""Anulación de resultados con dos conexiones (S8-B3b, S8-D46 b). Commit real (`bus_confirmado`).

La anulación toma el candado del socio como el registro: espera a una corrección en vuelo y luego
ve el resultado ya corregido (409 `result_not_voidable`); dos anulaciones a la vez dejan una sola.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.errors import DomainError
from app.modules.results import service
from app.modules.results.schemas import VoidIn
from tests.results._apoyo import Escena, escena, registrar
from tests.results.test_locked_by_results import Pausa

pytestmark = pytest.mark.usefixtures("reloj", "bus_confirmado")

MOTIVO = "Se registró en el socio equivocado"


async def _anular(session: AsyncSession, e: Escena, result_id: UUID) -> Any:
    with actor_scope(e.coach):
        return await service.void_result(session, result_id, VoidIn(reason=MOTIVO), by=e.coach)


async def test_anular_espera_a_una_correccion_en_vuelo_y_da_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """La corrección toma el candado del socio y se pausa; la anulación espera y, al seguir,
    ve el resultado ya corregido: 409 `result_not_voidable`, nunca dos filas vigentes."""
    una, otra = dos_sesiones
    e = await escena(una)
    uno = await registrar(una, e, seconds=300)
    await una.commit()
    pausa = Pausa(monkeypatch)

    async def corregir() -> Any:
        try:
            salida = await registrar(una, e, seconds=280, supersedes_id=uno.id)
            await una.commit()
            return salida
        except BaseException:
            await una.rollback()
            raise

    registro = asyncio.create_task(corregir())
    await asyncio.wait_for(pausa.dentro.wait(), timeout=15)

    async def anular() -> None:
        try:
            await _anular(otra, e, uno.id)
        finally:
            await otra.rollback()

    contraria = asyncio.create_task(anular())
    try:
        await asyncio.sleep(0.5)
        assert not contraria.done(), "la anulación debe esperar a la corrección en vuelo"
    finally:
        pausa.seguir.set()  # nunca dejar el candado tomado: el cierre de la prueba lo necesita
        await asyncio.wait_for(registro, timeout=30)
        resultado = (await asyncio.gather(contraria, return_exceptions=True))[0]
    assert isinstance(resultado, DomainError)
    assert (resultado.status, resultado.code) == (409, "result_not_voidable")
    vigentes = await una.scalar(text("SELECT count(*) FROM results.wod_results WHERE is_current"))
    anulados = await una.scalar(
        text("SELECT count(*) FROM results.wod_results WHERE status = 'voided'")
    )
    assert (vigentes, anulados) == (1, 0)


async def test_dos_admins_anulan_a_la_vez_uno_gana_otro_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    una, otra = dos_sesiones
    e = await escena(una)
    uno = await registrar(una, e)
    await una.commit()

    async def anular(sesion: AsyncSession) -> Any:
        try:
            salida = await _anular(sesion, e, uno.id)
            await sesion.commit()
            return salida
        except BaseException:
            await sesion.rollback()
            raise

    resultados = await asyncio.wait_for(
        asyncio.gather(anular(una), anular(otra), return_exceptions=True), timeout=30
    )
    errores = [r for r in resultados if isinstance(r, DomainError)]
    assert len(errores) == 1 and errores[0].code == "result_already_voided"
    assert sum(1 for r in resultados if not isinstance(r, BaseException)) == 1
