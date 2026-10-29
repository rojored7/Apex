"""Horario del worker, funciones puras (US-113; S4A-D5, S4A-D6, S4A-D48, S4A-D55).

- `WORKER_TIMEZONE`, `DAILY_HOUR`, `DAILY_MINUTE`: 07:00 de Bogotá (Q28, N-32); constantes, no
  `Settings` (S4A-D5).
- `STALE_FACTOR`: una corrida `running` de más de `STALE_FACTOR * timeout_s` se da por muerta y se
  puede volver a reclamar (S4A-D55).
- `next_run(now_utc, tz, hour, minute)`: el próximo instante `hour:minute` en `tz` estrictamente
  posterior a `now_utc` (con zona).
- `should_run(job_name, run_date, now_local, scheduled_at, previous, *, timeout_s)`: verdadero
  solo si ya pasó la hora del día y no hay fila de ese job y ese día, o la fila está `running`
  desde hace más de `STALE_FACTOR * timeout_s`. Un `ok` o un `error` del día no se repiten solos.
  Una fila de otro `job_name` (por ejemplo `expirations_sim`) o de otro día cuenta como "sin
  fila" (S4A-D48).
- `is_simulated(job_name)` y `simulated_name(job)`: el sufijo `_sim` de las corridas con reloj
  simulado (S4A-D48).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from app.core.jobs import JobRunView

WORKER_TIMEZONE: Final = "America/Bogota"
DAILY_HOUR: Final = 7
DAILY_MINUTE: Final = 0
STALE_FACTOR: Final = 2
SIMULATED_SUFFIX: Final = "_sim"


def next_run(now_utc: datetime, tz: str, hour: int, minute: int) -> datetime:
    """Próximo `hour:minute` en `tz` posterior a `now_utc` (en UTC, con zona)."""
    zona = ZoneInfo(tz)
    local = now_utc.astimezone(zona)
    candidato = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidato <= local:
        siguiente = local.date() + timedelta(days=1)
        candidato = datetime(
            siguiente.year, siguiente.month, siguiente.day, hour, minute, tzinfo=zona
        )
    return candidato.astimezone(now_utc.tzinfo)


def should_run(
    job_name: str,
    run_date: date,
    now_local: datetime,
    scheduled_at: datetime,
    previous: JobRunView | None,
    *,
    timeout_s: int = 900,
) -> bool:
    """¿Toca correr `job_name` el día `run_date`? (ver docstring del módulo)."""
    if now_local < scheduled_at:
        return False
    if previous is None or previous.job_name != job_name or previous.run_date != run_date:
        return True
    if previous.result != "running":
        return False
    return now_local - previous.started_at > timedelta(seconds=STALE_FACTOR * timeout_s)


def is_simulated(job_name: str) -> bool:
    """`True` si `job_name` es el de una corrida simulada (`<job>_sim`)."""
    return job_name.endswith(SIMULATED_SUFFIX)


def simulated_name(job: str) -> str:
    """`expirations` → `expirations_sim`."""
    return f"{job}{SIMULATED_SUFFIX}"
