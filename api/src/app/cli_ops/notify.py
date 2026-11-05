"""`notify [--generate-only | --send-only] [--as <correo>]` (S5-B7/B8, US-124 a US-126; S5-D26,
S5-D97, S5-D226).

- `--generate-only` (B7): `notifications.service.generate_today` con el "hoy" de Bogotá del reloj,
  sin reclamo. Imprime `notify: generados N, ya renovaron N, sin consentimiento N, sin reglas
  sí|no`.
- Sin flags (generar + enviar) o `--send-only` (solo enviar): se reclaman por
  `worker.runner.run_job` con el mismo `claim_run('notify')` del worker, así un segundo proceso no
  envía el mismo aviso. El actor de la corrida es el sistema (`sent_by = SYSTEM_USER_ID`, D33);
  `--as` se valida (admin activo) y queda en UNA línea de log (`notify: solicitado por <id>`).
  Salidas como `--run-once`: 0 ok, 1 el job falló, 3 ya hay una corrida vigente; 2 por uso.
- Ambos flags juntos salen con 2. Con `ENV=production` exige `--as` y rechaza `--db-timeouts off`.
La salida lleva solo conteos: ni UUID, ni correos, ni nombres.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Annotated, Any, Final

import typer

from app import cli_base
from app.cli_base import (
    RuntimeOptions,
    _run,
    cli_runtime,
    crypto_runtime,
    production_guard_error,
    reject,
    resolve_actor,
    resolve_admin_actor,
    runtime_options,
    unit_of_work,
)
from app.core.clock import current_clock
from app.core.config import Settings

COMMAND = "notify"
EXIT_BY_RESULT: Final = {"ok": 0, "ok_unverified": 0, "error": 1, "running": 3}
SUMMARY_LABELS: Final = (
    ("generados", "generados"),
    ("ya_renovaron", "ya renovaron"),
    ("sin_consentimiento", "sin consentimiento"),
    ("sin_reglas", "sin reglas"),
    ("enviados", "enviados"),
    ("fallidos", "fallidos"),
    ("omitidos", "omitidos"),
    ("pendientes", "pendientes"),
    ("sellado", "sellado"),
)
logger = logging.getLogger("app.cli")


async def _generate(settings: Settings, options: RuntimeOptions, actor_email: str | None) -> str:
    from app.modules.notifications import service

    async with cli_runtime(settings, options) as session:
        async with session.begin():
            actor = await resolve_actor(session, actor_email)
        with unit_of_work(actor):
            resultado = await service.generate_today(session, current_clock().today_bogota())
            await session.commit()
    return (
        f"{COMMAND}: generados {resultado.generados}, ya renovaron {resultado.ya_renovaron}, "
        f"sin consentimiento {resultado.sin_consentimiento}, "
        f"sin reglas {'sí' if resultado.sin_reglas else 'no'}"
    )


def _summary(result: str, error_type: str | None, details: dict[str, Any]) -> str:
    """`notify: clave N, ...` solo con los conteos del job (sin datos personales)."""
    if result == "running":
        return f"{COMMAND}: ya hay una corrida en curso"
    partes = [f"{texto} {details[clave]}" for clave, texto in SUMMARY_LABELS if clave in details]
    if error_type is not None:
        partes.append(f"error {error_type}")
    return f"{COMMAND}: " + ", ".join(partes)


async def _send(
    settings: Settings, options: RuntimeOptions, actor_email: str | None, *, send_only: bool
) -> tuple[str, int]:
    """El job `notify` por `run_job` (S5-D226); `(línea, código de salida)`."""
    from app.core import db
    from app.worker.jobs import notify as notify_job
    from app.worker.registry import get_registry
    from app.worker.runner import run_job

    spec = next(s for s in get_registry() if s.name == notify_job.NAME)
    if send_only:
        spec = replace(spec, run=notify_job.run_send_only)
    async with crypto_runtime(settings, options, persist_keys=False) as session:
        async with session.begin():
            quien = await resolve_admin_actor(session, actor_email, required=False)
        logger.info("notify: solicitado por %s", quien)
        salida = await run_job(spec, clock=current_clock(), session_factory=db.get_sessionmaker())
    linea = _summary(salida.result, salida.error_type, salida.details)
    return linea, EXIT_BY_RESULT.get(salida.result, 1)


def register(app: typer.Typer) -> None:
    @app.command(COMMAND)
    def notify_command(
        ctx: typer.Context,
        generate_only: Annotated[bool, typer.Option("--generate-only")] = False,
        send_only: Annotated[bool, typer.Option("--send-only")] = False,
        actor: Annotated[str | None, typer.Option("--as")] = None,
    ) -> None:
        """Genera y envía los avisos del día (idempotente); `--generate-only` o `--send-only`."""
        settings = cli_base.get_settings()
        opciones = runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        if generate_only and send_only:
            reject("--generate-only y --send-only no se combinan", COMMAND)
        if generate_only:
            typer.echo(_run(_generate(settings, opciones, actor)))
            return
        linea, codigo = _run(_send(settings, opciones, actor, send_only=send_only))
        typer.echo(linea)
        raise typer.Exit(code=codigo)
