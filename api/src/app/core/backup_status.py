"""Estado público de los respaldos para `/health` (US-115; S4B-D26, S4B-D60, S4B-D71).

Único archivo fuera de `app/worker/` que importa `app.core.jobs` (enmienda acotada de
`tests/architecture/test_worker_boundaries.py`, S4B-D26) y solo para leer: de `core.jobs` importa
únicamente `last_run` (`tests/architecture/test_backup_status_imports.py`, S4B-D71); no escribe,
no confirma. Además solo importa `core.db` y `core.clock`.

`backup_health()` abre una sesión corta de solo lectura, lee la última corrida del job
`HEALTH_JOB` y la traduce a los tres valores públicos de `PUBLIC_BACKUP` (S4B-D60): `ok` y
`ok_unverified` -> `ok`; `stale`, `missing`, `corrupt` y `undecryptable` -> `attention`; todo lo
demás (sin corrida, `running`, `error`, base caída o más lenta que 3 s, o una corrida más vieja que
`MAX_RUN_AGE`: ese caso es `attention`, el worker dejó de comprobar) -> `unknown`. El detalle de
los seis estados queda en `worker.job_runs`, `--status backup_check`, el log y la alerta; el
cuerpo público nunca lleva nombre ni ruta de archivo.

`MAX_RUN_AGE` es 36 h (S4B-D114): el job corre una vez al día (24 h) y la prueba fija el rango
abierto 24 h a 40 h; 36 h tolera un día de retraso del worker sin avisar y marca `attention`
antes de que pasen dos ciclos completos.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Final

from app.core.clock import current_clock
from app.core.db import get_sessionmaker
from app.core.jobs import last_run

logger = logging.getLogger("app.backup_status")

HEALTH_JOB: Final = "backup_check"
"""`job_name` cuya última corrida se lee."""

MAX_RUN_AGE: Final = timedelta(hours=36)
"""Una corrida `ok` más vieja que esto ya no sirve: el worker dejó de comprobar -> `attention`."""

BACKUP_STATES: Final[frozenset[str]] = frozenset(
    {"ok", "ok_unverified", "stale", "missing", "corrupt", "undecryptable"}
)
"""Los seis estados del job (valores de `result` en `worker.job_runs`)."""

PUBLIC_BACKUP: Final[frozenset[str]] = frozenset({"ok", "attention", "unknown"})
"""Los tres valores que ve `/health` (S4B-D60)."""


DB_TIMEOUT_S: Final = 2.5
"""Tope de la lectura: con la base caída `/health` responde en menos de 3 s."""

_ATTENTION: Final = frozenset({"stale", "missing", "corrupt", "undecryptable"})
_HEALTHY: Final = frozenset({"ok", "ok_unverified"})


async def backup_health() -> str:
    """Valor público (`PUBLIC_BACKUP`) del último `backup_check`; nunca lanza."""
    try:
        async with asyncio.timeout(DB_TIMEOUT_S), get_sessionmaker()() as sesion:
            corrida = await last_run(sesion, HEALTH_JOB)
    except Exception:
        logger.warning("backup_status: no se pudo leer la última corrida")
        return "unknown"
    if corrida is None:
        return "unknown"
    if current_clock().now_utc() - corrida.started_at > MAX_RUN_AGE:
        return "attention"
    if corrida.result in _HEALTHY:
        return "ok"
    return "attention" if corrida.result in _ATTENTION else "unknown"
