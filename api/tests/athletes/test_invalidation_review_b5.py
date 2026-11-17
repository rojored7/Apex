"""Revisiones de S9-B5 (seguridad y base de datos): lo que el Verde dejó sin fijar.

- L5 bd = L1 seg: `_invalidate` solo toca los récords del SOCIO del evento.
- L5 seg: la reposición tras invalidar un manual falla en blando (200, alerta sin ids, log
  «reposición omitida» sin la clave `result_id`) y la base ocupada sale como error de «ocupado».
- L2: `result_ids_with_record` manda UN solo parámetro de arreglo (`= ANY(:ids)`), no uno por id.
- L7 bd: presupuesto de sentencias de una corrección con RM y benchmark a la vez (dos objetivos).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import actor_scope
from app.modules.athletes import derive, service
from app.modules.athletes.records import result_ids_with_record
from app.modules.results import service as results_service
from tests.athletes._apoyo import alta_record, cuerpo_rm
from tests.athletes._apoyo_derivar import AlertasCapturadas, contar_sentencias, records_de
from tests.athletes._apoyo_invalidar import cargar, escena_serie, por_resultado, vivos, wod_en
from tests.factories.athletes import make_record
from tests.factories.explain import capturar_sql
from tests.factories.wods import make_benchmark
from tests.results._apoyo import Escena

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


@pytest.fixture
async def e(session: AsyncSession) -> Escena:
    return await escena_serie(session, "2026-10-12")


async def _roto(*_a: Any, **_k: Any) -> Any:
    raise RuntimeError("fallo forzado")


# L5 bd = L1 seg: el filtro por socio ----------------------------------------------------------


async def test_invalidate_solo_toca_los_records_del_socio_del_evento(
    session: AsyncSession, e: Escena
) -> None:
    ajeno = await make_record(session, kind="rm", source="derived", value_g=90_000)
    assert ajeno.result_id is not None
    ajeno_id, result_id = ajeno.id, ajeno.result_id

    with actor_scope(e.coach):
        tocados = await derive._invalidate(
            session,
            member_id=e.socio_id,  # no es el dueño del récord
            result_id=result_id,
            reason="voided",
            by_result=None,
        )

    assert tocados == []
    filas = await session.execute(
        text("SELECT invalidated_at FROM athletes.personal_records WHERE id = :i"),
        {"i": ajeno_id},
    )
    assert filas.scalar_one() is None


async def test_invalidate_del_socio_correcto_si_invalida(session: AsyncSession, e: Escena) -> None:
    r = await cargar(session, e, e.wod_id, 100_000)

    with actor_scope(e.coach):
        tocados = await derive._invalidate(
            session, member_id=e.socio_id, result_id=r.id, reason="voided", by_result=None
        )

    assert len(tocados) == 1


# L5 seg: la reposición de la ruta manual ------------------------------------------------------


async def _escena_manual(session: AsyncSession, e: Escena) -> Any:
    """Un manual de 100 kg que tapa un resultado de 60 kg (sin récord): invalidarlo repone el 60."""
    manual = await alta_record(
        session, e.coach, e.socio_id, cuerpo_rm(e.movimientos[0], value_g=100_000)
    )
    await cargar(session, e, e.wod_id, 60_000)
    await session.commit()
    return manual.id


async def test_un_fallo_al_reponer_tras_invalidar_un_manual_es_blando(
    session: AsyncSession,
    e: Escena,
    alertas: AlertasCapturadas,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manual_id = await _escena_manual(session, e)
    monkeypatch.setattr(results_service, "member_marks", _roto)

    with actor_scope(e.coach), caplog.at_level(logging.INFO):
        salida = await service.invalidate_manual_record(
            session, e.socio_id, manual_id, by=e.coach, role="admin"
        )

    assert salida.invalidated_reason == "manual_error"
    filas = await records_de(session, e.socio_id)
    assert por_resultado_manual(filas, manual_id)["invalidated_reason"] == "manual_error"
    assert vivos(filas) == [], "no se repuso el de 60"
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "RuntimeError"}]
    registros = [r for r in caplog.records if "omitida" in r.getMessage()]
    assert registros, "debe quedar un log de la reposición omitida"
    assert all("reposición omitida" in r.getMessage() for r in registros)
    assert all(not hasattr(r, "result_id") for r in registros), "sin result_id: no hay resultado"
    assert all(str(e.socio_id) in str(r.__dict__.get("member_id")) for r in registros)


def por_resultado_manual(filas: list[dict[str, Any]], record_id: Any) -> dict[str, Any]:
    return next(f for f in filas if f["id"] == record_id)


async def test_un_fallo_al_reponer_tras_un_resultado_sigue_diciendo_derivacion_omitida(
    session: AsyncSession,
    e: Escena,
    caplog: pytest.LogCaptureFixture,
    alertas: AlertasCapturadas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El mensaje de la vía de resultados no cambia."""
    malo = await cargar(session, e, e.wod_id, 1_000_000)
    c = await wod_en(session, e, "2026-10-13", "C")
    await cargar(session, e, c, 95_000)
    monkeypatch.setattr(results_service, "member_marks", _roto)

    with caplog.at_level(logging.INFO):
        await cargar(session, e, e.wod_id, 92_000, anterior_id=malo.id)

    assert any("derivación omitida" in r.getMessage() for r in caplog.records)
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "RuntimeError"}]


