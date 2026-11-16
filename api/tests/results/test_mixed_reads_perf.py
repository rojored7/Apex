"""Rendimiento de las lecturas del Sprint 8 con datos mezclados (V6). Marcada `perf`: no es gate.

Corre aparte: `uv run pytest -m perf tests/results tests/tv -q -s`. Siembra 30 WODs con unos 100
resultados cada uno (rx y scaled, correcciones con `supersedes_id`, anulados), 120 socios con
resultados en muchos WODs, hace `ANALYZE results.wod_results` y mide tras un calentamiento:
(a) el leaderboard de un WOD, (b) los resultados de un socio y (c) la lectura de `/tv/today`.
Imprime el `EXPLAIN (ANALYZE, BUFFERS)` de cada una; (a) y (b) no pueden hacer `Seq Scan` sobre
`wod_results` (usan los indices parciales de `0036`). (c) solo se reporta.
"""

from __future__ import annotations

import re
import time
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.pagination import PageParams
from app.modules.results import service
from app.modules.results.schemas import VoidIn
from app.modules.tv import service as tv_service
from tests.factories.explain import capturar_sql, imprimir_explain
from tests.factories.members import make_members
from tests.factories.results import make_result
from tests.factories.users import make_user
from tests.factories.wods import make_movement, make_wod
from tests.tv._apoyo import CONSENTIDO, HOY, config

pytestmark = [pytest.mark.perf, pytest.mark.usefixtures("reloj", "bus_listo")]

TOPE_MS = 300
WODS = 30
POR_WOD = 100
SOCIOS = 120
SOCIO_CLAVE = 50  # tiene resultado en los 30 WODs (ventana rotativa de 100 sobre 120)
SEQ_SCAN_WOD_RESULTS = re.compile(r"Seq Scan on wod_results")


async def _sembrar(session: AsyncSession) -> tuple[UUID, list[UUID], UUID]:
    """(socio clave, ids de WOD con el de hoy al final, WOD de hoy)."""
    coach = (await make_user(session, role="coach")).id
    mov = await make_movement(session, coach, name=f"Mov {uuid4().hex[:6]}", unit="kg")
    socios = await make_members(session, SOCIOS, data_consent_at=CONSENTIDO)
    hoy = date.fromisoformat(HOY)
    wods: list[UUID] = []
    for w in range(WODS):
        fecha = (hoy - timedelta(days=WODS - 1 - w)).isoformat()
        wod = await make_wod(
            session,
            coach,
            [mov.id],
            date=fecha,
            title=f"WOD {w}",
            score_type="time",
            time_cap_s=600,
        )
        wods.append(wod.id)
        for k in range(POR_WOD):
            socio = socios[(3 * w + k) % SOCIOS]
            nivel = "rx" if (k + w) % 3 else "scaled"
            marca = await make_result(
                session, coach, wod.id, socio.id, seconds=100 + (k * 7 + w) % 400, level=nivel
            )
            if k % 10 == 0:  # correccion: la anterior queda is_current = false
                await make_result(
                    session, coach, wod.id, socio.id, seconds=90 + k, level=nivel,
                    supersedes_id=marca.id,
                )  # fmt: skip
            elif k % 15 == 0:  # anulado
                with actor_scope(coach):
                    await service.void_result(session, marca.id, VoidIn(reason="prueba"), by=coach)
                    await session.commit()
    await session.execute(text("ANALYZE results.wod_results"))
    return socios[SOCIO_CLAVE].id, wods, wods[-1]


async def _medir(
    session: AsyncSession, titulo: str, lectura: Callable[[], Awaitable[Any]]
) -> tuple[float, list[str]]:
    await lectura()  # calentamiento
    inicio = time.perf_counter()
    salida = await lectura()
    ms = (time.perf_counter() - inicio) * 1000
    with capturar_sql(session, "results.wod_results") as capturadas:
        await lectura()
    await imprimir_explain(session, titulo, capturadas)
    conexion = await session.connection()
    planes = []
    for sql, parametros in capturadas:
        res = await conexion.exec_driver_sql("EXPLAIN " + sql, parametros)
        planes.append("\n".join(str(f[0]) for f in res.all()))
    print(f"{titulo}: {ms:.1f} ms")
    assert salida is not None
    return ms, planes


async def test_lecturas_con_datos_mezclados(session: AsyncSession) -> None:
    socio, wods, wod_hoy = await _sembrar(session)
    pagina = PageParams(limit=50)
    medio = wods[WODS // 2]

    async def tablero() -> Any:
        return await service.leaderboard(session, medio, pagina)

    async def del_socio() -> Any:
        return await service.list_member_results(session, socio, PageParams(limit=50))

    async def tv() -> Any:
        return await tv_service.today(session, config())

    ms_a, planes_a = await _medir(session, "leaderboard (30 WODs)", tablero)
    ms_b, planes_b = await _medir(session, "resultados del socio (30 WODs)", del_socio)
    ms_c, _planes_c = await _medir(session, "tv/today (30 WODs)", tv)
    print(f"RESUMEN ms: leaderboard={ms_a:.1f} socio={ms_b:.1f} tv={ms_c:.1f}")
    assert wod_hoy in wods

    assert ms_a < TOPE_MS and ms_b < TOPE_MS and ms_c < TOPE_MS
    for plan in planes_a:
        assert not SEQ_SCAN_WOD_RESULTS.search(plan), f"leaderboard: Seq Scan: {plan}"
    # V6 (corregido, S8-D50): la lectura del socio usa `ix_wod_results_member_date`
    # sin tocar el planificador (el filtro es la columna desnuda `is_current`, no `IS TRUE`).
    for plan in planes_b:
        assert not SEQ_SCAN_WOD_RESULTS.search(plan), f"socio: Seq Scan: {plan}"
        assert "ix_wod_results_member_date" in plan, plan
