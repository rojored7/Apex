"""Jobs del worker (US-113; S4A-D6). `JOBS` es la tupla que lee `registry.get_registry()`."""

from __future__ import annotations

from app.worker.jobs import expirations
from app.worker.registry import JobSpec
from app.worker.schedule import DAILY_HOUR, DAILY_MINUTE

JOBS: tuple[JobSpec, ...] = (
    JobSpec(name=expirations.NAME, run=expirations.run, hour=DAILY_HOUR, minute=DAILY_MINUTE),
)
