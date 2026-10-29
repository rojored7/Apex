"""`worker/runner.py` contra la base real (US-113; S4A-D6, S4A-D7, S4A-D48, S4A-D55).

Reloj `reloj_worker` (`2026-10-21T15:00Z`, 10:00 de Bogotá, ya pasadas las 07:00). Dos jobs de
prueba (`tests/worker/conftest.py`): `prueba_escribe` da de alta un plan por el service real;
`prueba_lanza` da de alta otro dentro de su transacción y lanza
`RuntimeError("documento 1020304417 en el mensaje")` antes de confirmar.
- `run_cycle` corre el segundo job aunque el primero lance; la escritura del que lanza se revierte;
  `job_runs` queda con `error` (`RuntimeError`, sin el mensaje) y `ok`; `alert("job_failed", ...)`
  recibe solo claves de `ALERT_CONTEXT_KEYS`; ni el log ni stdout llevan el documento.
- `timeout_s=1` con un job que duerme 3 s: `error="TimeoutError"` y la fila no queda `running`.
- Las escrituras del job llevan `SYSTEM_USER_ID` y un lote (`batch_scope`) fijado; el reclamo
  también (S4A-D55 a), aunque quien llama no fije actor.
- `simulated=True` reclama `<job>_sim` con `details["clock_override"] = True`.
- Reinicio a las 09:00 de Bogotá (14:00Z): con el ciclo del día hecho no corre nada; sin él corre
  una sola vez aunque se llame dos veces.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import alerts
from app.core.alerts import ALERT_CONTEXT_KEYS
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, current_actor
from app.core.jobs import JobRun, claim_run
from app.modules.plans.models import Plan
from app.worker import runner
from app.worker.registry import JobSpec
from app.worker.runner import JobContext, JobResult, run_cycle, run_job
from tests.factories.job_runs import make_job_run
from tests.worker.conftest import (
    DOCUMENTO,
    PLAN_DEL_JOB,
    PLAN_REVERTIDO,
    SpecObservado,
)

Fabrica = async_sessionmaker[AsyncSession]
DIA = date(2026, 10, 21)
NUEVE_BOGOTA = datetime(2026, 10, 21, 14, 0, tzinfo=UTC)


class SinkEspia:
    def __init__(self) -> None:
        self.recibidas: list[tuple[str, dict[str, object]]] = []

    def send(self, code: str, context: Mapping[str, object]) -> None:
        self.recibidas.append((code, dict(context)))


@pytest.fixture
def sink_espia() -> Iterator[SinkEspia]:
    """Un sink espía en lugar de los del proceso; al salir se restaura la lista."""
    foto = list(alerts._sinks)
    espia = SinkEspia()
    alerts._sinks[:] = [espia]
    try:
        yield espia
    finally:
        alerts._sinks[:] = foto


async def _corridas(fabrica: Fabrica) -> dict[str, JobRun]:
    async with fabrica() as sesion:
        return {f.job_name: f for f in (await sesion.scalars(select(JobRun))).all()}


async def _planes(fabrica: Fabrica) -> list[Plan]:
    async with fabrica() as sesion:
        return list((await sesion.scalars(select(Plan))).all())


def _texto_de_registros(caplog: pytest.LogCaptureFixture) -> str:
    formato = logging.Formatter("%(name)s %(levelname)s %(message)s")
    return "\n".join(
        formato.format(r) + " " + str({k: v for k, v in vars(r).items() if k != "msg"})
        for r in caplog.records
    )


# Un job que falla no detiene a los demás ------------------------------------------------------


async def test_el_segundo_job_corre_aunque_el_primero_lance(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_lanza: SpecObservado,
    spec_que_escribe: SpecObservado,
    sink_espia: SinkEspia,
) -> None:
    resultados = await run_cycle(
        (spec_que_lanza.spec, spec_que_escribe.spec),
        clock=reloj_worker,
        session_factory=session_factory,
    )

    assert [(r.job_name, r.result) for r in resultados] == [
        ("prueba_lanza", "error"),
        ("prueba_escribe", "ok"),
    ]
    assert resultados[0].error_type == "RuntimeError"
    assert all(r.run_date == DIA for r in resultados)
    nombres = [p.name for p in await _planes(session_factory)]
    assert nombres == [PLAN_DEL_JOB]
    assert PLAN_REVERTIDO not in nombres


async def test_job_runs_queda_con_error_sin_mensaje_y_ok(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_lanza: SpecObservado,
    spec_que_escribe: SpecObservado,
    sink_espia: SinkEspia,
) -> None:
    await run_cycle(
        (spec_que_lanza.spec, spec_que_escribe.spec),
        clock=reloj_worker,
        session_factory=session_factory,
    )

    corridas = await _corridas(session_factory)
    assert set(corridas) == {"prueba_lanza", "prueba_escribe"}
    fallida, buena = corridas["prueba_lanza"], corridas["prueba_escribe"]
    assert (fallida.result, fallida.error) == ("error", "RuntimeError")
    assert (buena.result, buena.error) == ("ok", None)
    assert buena.details["revisados"] == 1
    for fila in corridas.values():
        assert fila.run_date == DIA and fila.finished_at is not None
        assert fila.created_by == SYSTEM_USER_ID
        assert DOCUMENTO not in str(fila.details) and DOCUMENTO not in (fila.error or "")


async def test_el_fallo_avisa_con_job_failed_y_contexto_cerrado(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_lanza: SpecObservado,
    sink_espia: SinkEspia,
) -> None:
    await run_job(spec_que_lanza.spec, clock=reloj_worker, session_factory=session_factory)

    assert len(sink_espia.recibidas) == 1
    codigo, contexto = sink_espia.recibidas[0]
    assert codigo == "job_failed"
    assert set(contexto) <= ALERT_CONTEXT_KEYS
    assert contexto["job"] == "prueba_lanza"
    assert contexto["result"] == "error"
    assert contexto["error_type"] == "RuntimeError"
    assert DOCUMENTO not in str(contexto)


async def test_un_job_que_va_bien_no_avisa(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_escribe: SpecObservado,
    sink_espia: SinkEspia,
) -> None:
    resultado = await run_job(
        spec_que_escribe.spec, clock=reloj_worker, session_factory=session_factory
    )
    assert (resultado.result, resultado.error_type) == ("ok", None)
    assert resultado.details.get("revisados") == 1
    assert sink_espia.recibidas == []


async def test_ni_el_log_ni_stdout_llevan_el_documento(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_lanza: SpecObservado,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caplog.set_level(logging.DEBUG)

    await run_job(spec_que_lanza.spec, clock=reloj_worker, session_factory=session_factory)

    salida = capsys.readouterr()
    assert DOCUMENTO not in salida.out and DOCUMENTO not in salida.err
    assert DOCUMENTO not in _texto_de_registros(caplog)
    assert any(r.levelno >= logging.ERROR for r in caplog.records), "el fallo no quedó en el log"


# Tiempo máximo ----------------------------------------------------------------------------------


async def test_timeout_marca_error_y_no_deja_running(
    session_factory: Fabrica, reloj_worker: FrozenClock, sink_espia: SinkEspia
) -> None:
    async def lento(ctx: JobContext) -> JobResult:
        await asyncio.sleep(3)
        return JobResult(ok=True)  # pragma: no cover - el tiempo máximo corta antes

    spec = JobSpec(name="prueba_lenta", run=lento, hour=7, minute=0, timeout_s=1)
    bucle = asyncio.get_running_loop()
    inicio = bucle.time()

    resultado = await run_job(spec, clock=reloj_worker, session_factory=session_factory)

    assert bucle.time() - inicio < 2.5
    assert (resultado.result, resultado.error_type) == ("error", "TimeoutError")
    fila = (await _corridas(session_factory))["prueba_lenta"]
    assert (fila.result, fila.error) == ("error", "TimeoutError")
    assert fila.finished_at is not None
    assert sink_espia.recibidas[0][1]["error_type"] == "TimeoutError"


# Actor y lote -----------------------------------------------------------------------------------


async def test_el_job_escribe_como_usuario_del_sistema_con_lote(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_escribe: SpecObservado,
) -> None:
    assert current_actor.get() is None

    await run_job(spec_que_escribe.spec, clock=reloj_worker, session_factory=session_factory)

    assert spec_que_escribe.actores == [SYSTEM_USER_ID]
    assert spec_que_escribe.lotes[0] is not None
    assert [p.created_by for p in await _planes(session_factory)] == [SYSTEM_USER_ID]
    assert (await _corridas(session_factory))["prueba_escribe"].created_by == SYSTEM_USER_ID
    assert current_actor.get() is None


async def test_el_contexto_del_job_trae_el_hoy_de_bogota_y_el_reloj(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_escribe: SpecObservado,
) -> None:
    await run_job(spec_que_escribe.spec, clock=reloj_worker, session_factory=session_factory)

    ctx = spec_que_escribe.contextos[0]
    assert ctx.today == DIA
    assert ctx.clock is reloj_worker
    assert ctx.simulated is False


# Corrida simulada -------------------------------------------------------------------------------


async def test_simulada_reclama_el_nombre_sim_y_marca_clock_override(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_escribe: SpecObservado,
) -> None:
    resultado = await run_job(
        spec_que_escribe.spec,
        clock=reloj_worker,
        session_factory=session_factory,
        simulated=True,
    )

    assert resultado.job_name == "prueba_escribe_sim"
    corridas = await _corridas(session_factory)
    assert set(corridas) == {"prueba_escribe_sim"}
    assert corridas["prueba_escribe_sim"].details["clock_override"] is True
    assert spec_que_escribe.contextos[0].simulated is True


# Recuperación al reiniciar ----------------------------------------------------------------------


async def test_reinicio_a_las_nueve_con_el_ciclo_hecho_no_corre_nada(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_escribe: SpecObservado,
) -> None:
    reloj_worker.set(NUEVE_BOGOTA)
    async with session_factory() as sesion:
        await make_job_run(
            sesion, "prueba_escribe", DIA, started_at=datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
        )

    resultados = await run_cycle(
        (spec_que_escribe.spec,), clock=reloj_worker, session_factory=session_factory
    )

    assert resultados == []
    assert spec_que_escribe.actores == []
    assert await _planes(session_factory) == []


async def test_reinicio_a_las_nueve_sin_ciclo_corre_una_sola_vez(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_escribe: SpecObservado,
) -> None:
    reloj_worker.set(NUEVE_BOGOTA)

    primera = await run_cycle(
        (spec_que_escribe.spec,), clock=reloj_worker, session_factory=session_factory
    )
    segunda = await run_cycle(
        (spec_que_escribe.spec,), clock=reloj_worker, session_factory=session_factory
    )

    assert [(r.job_name, r.result) for r in primera] == [("prueba_escribe", "ok")]
    assert segunda == []
    assert len(spec_que_escribe.actores) == 1
    assert len(await _planes(session_factory)) == 1


async def test_antes_de_las_siete_el_ciclo_no_corre(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_escribe: SpecObservado,
) -> None:
    reloj_worker.set(datetime(2026, 10, 21, 11, 59, tzinfo=UTC))  # 06:59 de Bogotá

    resultados = await run_cycle(
        (spec_que_escribe.spec,), clock=reloj_worker, session_factory=session_factory
    )

    assert resultados == []
    assert await _corridas(session_factory) == {}


# Bordes: lo que devuelve el job y la base que falla en el ciclo ---------------------------------


async def test_details_fuera_del_contrato_cuentan_como_error_sin_guardarlos(
    session_factory: Fabrica, reloj_worker: FrozenClock, sink_espia: SinkEspia
) -> None:
    async def con_nombre(ctx: JobContext) -> JobResult:
        return JobResult(ok=True, details={"socio": "Laura"})

    spec = JobSpec(name="prueba_details", run=con_nombre, hour=7, minute=0)

    resultado = await run_job(spec, clock=reloj_worker, session_factory=session_factory)

    assert (resultado.result, resultado.error_type) == ("error", "ValueError")
    fila = (await _corridas(session_factory))["prueba_details"]
    assert (fila.result, fila.error) == ("error", "ValueError")
    assert "socio" not in fila.details and "Laura" not in str(fila.details)
    assert sink_espia.recibidas[0][0] == "job_failed"


async def test_un_job_que_devuelve_ok_falso_queda_en_error_y_avisa(
    session_factory: Fabrica, reloj_worker: FrozenClock, sink_espia: SinkEspia
) -> None:
    async def fallido(ctx: JobContext) -> JobResult:
        return JobResult(ok=False, details={"errores": 2})

    spec = JobSpec(name="prueba_fallida", run=fallido, hour=7, minute=0)

    resultado = await run_job(spec, clock=reloj_worker, session_factory=session_factory)

    assert (resultado.result, resultado.error_type) == ("error", None)
    fila = (await _corridas(session_factory))["prueba_fallida"]
    assert (fila.result, fila.error, fila.details["errores"]) == ("error", None, 2)
    codigo, contexto = sink_espia.recibidas[0]
    assert codigo == "job_failed" and "error_type" not in contexto


async def test_si_la_base_falla_al_leer_un_job_el_ciclo_sigue_con_el_siguiente(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_lanza: SpecObservado,
    spec_que_escribe: SpecObservado,
    sink_espia: SinkEspia,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = runner.last_run

    async def last_run_roto(sesion: AsyncSession, job_name: str) -> object:
        if job_name == "prueba_lanza":
            raise ConnectionError("base caída")
        return await original(sesion, job_name)

    monkeypatch.setattr(runner, "last_run", last_run_roto)

    resultados = await run_cycle(
        (spec_que_lanza.spec, spec_que_escribe.spec),
        clock=reloj_worker,
        session_factory=session_factory,
    )

    assert [(r.job_name, r.result) for r in resultados] == [("prueba_escribe", "ok")]
    assert spec_que_lanza.actores == []
    assert sink_espia.recibidas == [
        ("job_failed", {"job": "prueba_lanza", "result": "error", "error_type": "ConnectionError"})
    ]


# Revisiones de B1 (S4A-D77, S4A-D79, S4A-D81) ---------------------------------------------------


async def test_si_otro_proceso_reclama_la_fila_durante_el_job_el_cierre_es_lost_claim(
    session_factory: Fabrica, reloj_worker: FrozenClock, sink_espia: SinkEspia
) -> None:
    otro_inicio = reloj_worker.now_utc() + timedelta(hours=1)

    async def robado(ctx: JobContext) -> JobResult:
        async with ctx.session_factory() as sesion:
            await claim_run(
                sesion, "prueba_robada", ctx.today, now=otro_inicio, stale_after=timedelta(0)
            )
            await sesion.commit()
        return JobResult(ok=True, details={"revisados": 1})

    spec = JobSpec(name="prueba_robada", run=robado, hour=7, minute=0)

    resultado = await run_job(spec, clock=reloj_worker, session_factory=session_factory)

    assert (resultado.result, resultado.error_type) == ("error", "LostClaim")
    fila = (await _corridas(session_factory))["prueba_robada"]
    assert (fila.result, fila.started_at, fila.error) == ("running", otro_inicio, None)
    assert "revisados" not in fila.details
    assert sink_espia.recibidas[0][1]["error_type"] == "LostClaim"


class _OrigenOcupado(Exception):
    sqlstate = "55P03"


async def test_si_la_base_no_da_el_candado_al_reclamar_no_corre_y_no_falla(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_escribe: SpecObservado,
    sink_espia: SinkEspia,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ocupado(*args: object, **kwargs: object) -> None:
        raise DBAPIError("INSERT", {}, _OrigenOcupado())

    monkeypatch.setattr(runner, "claim_run", ocupado)

    resultado = await run_job(
        spec_que_escribe.spec, clock=reloj_worker, session_factory=session_factory
    )

    assert resultado.result == "running"
    assert spec_que_escribe.actores == [] and sink_espia.recibidas == []


async def test_un_error_de_base_al_reclamar_que_no_es_busy_se_propaga(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_escribe: SpecObservado,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _OrigenRoto(Exception):
        sqlstate = "08006"

    async def roto(*args: object, **kwargs: object) -> None:
        raise DBAPIError("INSERT", {}, _OrigenRoto())

    monkeypatch.setattr(runner, "claim_run", roto)

    with pytest.raises(DBAPIError):
        await run_job(spec_que_escribe.spec, clock=reloj_worker, session_factory=session_factory)


async def test_dos_ciclos_simultaneos_el_mismo_dia_corren_el_job_una_sola_vez(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_escribe: SpecObservado,
) -> None:
    resultados = await asyncio.gather(
        *(
            run_cycle((spec_que_escribe.spec,), clock=reloj_worker, session_factory=session_factory)
            for _ in range(2)
        )
    )

    assert sorted(len(r) for r in resultados) == [0, 1]
    assert len(spec_que_escribe.actores) == 1
    assert len(await _planes(session_factory)) == 1


async def test_el_ciclo_no_repite_un_dia_cerrado_aunque_llegue_tarde(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_escribe: SpecObservado,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `last_run` leído antes del cierre de otro ciclo: el reclamo es lo que impide repetir.
    async with session_factory() as sesion:
        await make_job_run(sesion, "prueba_escribe", DIA)

    async def sin_fila(sesion: AsyncSession, job_name: str) -> None:
        return None

    monkeypatch.setattr(runner, "last_run", sin_fila)

    resultados = await run_cycle(
        (spec_que_escribe.spec,), clock=reloj_worker, session_factory=session_factory
    )

    assert resultados == []
    assert spec_que_escribe.actores == []


async def test_run_job_manual_si_repite_un_dia_cerrado(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_escribe: SpecObservado,
) -> None:
    async with session_factory() as sesion:
        await make_job_run(sesion, "prueba_escribe", DIA)

    resultado = await run_job(
        spec_que_escribe.spec, clock=reloj_worker, session_factory=session_factory
    )

    assert resultado.result == "ok"
    assert len(spec_que_escribe.actores) == 1
