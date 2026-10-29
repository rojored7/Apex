"""Horario del worker, funciones puras (US-113; S4A-D5, S4A-D6, S4A-D48, S4A-D55).

Valores calculados a mano desde la regla:
- 07:00 de Bogotá (UTC-5, sin horario de verano) son las 12:00Z. Desde `2026-10-21T11:59Z` el
  próximo disparo es `2026-10-21T12:00Z`; desde `12:00:01Z` ya pasó y es `2026-10-22T12:00Z`.
- `2026-10-22T01:00Z` son las 20:00 del 21 en Bogotá: `today_bogota` da `2026-10-21`.
- `STALE_FACTOR * timeout_s` con `timeout_s=900` son 1.800 s (30 min): un `running` de hace 31 min
  está muerto (sí se corre), uno de hace 10 min sigue vivo (no se corre).
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.clock import FrozenClock
from app.core.jobs import JobRunView
from app.worker.jobs import JOBS
from app.worker.registry import JobSpec, get_registry, register
from app.worker.schedule import (
    DAILY_HOUR,
    DAILY_MINUTE,
    STALE_FACTOR,
    WORKER_TIMEZONE,
    is_simulated,
    next_run,
    should_run,
    simulated_name,
)

BOGOTA = ZoneInfo("America/Bogota")
DIA = date(2026, 10, 21)
PROGRAMADA = datetime(2026, 10, 21, 7, 0, tzinfo=BOGOTA)  # 12:00Z
FORMA_JOB_NAME = re.compile(r"^[a-z][a-z0-9_]{1,62}$")  # CHECK de `0012` (S4A-D38)


def _fila(
    resultado: str,
    *,
    hace: timedelta = timedelta(hours=1),
    ahora: datetime,
    job_name: str = "expirations",
    run_date: date = DIA,
) -> JobRunView:
    inicio = ahora - hace
    return JobRunView(
        id=uuid4(),
        job_name=job_name,
        run_date=run_date,
        started_at=inicio,
        finished_at=None if resultado == "running" else inicio,
        result=resultado,
        error="RuntimeError" if resultado == "error" else None,
        details={},
    )


# Constantes ---------------------------------------------------------------------------------------


def test_constantes_del_horario() -> None:
    assert WORKER_TIMEZONE == "America/Bogota"
    assert (DAILY_HOUR, DAILY_MINUTE) == (7, 0)
    assert STALE_FACTOR == 2


# next_run -----------------------------------------------------------------------------------------


def test_next_run_un_minuto_antes_da_las_doce_utc_del_mismo_dia() -> None:
    proximo = next_run(datetime(2026, 10, 21, 11, 59, tzinfo=UTC), WORKER_TIMEZONE, 7, 0)
    assert proximo == datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    assert proximo.tzinfo is not None


def test_next_run_un_segundo_despues_da_el_dia_siguiente() -> None:
    proximo = next_run(datetime(2026, 10, 21, 12, 0, 1, tzinfo=UTC), WORKER_TIMEZONE, 7, 0)
    assert proximo == datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def test_next_run_cruza_la_medianoche_utc_sin_saltar_el_dia_de_bogota() -> None:
    # 2026-10-22T01:00Z son las 20:00 del 21 en Bogotá: el próximo 07:00 es el del 22 (12:00Z).
    proximo = next_run(datetime(2026, 10, 22, 1, 0, tzinfo=UTC), WORKER_TIMEZONE, 7, 0)
    assert proximo == datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def test_today_bogota_a_la_una_utc_es_el_dia_anterior() -> None:
    assert FrozenClock(datetime(2026, 10, 22, 1, 0, tzinfo=UTC)).today_bogota() == date(
        2026, 10, 21
    )


# should_run ---------------------------------------------------------------------------------------


def test_sin_fila_corre_despues_de_la_hora() -> None:
    ahora = datetime(2026, 10, 21, 9, 0, tzinfo=BOGOTA)
    assert should_run("expirations", DIA, ahora, PROGRAMADA, None) is True


def test_sin_fila_no_corre_antes_de_la_hora() -> None:
    ahora = datetime(2026, 10, 21, 6, 59, tzinfo=BOGOTA)
    assert should_run("expirations", DIA, ahora, PROGRAMADA, None) is False


def test_con_ok_del_dia_no_corre() -> None:
    ahora = datetime(2026, 10, 21, 9, 0, tzinfo=BOGOTA)
    assert should_run("expirations", DIA, ahora, PROGRAMADA, _fila("ok", ahora=ahora)) is False


def test_con_error_del_dia_no_reintenta_solo() -> None:
    ahora = datetime(2026, 10, 21, 9, 0, tzinfo=BOGOTA)
    assert should_run("expirations", DIA, ahora, PROGRAMADA, _fila("error", ahora=ahora)) is False


def test_running_de_hace_31_minutos_esta_muerto_y_corre() -> None:
    ahora = datetime(2026, 10, 21, 9, 0, tzinfo=BOGOTA)
    previa = _fila("running", hace=timedelta(minutes=31), ahora=ahora)
    assert should_run("expirations", DIA, ahora, PROGRAMADA, previa, timeout_s=900) is True


def test_running_de_hace_10_minutos_sigue_vivo_y_no_corre() -> None:
    ahora = datetime(2026, 10, 21, 9, 0, tzinfo=BOGOTA)
    previa = _fila("running", hace=timedelta(minutes=10), ahora=ahora)
    assert should_run("expirations", DIA, ahora, PROGRAMADA, previa, timeout_s=900) is False


def test_el_umbral_de_muerto_escala_con_timeout_s() -> None:
    ahora = datetime(2026, 10, 21, 9, 0, tzinfo=BOGOTA)
    previa = _fila("running", hace=timedelta(minutes=31), ahora=ahora)
    # 2 * 1.200 s = 40 min: a los 31 min sigue vivo.
    assert should_run("expirations", DIA, ahora, PROGRAMADA, previa, timeout_s=1200) is False


def test_una_fila_simulada_del_dia_no_cuenta_para_el_job_real() -> None:
    ahora = datetime(2026, 10, 21, 9, 0, tzinfo=BOGOTA)
    simulada = _fila("ok", ahora=ahora, job_name="expirations_sim")
    assert should_run("expirations", DIA, ahora, PROGRAMADA, simulada) is True


def test_una_fila_de_otro_dia_no_cuenta() -> None:
    ahora = datetime(2026, 10, 21, 9, 0, tzinfo=BOGOTA)
    ayer = _fila("ok", ahora=ahora, hace=timedelta(days=1), run_date=DIA - timedelta(days=1))
    assert should_run("expirations", DIA, ahora, PROGRAMADA, ayer) is True


# Nombres simulados --------------------------------------------------------------------------------


def test_nombre_simulado() -> None:
    assert simulated_name("expirations") == "expirations_sim"
    assert is_simulated("expirations_sim") is True
    assert is_simulated("expirations") is False
    assert is_simulated("simulacion") is False


@pytest.mark.parametrize("job", ["expirations", "sign_audit", "backup_check"])
def test_el_nombre_simulado_cumple_el_check_de_forma(job: str) -> None:
    assert FORMA_JOB_NAME.fullmatch(simulated_name(job))


# Registro (S4A-D6) --------------------------------------------------------------------------------


def test_register_devuelve_un_registro_nuevo_sin_mutar_el_anterior() -> None:
    base = get_registry()
    extra = JobSpec(name="prueba_extra", run=base[0].run, hour=7, minute=0)

    nuevo = register(base, extra)

    assert nuevo == (*base, extra)
    assert get_registry() == base and extra not in base


def test_register_rechaza_un_nombre_repetido() -> None:
    base = get_registry()
    with pytest.raises(ValueError):
        register(base, JobSpec(name=base[0].name, run=base[0].run, hour=8, minute=0))


def test_el_registro_del_proceso_es_jobs_con_expirations_a_las_siete() -> None:
    assert get_registry() is JOBS
    assert [(s.name, s.hour, s.minute, s.timeout_s) for s in JOBS] == [("expirations", 7, 0, 900)]
