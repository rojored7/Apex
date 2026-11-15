"""Rendimiento del leaderboard (S8-B4, US-171 CA8). Marcada `perf`: no es gate (`-m "not perf"`).

Corre aparte: `uv run pytest -m perf tests/results/test_leaderboard_perf.py -q -s`. Siembra los
resultados, hace `ANALYZE results.wod_results` (el plan depende de las estadísticas) y mide la
lectura completa (consulta, nombres y orden) tras un calentamiento. Con `-s` imprime el
`EXPLAIN (ANALYZE, BUFFERS)` de la consulta de resultados.
"""

from __future__ import annotations

import time
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.modules.results import service
from tests.factories.explain import capturar_sql, imprimir_explain
from tests.factories.members import make_members
from tests.factories.results import make_result
from tests.factories.users import make_user
from tests.factories.wods import make_movement, make_wod

pytestmark = [pytest.mark.perf, pytest.mark.usefixtures("reloj", "bus_listo")]

TOPE_MS = 300


@pytest.mark.parametrize("cuantos", [60, 400])
async def test_leaderboard_bajo_300_ms(session: AsyncSession, cuantos: int) -> None:
    coach = (await make_user(session, role="coach")).id
    mov = await make_movement(session, coach, name=f"Mov {uuid4().hex[:6]}", unit="kg")
    wod = (
        await make_wod(
            session, coach, [mov.id], date="2026-10-21", score_type="time", time_cap_s=600
        )
    ).id
    socios = await make_members(session, cuantos)
    for n, socio in enumerate(socios):
        await make_result(
            session,
            coach,
            wod,
            socio.id,
            seconds=100 + (n * 7) % 400,
            level="rx" if n % 3 else "scaled",
        )
    await session.execute(text("ANALYZE results.wod_results"))
    pagina = PageParams(limit=50)
    await service.leaderboard(session, wod, pagina)  # calentamiento
    inicio = time.perf_counter()
    salida = await service.leaderboard(session, wod, pagina)
    ms = (time.perf_counter() - inicio) * 1000
    assert salida.total == cuantos and len(salida.items) == 50
    with capturar_sql(session, "results.wod_results") as capturadas:
        await service.leaderboard(session, wod, pagina)
    await imprimir_explain(session, f"leaderboard {cuantos}", capturadas)
    print(f"leaderboard {cuantos} resultados: {ms:.1f} ms")
    assert ms < TOPE_MS
