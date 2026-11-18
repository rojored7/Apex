"""`rederive_member` (S9-B6; S9-D62 A): calcula los borradores del socio EN MEMORIA y escribe con
UN solo `add_all` + `flush`; las sentencias por socio no crecen con las marcas (sin N+1)."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.athletes import derive
from app.modules.athletes import service as athletes_service
from app.modules.results.events import WodResultValidated
from app.modules.wods import service as wods_service
from tests.athletes._apoyo_derivar import AlertasCapturadas, alertas, contar_sentencias, records_de  # noqa: F401
from tests.athletes._apoyo_invalidar import cargar, escena_serie, wod_en

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def _sin_records(session: AsyncSession, kgs: list[int], mes: str = "10") -> Any:
    handlers = events._subscribers.get(WodResultValidated, [])
    quitados = [h for h in handlers if h is derive.on_wod_result_validated]
    for h in quitados:
        handlers.remove(h)
    try:
        e = await escena_serie(session, f"2026-{mes}-01")
        for i, kg in enumerate(kgs):
            dia = f"2026-{mes}-{1 + i:02d}"
            wod = e.wod_id if i == 0 else await wod_en(session, e, dia, f"W{i}")
            await cargar(session, e, wod, kg * 1000)
    finally:
        handlers.extend(quitados)
    return e


async def _sentencias(session: AsyncSession, e: Any) -> list[str]:
    with actor_scope(SYSTEM_USER_ID), contar_sentencias(session, ("SELECT", "INSERT")) as vistas:
        await athletes_service.rederive_member(session, e.socio_id)
    return list(vistas)


async def test_las_sentencias_no_crecen_con_las_marcas_que_no_superan(
    session: AsyncSession,
) -> None:
    corta = await _sin_records(session, [100, 90, 80])
    larga = await _sin_records(session, [100, 90, 80, 70, 60, 50, 40], "09")
    assert len(await _sentencias(session, corta)) == len(await _sentencias(session, larga))
    assert len(await records_de(session, corta.socio_id)) == 1


async def test_un_solo_flush_por_socio_aunque_cree_varios_records(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = await _sin_records(session, [100, 110, 120])
    original = session.flush
    llamadas: list[int] = []

    async def contar(*a: Any, **k: Any) -> None:
        llamadas.append(1)
        await original(*a, **k)

    monkeypatch.setattr(session, "flush", contar)
    with actor_scope(SYSTEM_USER_ID):
        r = await athletes_service.rederive_member(session, e.socio_id)
    assert r.created == 3
    assert len(llamadas) == 1


async def test_la_reposicion_en_vivo_avisa_si_los_wods_del_movimiento_se_recortan(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    alertas: AlertasCapturadas,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    """S9-D62 B: `WOD_IDS_MAX` recortó la lista: alerta sin ids y línea de log con el socio."""
    e = await _sin_records(session, [100, 110])
    monkeypatch.setattr(wods_service, "WOD_IDS_MAX", 1)
    with actor_scope(SYSTEM_USER_ID), caplog.at_level(logging.WARNING):
        await derive.restore_after_manual(
            session, e.socio_id, kind="rm", target_id=e.movimientos[0]
        )
    assert alertas.de("athletes_restore_capped") == [{"marcas": 2}]
    assert any(getattr(r, "member_id", None) == str(e.socio_id) for r in caplog.records)
    assert "derive-records" in caplog.text
