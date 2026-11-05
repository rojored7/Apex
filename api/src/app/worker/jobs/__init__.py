"""Jobs del worker (US-113; S4A-D6). `JOBS` es la tupla que lee `registry.get_registry()`."""

from __future__ import annotations

from app.worker.jobs import backup_check, expirations, notify
from app.worker.registry import JobSpec
from app.worker.schedule import DAILY_HOUR, DAILY_MINUTE

JOBS: tuple[JobSpec, ...] = (
    JobSpec(name=expirations.NAME, run=expirations.run, hour=DAILY_HOUR, minute=DAILY_MINUTE),
    # S5-B8 (S5-D35): después de `expirations` (los estados ya recalculados), antes del chequeo.
    JobSpec(name=notify.NAME, run=notify.run, hour=DAILY_HOUR, minute=DAILY_MINUTE, timeout_s=600),
    # S4B-B2 (S4B-D25): mismo horario, después de `expirations`; tiempo máximo 600 s (sin `age`).
    JobSpec(
        name=backup_check.NAME,
        run=backup_check.run,
        hour=DAILY_HOUR,
        minute=DAILY_MINUTE,
        timeout_s=600,
    ),
)
