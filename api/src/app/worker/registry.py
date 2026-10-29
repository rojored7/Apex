"""Registro inmutable de jobs del worker (US-113; S4A-D6).

- `JobSpec(name, run, hour, minute, timeout_s=900)`: dataclass congelada; `run` es
  `async (JobContext) -> JobResult`.
- `register(registry, spec)`: pura; devuelve una tupla nueva con `spec` al final (un nombre
  repetido lanza `ValueError`).
- `get_registry()`: la tupla de `app.worker.jobs.JOBS`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.worker.runner import JobContext, JobResult

JobRun = Callable[[JobContext], Awaitable[JobResult]]


@dataclass(frozen=True)
class JobSpec:
    """Un job programado: nombre (`^[a-z][a-z0-9_]{1,62}$`), función, hora y tiempo máximo."""

    name: str
    run: JobRun
    hour: int
    minute: int
    timeout_s: int = 900


def register(registry: tuple[JobSpec, ...], spec: JobSpec) -> tuple[JobSpec, ...]:
    """Registro nuevo con `spec` al final; no muta `registry`."""
    if any(previo.name == spec.name for previo in registry):
        raise ValueError(f"job repetido: {spec.name}")
    return (*registry, spec)


def get_registry() -> tuple[JobSpec, ...]:
    """Los jobs del proceso (`app.worker.jobs.JOBS`).

    Import perezoso: `app.worker.jobs` importa este módulo para declarar `JobSpec`.
    """
    from app.worker.jobs import JOBS

    return JOBS