# L2 bd: un solo parámetro de arreglo ----------------------------------------------------------


async def test_result_ids_with_record_manda_un_solo_parametro_de_arreglo(
    session: AsyncSession, e: Escena
) -> None:
    pocos = [uuid4() for _ in range(2)]
    muchos = [uuid4() for _ in range(60)]

    with capturar_sql(session, "athletes.personal_records") as vistas:
        await result_ids_with_record(session, e.socio_id, "rm", pocos)
        await result_ids_with_record(session, e.socio_id, "rm", muchos)

    (sql_a, par_a), (sql_b, par_b) = vistas
    assert "ANY" in sql_a.upper() and "ANY" in sql_b.upper()
    assert len(tuple(par_a)) == len(tuple(par_b)), "los parámetros no crecen con los ids"
    assert any(isinstance(p, list | tuple) and len(p) == 60 for p in tuple(par_b))


# L7 bd: presupuesto con dos objetivos ---------------------------------------------------------

PRESUPUESTO_DOS_OBJETIVOS = 19  # medido: 12 con un objetivo + 7 del segundo (S9-D60)


async def _hueco_con_benchmark(session: AsyncSession, dias: tuple[str, str, str]) -> Any:
    """90 kg, 1.000 kg erróneo (RM y benchmark `load` a la vez) y 95 kg (también benchmark)."""
    e = await escena_serie(session, dias[0])
    bm = await make_benchmark(session, e.coach, name=f"Carga {dias[0]}", score_type="load")
    await cargar(session, e, e.wod_id, 90_000)
    w_b = await wod_en(session, e, dias[1], f"B {dias[1]}", benchmark_id=bm.id)
    malo = await cargar(session, e, w_b, 1_000_000)
    w_c = await wod_en(session, e, dias[2], f"C {dias[2]}", benchmark_id=bm.id)
    await cargar(session, e, w_c, 95_000)
    return e, w_b, malo


async def test_presupuesto_de_una_correccion_con_rm_y_benchmark_a_la_vez(
    session: AsyncSession,
) -> None:
    """El tope de S9-D30 (12) vale por OBJETIVO; con dos objetivos se fija el número medido."""
    tablas = ("athletes.", "results.", "wods.")
    con, w_con, malo_con = await _hueco_con_benchmark(
        session, ("2026-10-01", "2026-10-02", "2026-10-03")
    )
    sin, w_sin, malo_sin = await _hueco_con_benchmark(
        session, ("2026-10-05", "2026-10-06", "2026-10-07")
    )

    with contar_sentencias(session, tablas) as vistas_con:
        await cargar(session, con, w_con, 92_000, anterior_id=malo_con.id)
    for handlers in list(events._subscribers.values()):
        for h in list(handlers):
            if getattr(h, "__module__", "") == "app.modules.athletes.derive":
                handlers.remove(h)
    with contar_sentencias(session, tablas) as vistas_sin:
        await cargar(session, sin, w_sin, 92_000, anterior_id=malo_sin.id)

    filas = await records_de(session, con.socio_id)
    assert len([f for f in filas if f["kind"] == "benchmark" and f["invalidated_at"] is None]) == 2
    assert por_resultado(filas, malo_con.id)["invalidated_reason"] == "superseded"
    assert len(vistas_con) - len(vistas_sin) == PRESUPUESTO_DOS_OBJETIVOS
