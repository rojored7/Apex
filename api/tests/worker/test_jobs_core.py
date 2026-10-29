"""`core/jobs.py` contra la base real (US-113; S4A-D3, S4A-D48, S4A-D55).

Todo con commit real (`session_factory`, y `dos_sesiones` para el reclamo concurrente), bajo
`actor_scope` salvo la prueba de actor ausente. Cada sesión se confirma tras la llamada (si la
función ya confirmó, el segundo commit no cambia nada).
- `claim_run` crea la fila `running` del día con `created_by` = actor y `started_at` = `now`; sin
  actor lanza `MissingActorError` antes de escribir (S4A-D55 a); con un `running` vigente da
  `None`; tras un `ok` el reclamo del mismo día reutiliza la fila; un `running` de más de
  `stale_after` se vuelve a reclamar; dos reclamos simultáneos dejan una sola ejecución.
- `finish_run` guarda el resultado, `finished_at` y el intento en `details["attempts"]` (máximo 20,
  los más recientes); `error` solo es un nombre de tipo y `details` solo claves de `DETAIL_KEYS` con
  enteros (más `clock_override` booleano): si no, `ValueError` y la fila no cambia (S4A-D55 d).
- `last_run` da el último intento por `started_at` del `job_name` exacto.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, MissingActorError, actor_scope
from app.core.jobs import (
    ATTEMPTS_PATH,
    DETAIL_KEYS,
    MAX_ATTEMPTS,
    JobRun,
    JobRunView,
    claim_run,
    finish_run,
    last_run,
)
from tests.factories.job_runs import make_job_run

Fabrica = async_sessionmaker[AsyncSession]
DIA = date(2026, 10, 21)
JOB = "expirations"
CLAVES_INTENTO = {"started_at", "finished_at", "result", "error"}


async def _reclamar(
    fabrica: Fabrica,
    now: datetime,
    *,
    job: str = JOB,
    dia: date = DIA,
    stale_after: timedelta = timedelta(minutes=30),
) -> JobRunView | None:
    async with fabrica() as sesion:
        vista = await claim_run(sesion, job, dia, now=now, stale_after=stale_after)
        await sesion.commit()
    return vista


async def _cerrar_si_es_suyo(
    fabrica: Fabrica,
    reclamo: JobRunView,
    *,
    result: str = "ok",
    error: str | None = None,
    details: dict[str, Any] | None = None,
) -> JobRunView | None:
    async with fabrica() as sesion:
        vista = await finish_run(
            sesion,
            reclamo.id,
            claimed_started_at=reclamo.started_at,
            result=result,
            error=error,
            details=details or {},
        )
        await sesion.commit()
    return vista


async def _cerrar(
    fabrica: Fabrica,
    reclamo: JobRunView,
    *,
    result: str = "ok",
    error: str | None = None,
    details: dict[str, Any] | None = None,
) -> JobRunView:
    vista = await _cerrar_si_es_suyo(fabrica, reclamo, result=result, error=error, details=details)
    assert vista is not None, "el intento reclamado no se cerró"
    return vista


async def _filas(fabrica: Fabrica, job: str = JOB) -> list[JobRun]:
    async with fabrica() as sesion:
        return list((await sesion.scalars(select(JobRun).where(JobRun.job_name == job))).all())


async def _ultimo(fabrica: Fabrica, job: str) -> JobRunView | None:
    async with fabrica() as sesion:
        return await last_run(sesion, job)


# claim_run --------------------------------------------------------------------------------------


async def test_claim_run_crea_la_fila_running_con_el_actor(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    ahora = reloj_worker.now_utc()
    actor = uuid4()
    with actor_scope(actor):
        vista = await _reclamar(session_factory, ahora)

    assert vista is not None
    assert (vista.job_name, vista.run_date, vista.result) == (JOB, DIA, "running")
    assert vista.started_at == ahora and vista.finished_at is None and vista.error is None
    filas = await _filas(session_factory)
    assert len(filas) == 1
    assert filas[0].id == vista.id and filas[0].created_by == actor


async def test_claim_run_con_el_usuario_del_sistema(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        await _reclamar(session_factory, reloj_worker.now_utc())
    assert [f.created_by for f in await _filas(session_factory)] == [SYSTEM_USER_ID]


async def test_claim_run_sin_actor_lanza_antes_de_escribir(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    with pytest.raises(MissingActorError):
        await _reclamar(session_factory, reloj_worker.now_utc())
    assert await _filas(session_factory) == []


async def test_segundo_reclamo_con_running_vigente_da_none(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    ahora = reloj_worker.now_utc()
    with actor_scope(SYSTEM_USER_ID):
        primero = await _reclamar(session_factory, ahora)
        segundo = await _reclamar(session_factory, ahora + timedelta(minutes=10))
    assert primero is not None and segundo is None
    filas = await _filas(session_factory)
    assert len(filas) == 1 and filas[0].started_at == ahora and filas[0].result == "running"


async def test_tras_un_ok_el_reclamo_del_mismo_dia_reutiliza_la_fila(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    ahora = reloj_worker.now_utc()
    with actor_scope(SYSTEM_USER_ID):
        primero = await _reclamar(session_factory, ahora)
        assert primero is not None
        await _cerrar(session_factory, primero, details={"placeholder_ok": 1})
        segundo = await _reclamar(session_factory, ahora + timedelta(hours=1))
        assert segundo is not None
        cerrado = await _cerrar(session_factory, segundo, details={"placeholder_ok": 1})

    assert segundo.id == primero.id
    assert segundo.result == "running" and segundo.finished_at is None
    assert cerrado.result == "ok"
    intentos = cerrado.details["attempts"]
    assert len(intentos) == 2
    assert all(set(i) == CLAVES_INTENTO for i in intentos)
    assert [i["result"] for i in intentos] == ["ok", "ok"]
    assert len(await _filas(session_factory)) == 1


async def test_tras_un_error_el_reclamo_del_mismo_dia_se_permite(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    ahora = reloj_worker.now_utc()
    with actor_scope(SYSTEM_USER_ID):
        primero = await _reclamar(session_factory, ahora)
        assert primero is not None
        await _cerrar(session_factory, primero, result="error", error="RuntimeError")
        segundo = await _reclamar(session_factory, ahora + timedelta(minutes=1))
    assert segundo is not None and segundo.id == primero.id and segundo.error is None


async def test_un_running_viejo_se_vuelve_a_reclamar(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    ahora = reloj_worker.now_utc()
    async with session_factory() as sesion:
        viejo = await make_job_run(
            sesion, JOB, DIA, result="running", started_at=ahora - timedelta(minutes=31)
        )
    with actor_scope(SYSTEM_USER_ID):
        vista = await _reclamar(session_factory, ahora, stale_after=timedelta(minutes=30))
    assert vista is not None and vista.id == viejo.id
    assert vista.started_at == ahora and vista.result == "running"


async def test_un_running_reciente_no_se_reclama_aunque_sea_de_otro_proceso(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    ahora = reloj_worker.now_utc()
    async with session_factory() as sesion:
        await make_job_run(
            sesion, JOB, DIA, result="running", started_at=ahora - timedelta(minutes=29)
        )
    with actor_scope(SYSTEM_USER_ID):
        assert await _reclamar(session_factory, ahora, stale_after=timedelta(minutes=30)) is None


async def test_dos_reclamos_concurrentes_dejan_una_sola_ejecucion(
    dos_sesiones: tuple[AsyncSession, AsyncSession], reloj_worker: FrozenClock
) -> None:
    ahora = reloj_worker.now_utc()

    async def reclamar(sesion: AsyncSession) -> JobRunView | None:
        with actor_scope(SYSTEM_USER_ID):
            vista = await claim_run(sesion, JOB, DIA, now=ahora, stale_after=timedelta(minutes=30))
            await sesion.commit()
        return vista

    resultados = await asyncio.gather(*(reclamar(s) for s in dos_sesiones))

    assert sum(r is not None for r in resultados) == 1
    primera = dos_sesiones[0]
    total = await primera.scalar(
        select(func.count()).select_from(JobRun).where(JobRun.job_name == JOB)
    )
    assert total == 1


# finish_run -------------------------------------------------------------------------------------


async def test_finish_run_con_error_guarda_solo_el_tipo(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        vista = await _reclamar(session_factory, reloj_worker.now_utc())
        assert vista is not None
        cerrado = await _cerrar(
            session_factory, vista, result="error", error="RuntimeError", details={"errores": 1}
        )
    assert (cerrado.result, cerrado.error) == ("error", "RuntimeError")
    assert cerrado.finished_at == reloj_worker.now_utc()
    assert cerrado.details["errores"] == 1
    assert cerrado.details["attempts"][-1]["error"] == "RuntimeError"
    fila = (await _filas(session_factory))[0]
    assert (fila.result, fila.error) == ("error", "RuntimeError")


@pytest.mark.parametrize(
    ("error", "details"),
    [
        ("documento 1020304417", {}),
        ("RuntimeError: documento 1020304417", {}),
        ("Runtime Error", {}),
        (None, {"socio": "Laura"}),
        (None, {"revisados": "3"}),
        (None, {"revisados": 1.5}),
        (None, {"clock_override": "si"}),
        (None, {"attempts": []}),
    ],
    ids=[
        "mensaje_con_documento",
        "tipo_y_mensaje",
        "con_espacio",
        "clave_ajena",
        "valor_texto",
        "valor_decimal",
        "clock_override_no_booleano",
        "attempts_del_llamador",
    ],
)
async def test_finish_run_rechaza_error_o_details_abiertos_sin_escribir(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    error: str | None,
    details: dict[str, Any],
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        vista = await _reclamar(session_factory, reloj_worker.now_utc())
        assert vista is not None
        with pytest.raises(ValueError):
            await _cerrar(session_factory, vista, result="error", error=error, details=details)
    fila = (await _filas(session_factory))[0]
    assert (fila.result, fila.error, fila.finished_at) == ("running", None, None)
    assert "socio" not in fila.details and "attempts" not in fila.details


async def test_finish_run_acepta_todas_las_claves_cerradas_y_clock_override(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    detalles: dict[str, Any] = {clave: 0 for clave in sorted(DETAIL_KEYS)}
    detalles["clock_override"] = True
    with actor_scope(SYSTEM_USER_ID):
        vista = await _reclamar(session_factory, reloj_worker.now_utc())
        assert vista is not None
        cerrado = await _cerrar(session_factory, vista, details=detalles)
    assert {k: v for k, v in cerrado.details.items() if k != "attempts"} == detalles


async def test_detail_keys_es_el_conjunto_cerrado_del_plan() -> None:
    assert (
        frozenset(
            {
                "revisados",
                "cambiadas",
                "por_vencer",
                "vencidas",
                "otras",
                "busy_omitidos",
                "errores",
                "placeholder_ok",
            }
        )
        == DETAIL_KEYS
    )
    assert MAX_ATTEMPTS == 20


async def test_attempts_se_recorta_a_los_20_mas_recientes(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    ahora = reloj_worker.now_utc()
    previos = [
        {
            "started_at": (ahora - timedelta(minutes=30 - i)).isoformat(),
            "finished_at": (ahora - timedelta(minutes=30 - i)).isoformat(),
            "result": "ok",
            "error": None,
        }
        for i in range(MAX_ATTEMPTS)
    ]
    async with session_factory() as sesion:
        await make_job_run(
            sesion, JOB, DIA, started_at=ahora - timedelta(hours=1), details={"attempts": previos}
        )
    with actor_scope(SYSTEM_USER_ID):
        vista = await _reclamar(session_factory, ahora)
        assert vista is not None
        cerrado = await _cerrar(session_factory, vista, result="error", error="TimeoutError")
    intentos = cerrado.details["attempts"]
    assert len(intentos) == MAX_ATTEMPTS
    assert intentos[0] == previos[1]
    assert intentos[-1]["result"] == "error" and intentos[-1]["error"] == "TimeoutError"


# last_run ---------------------------------------------------------------------------------------


async def test_last_run_da_el_ultimo_por_started_at(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    ahora = reloj_worker.now_utc()
    async with session_factory() as sesion:
        await make_job_run(
            sesion, JOB, DIA - timedelta(days=1), started_at=ahora - timedelta(days=1)
        )
        hoy = await make_job_run(sesion, JOB, DIA, result="error", error="RuntimeError")
        await make_job_run(sesion, "otro_job", DIA, started_at=ahora + timedelta(minutes=5))
    ultimo = await _ultimo(session_factory, JOB)
    assert ultimo == hoy


async def test_last_run_sin_corridas_da_none(session_factory: Fabrica) -> None:
    assert await _ultimo(session_factory, JOB) is None


async def test_last_run_del_job_real_ignora_la_simulada(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    ahora = reloj_worker.now_utc()
    async with session_factory() as sesion:
        real = await make_job_run(sesion, JOB, DIA, started_at=ahora - timedelta(hours=2))
        simulada = await make_job_run(
            sesion,
            "expirations_sim",
            date(2026, 11, 1),
            started_at=ahora,
            details={"clock_override": True},
        )
    assert await _ultimo(session_factory, JOB) == real
    assert await _ultimo(session_factory, "expirations_sim") == simulada


# Revisiones de B1: cierre condicionado, rastro de `stale` y reclamo sin repetir (S4A-D77 a D79) --


async def test_el_cierre_de_un_intento_vencido_no_toca_el_que_lo_reemplazo(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    ahora = reloj_worker.now_utc()
    with actor_scope(SYSTEM_USER_ID):
        viejo = await _reclamar(session_factory, ahora)
        nuevo = await _reclamar(session_factory, ahora + timedelta(minutes=31))
        assert viejo is not None and nuevo is not None and nuevo.id == viejo.id
        tardio = await _cerrar_si_es_suyo(session_factory, viejo, result="error", error="X")

    assert tardio is None
    fila = (await _filas(session_factory))[0]
    assert (fila.result, fila.started_at, fila.error) == ("running", nuevo.started_at, None)
    assert [i["result"] for i in fila.details["attempts"]] == ["stale"]


async def test_un_reclamo_por_vencido_deja_el_rastro_stale(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    ahora = reloj_worker.now_utc()
    inicio_viejo = ahora - timedelta(minutes=31)
    async with session_factory() as sesion:
        await make_job_run(sesion, JOB, DIA, result="running", started_at=inicio_viejo)
    with actor_scope(SYSTEM_USER_ID):
        vista = await _reclamar(session_factory, ahora)
        assert vista is not None
        cerrado = await _cerrar(session_factory, vista, details={"placeholder_ok": 1})

    intentos = cerrado.details["attempts"]
    assert [i["result"] for i in intentos] == ["stale", "ok"]
    assert all(set(i) == CLAVES_INTENTO for i in intentos)
    assert datetime.fromisoformat(intentos[0]["started_at"]) == inicio_viejo
    assert datetime.fromisoformat(intentos[0]["finished_at"]) == ahora
    assert intentos[0]["error"] is None


async def test_un_doble_cierre_del_mismo_intento_no_duplica_attempts(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        vista = await _reclamar(session_factory, reloj_worker.now_utc())
        assert vista is not None
        primero = await _cerrar(session_factory, vista, details={"placeholder_ok": 1})
        segundo = await _cerrar_si_es_suyo(session_factory, vista, result="error", error="X")

    assert segundo is None
    fila = (await _filas(session_factory))[0]
    assert (fila.result, fila.error) == ("ok", None)
    assert fila.details == primero.details and len(fila.details["attempts"]) == 1


async def test_sin_reclaim_finished_un_dia_cerrado_no_se_vuelve_a_reclamar(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    ahora = reloj_worker.now_utc()
    with actor_scope(SYSTEM_USER_ID):
        primero = await _reclamar(session_factory, ahora)
        assert primero is not None
        await _cerrar(session_factory, primero, result="error", error="RuntimeError")
        async with session_factory() as sesion:
            otro = await claim_run(
                sesion, JOB, DIA, now=ahora + timedelta(hours=1), reclaim_finished=False
            )
            await sesion.commit()

    assert otro is None
    fila = (await _filas(session_factory))[0]
    assert (fila.result, fila.started_at) == ("error", ahora)


def test_attempts_path_recorta_a_max_attempts() -> None:
    assert ATTEMPTS_PATH == f"$[last - {MAX_ATTEMPTS - 1} to last]"
