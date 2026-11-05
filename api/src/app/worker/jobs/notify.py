"""Job diario `notify`: genera y envía los avisos del día (S5-B8, US-124 a US-126; S5-D35, S5-D86).

`run(ctx)`: tres fases en un `JobResult` de enteros:
1. `generate`: `notifications.service.generate_today(session, ctx.today)` (confirma por lote);
2. `send`: `notifications.service.send_pending(session_factory, ctx.today, settings=...)`, SOLO si
   `recovery.try_load(..., create_missing=False, classes=WORKER_CRYPTO_CLASSES)` deja el keyring
   cargado; si no (custodio sellado o inalcanzable), omite la fase, `details["sellado"] = 1` y
   el job queda `ok` (`recovery` ya emitió `crypto_sealed` al cambiar el estado, sin repetirlo).
   `forbidden` y `unwrap_failed` no se tragan: el job falla (M-4);
3. `summary`: `alert("notify_summary", ...)` solo con enteros.
`ok = fallidos == 0` (los omitidos no son error). `run_send_only(ctx)`: solo las fases 2 y 3 (CLI
`notify --send-only`). Solo importa `service` de `notifications` (sin SQL ni privados).
"""

from __future__ import annotations

import logging
from typing import Final

from app.core.alerts import alert
from app.core.config import get_settings
from app.core.crypto import recovery
from app.modules.notifications import service as notifications_service
from app.worker.runner import JobContext, JobResult

NAME: Final = "notify"
SEALED_ALERT: Final = "crypto_sealed"
SEALED_KEY: Final = "sellado"
CRYPTO_CLASSES: Final = frozenset({"member.phone", "member.email"})
"""Las clases que abre el job (las mismas que `runtime.WORKER_CRYPTO_CLASSES`)."""

logger = logging.getLogger("app.worker")

__all__ = ["NAME", "get_settings", "notifications_service", "recovery", "run", "run_send_only"]


async def _generate(ctx: JobContext) -> dict[str, int]:
    async with ctx.session_factory() as session:
        resultado = await notifications_service.generate_today(session, ctx.today)
        await session.commit()
    return {
        "generados": resultado.generados,
        "ya_renovaron": resultado.ya_renovaron,
        "sin_consentimiento": resultado.sin_consentimiento,
        "sin_reglas": int(resultado.sin_reglas),
    }


async def _run(ctx: JobContext, *, generate: bool) -> JobResult:
    details: dict[str, int]
    details = {}
    if generate:
        details.update(await _generate(ctx))
    settings = get_settings()
    estado = await recovery.try_load(
        ctx.session_factory, settings, create_missing=False, classes=CRYPTO_CLASSES
    )
    fallidos = 0
    if estado == "ok":
        enviado = await notifications_service.send_pending(
            ctx.session_factory, ctx.today, settings=settings
        )
        fallidos = enviado.fallidos
        if enviado.sin_credenciales:
            alert("mail_unconfigured")  # S5-D231: una vez por corrida, sin datos
        details.update(
            enviados=enviado.enviados,
            fallidos=enviado.fallidos,
            omitidos=enviado.omitidos,
            pendientes=enviado.pendientes,
        )
    else:
        logger.warning(
            "notify: %s, se omite el envío", SEALED_ALERT, extra={"crypto_state": estado}
        )
        details.update(enviados=0, fallidos=0, omitidos=0)
        details[SEALED_KEY] = 1
    alert(
        "notify_summary",
        generados=details.get("generados", 0),
        pendientes=details.get("pendientes", 0),
        enviados=details["enviados"],
        fallidos=details["fallidos"],
        omitidos=details["omitidos"],
    )
    return JobResult(ok=fallidos == 0, details=details)


async def run(ctx: JobContext) -> JobResult:
    return await _run(ctx, generate=True)


async def run_send_only(ctx: JobContext) -> JobResult:
    return await _run(ctx, generate=False)
