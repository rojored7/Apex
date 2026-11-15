"""Corrección concurrente de resultados (S8-B2, US-170, Q18; S8-D11, S8-D36). Dos conexiones."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.modules.results import record
from app.modules.results.models import WodResult
from tests.results._apoyo import Escena, escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_confirmado")


async def _registrar_y_confirmar(session: AsyncSession, e: Escena, **cambios: Any) -> Any:
    try:
        salida = await registrar(session, e, **cambios)
        await session.commit()
        return salida
    except BaseException:
        await session.rollback()
        raise


async def test_dos_coaches_a_la_vez_uno_gana_otro_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    una, otra = dos_sesiones
    e = await escena(una)
    primero = await _registrar_y_confirmar(una, e, seconds=300)
    resultados = await asyncio.wait_for(
        asyncio.gather(
            _registrar_y_confirmar(una, e, seconds=280, supersedes_id=primero.id),
            _registrar_y_confirmar(otra, e, seconds=270, supersedes_id=primero.id),
            return_exceptions=True,
        ),
        timeout=30,
    )
    errores = [r for r in resultados if isinstance(r, DomainError)]
    assert len(errores) == 1 and (errores[0].status, errores[0].code) == (409, "invalid_supersedes")
    assert sum(1 for r in resultados if not isinstance(r, BaseException)) == 1
    cuenta = await una.scalar(
        text("SELECT count(*) FROM results.wod_results WHERE wod_id = :w"), {"w": e.wod_id}
    )
    vigentes = await una.scalar(text("SELECT count(*) FROM results.wod_results WHERE is_current"))
    assert (cuenta, vigentes) == (2, 1)


async def test_23505_del_indice_de_supersedes_traducido(
    dos_sesiones: tuple[AsyncSession, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si el vigente no se viera, el único de `supersedes_id` rechaza al segundo sucesor del mismo
    resultado: 409 `invalid_supersedes` (nunca 500) y la sesión sigue usable."""
    una, _otra = dos_sesiones
    e = await escena(una)
    a = await _registrar_y_confirmar(una, e, seconds=300)
    b = await _registrar_y_confirmar(una, e, seconds=290, supersedes_id=a.id)
    # `b` se apaga (dentro de la transacción de la prueba) para que solo el único de
    # `supersedes_id` pueda rechazar un segundo sucesor de `a`, no el del vigente.
    await una.execute(update(WodResult).where(WodResult.id == b.id).values(is_current=False))
    await una.flush()
    vieja = await una.get(WodResult, a.id)

    async def ciego(*_a: Any, **_k: Any) -> WodResult | None:
        return vieja

    monkeypatch.setattr(record, "_current", ciego)
    with pytest.raises(DomainError) as info:
        await registrar(una, e, seconds=250, supersedes_id=a.id)
    assert (info.value.status, info.value.code) == (409, "invalid_supersedes")
    await una.rollback()
    assert await una.scalar(text("SELECT 1")) == 1
