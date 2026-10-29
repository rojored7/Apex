"""Entrada del worker: `python -m app.worker.main` (US-113; S4A-D4, S4A-D6, S4A-D48, E5).

Delgado: la lógica vive en `schedule`, `runner` y `runtime`.

- Sin argumentos: `serve` (scheduler `AsyncIOScheduler(timezone=WORKER_TIMEZONE)`,
  `CronTrigger(hour=DAILY_HOUR, minute=DAILY_MINUTE)`, `coalesce=True`, `max_instances=1`,
  latido cada `HEARTBEAT_INTERVAL_S` tras conectar a la base, recuperación del ciclo del día al
  arrancar con `should_run`, parada por `stop` o `SIGTERM` con espera acotada a 30 s).
- `--run-once <job> [--date AAAA-MM-DD] [--simulate]`: 0 ok, 1 el job falló, 2 job inexistente
  (imprime los registrados) o argumento inválido (incluida la guarda de `--date`,
  `runtime.clock_override_error`), 3 ya hay una corrida `running` vigente. Con fecha simulada:
  `FrozenClock` a las 12:00 de Bogotá de esa fecha, primera línea `RELOJ SIMULADO: <fecha>`,
  `logger.warning("clock override")` y reclamo de `<job>_sim`.
- `--status <job>`: el último intento (`last_run`) en JSON, sin `details["attempts"]`; 0, o 2 si
  no hay corridas. Admite `<job>_sim`.

`load_settings` y `get_registry` se usan por su nombre en este módulo (las pruebas los
reemplazan). `main(argv)` funciona también llamado desde un loop en marcha (como `cli._run`: un
hilo con una copia del contexto, así el reloj fijado por quien llama llega al comando). Nunca lee
`os.environ`: `ENV` sale de `Settings`. La salida intencional (`RELOJ SIMULADO`, la lista de jobs y
el JSON de `--status`) va con `print`; todo lo demás es log JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import logging
import signal
import sys
from collections.abc import Coroutine, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any, Final
from zoneinfo import ZoneInfo

from app.core.alerts import alert
from app.core.clock import Clock, FrozenClock, current_clock, reset_clock, set_clock
from app.core.config import Settings, load_settings
from app.core.jobs import ATTEMPTS_KEY, JobRunView, last_run
from app.worker import runtime
from app.worker.registry import JobSpec, get_registry
from app.worker.runner import RESULT_RUNNING, run_job
from app.worker.schedule import WORKER_TIMEZONE

__all__ = ["build_parser", "get_registry", "load_settings", "main", "run_once", "serve", "status"]

logger = logging.getLogger("app.worker")

EXIT_OK: Final = 0
EXIT_JOB_FAILED: Final = 1
EXIT_USAGE: Final = 2
EXIT_RUNNING: Final = 3
SIMULATED_HOUR: Final = 12
EXIT_BY_RESULT: Final = {"ok": EXIT_OK, "error": EXIT_JOB_FAILED, RESULT_RUNNING: EXIT_RUNNING}


def _fecha(valor: str) -> date:
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise argparse.ArgumentTypeError(f"fecha inválida: {valor!r} (use AAAA-MM-DD)") from None


def build_parser() -> argparse.ArgumentParser:
    """`--run-once <job>`, `--date`, `--simulate`, `--status <job>`."""
    parser = argparse.ArgumentParser(
        prog="python -m app.worker.main",
        description="Worker de APEX: sin argumentos queda programado (07:00 de Bogotá).",
    )
    accion = parser.add_mutually_exclusive_group()
    accion.add_argument("--run-once", metavar="JOB", help="corre JOB una vez y sale")
    accion.add_argument("--status", metavar="JOB", help="último intento de JOB en JSON")
    parser.add_argument("--date", type=_fecha, help="día a simular (AAAA-MM-DD; con --simulate)")
    parser.add_argument("--simulate", action="store_true", help="reloj simulado (solo ENV=dev)")
    return parser


def _buscar(job: str) -> JobSpec | None:
    return next((spec for spec in get_registry() if spec.name == job), None)


def _reloj_simulado(dia: date) -> FrozenClock:
    """12:00 de Bogotá del día pedido (S4A-D4)."""
    zona = ZoneInfo(WORKER_TIMEZONE)
    return FrozenClock(datetime(dia.year, dia.month, dia.day, SIMULATED_HOUR, tzinfo=zona))


def _rechazo_de_fecha(
    objetivo: date, hoy: date, *, simulate: bool, settings: Settings
) -> str | None:
    """Guarda E5 de `--date` y, con `--simulate` aunque sea hoy, la de `ENV` y la base."""
    error = runtime.clock_override_error(objetivo, hoy, simulate=simulate, settings=settings)
    if error is None and simulate:
        return runtime.simulation_error(settings)
    return error


async def run_once(job: str, *, date: date | None, simulate: bool, settings: Settings) -> int:
    """Una corrida de `job` (códigos 0, 1, 2, 3)."""
    spec = _buscar(job)
    if spec is None:
        nombres = ", ".join(s.name for s in get_registry())
        # Salida intencional de la CLI del worker, sin PII (excepción S4A-D87).
        print(f"job inexistente: {job}. Registrados: {nombres}", file=sys.stderr)
        return EXIT_USAGE
    hoy = current_clock().today_bogota()
    objetivo = date or hoy
    rechazo = _rechazo_de_fecha(objetivo, hoy, simulate=simulate, settings=settings)
    if rechazo is not None:
        # Salida intencional de la CLI del worker, sin PII (excepción S4A-D87).
        print(rechazo, file=sys.stderr)
        return EXIT_USAGE
    reloj: Clock = _reloj_simulado(objetivo) if simulate else current_clock()
    if simulate:
        # Antes de `configure_logging`: su handler escribe JSON en stdout (S4A-D48).
        # Salida intencional de la CLI del worker, sin PII (excepción S4A-D87).
        print(f"RELOJ SIMULADO: {objetivo.isoformat()}", flush=True)
    token = set_clock(reloj)
    try:
        return await _correr(spec, reloj, objetivo if simulate else None, settings)
    finally:
        reset_clock(token)


async def _correr(spec: JobSpec, reloj: Clock, simulada: date | None, settings: Settings) -> int:
    """La corrida dentro del runtime. Si la base falla al reclamar o al cerrar, sale con 1 y deja
    solo el tipo del error en el log y en `job_failed` (S4A-D83), sin traza."""
    try:
        async with runtime.worker_runtime(settings) as fabrica:
            if simulada is not None:
                logger.warning("clock override", extra={"simulated_date": simulada.isoformat()})
            outcome = await run_job(
                spec, clock=reloj, session_factory=fabrica, simulated=simulada is not None
            )
    except Exception as error:
        tipo = type(error).__name__
        logger.error("job run failed", extra={"job": spec.name, "error_type": tipo})
        alert("job_failed", job=spec.name, result="error", error_type=tipo)
        return EXIT_JOB_FAILED
    return EXIT_BY_RESULT.get(outcome.result, EXIT_JOB_FAILED)


def _status_json(vista: JobRunView) -> str:
    detalles = {k: v for k, v in vista.details.items() if k != ATTEMPTS_KEY}
    datos = {
        "id": str(vista.id),
        "job_name": vista.job_name,
        "run_date": vista.run_date.isoformat(),
        "started_at": vista.started_at.isoformat(),
        "finished_at": vista.finished_at.isoformat() if vista.finished_at else None,
        "result": vista.result,
        "error": vista.error,
        "details": detalles,
    }
    return json.dumps(datos, ensure_ascii=False, sort_keys=True)


async def status(job: str, settings: Settings) -> int:
    """Imprime el último intento de `job` en JSON (0) o sale con 2 si no hay corridas."""
    async with runtime.worker_runtime(settings) as fabrica, fabrica() as sesion:
        vista = await last_run(sesion, job)
    if vista is None:
        # Salida intencional de la CLI del worker, sin PII (excepción S4A-D87).
        print(f"sin corridas de {job}", file=sys.stderr)
        return EXIT_USAGE
    # Salida intencional de la CLI del worker, sin PII (excepción S4A-D87).
    print(_status_json(vista), flush=True)
    return EXIT_OK


async def serve(settings: Settings, *, stop: asyncio.Event) -> int:
    """Scheduler con latido hasta que `stop` se dispare; 0 al salir limpio."""
    async with runtime.worker_runtime(settings) as fabrica:
        await runtime.wait_for_database(settings)
        ciclos = runtime.CycleTasks(fabrica, get_registry)
        await ciclos.heartbeat()
        scheduler = runtime.build_scheduler(ciclos)
        scheduler.start()
        logger.info("worker started", extra={"timezone": WORKER_TIMEZONE})
        recuperacion = asyncio.create_task(ciclos.cycle())
        try:
            await stop.wait()
        finally:
            scheduler.shutdown(wait=False)
            await ciclos.wait_running()
            (fin_recuperacion,) = await asyncio.gather(recuperacion, return_exceptions=True)
            if isinstance(fin_recuperacion, Exception):
                logger.error(
                    "worker recovery failed",
                    extra={"error_type": type(fin_recuperacion).__name__},
                )
            logger.info("worker stopped")
    return EXIT_OK


async def _serve_until_signal(settings: Settings) -> int:
    """`serve` con SIGTERM y SIGINT conectados a la parada donde la plataforma lo permite."""
    stop = asyncio.Event()
    bucle = asyncio.get_running_loop()
    for senal in (signal.SIGTERM, signal.SIGINT):
        try:
            bucle.add_signal_handler(senal, stop.set)
        except (NotImplementedError, RuntimeError):  # Windows: Ctrl+C llega como interrupción
            continue
    return await serve(settings, stop=stop)


def _run(coro: Coroutine[Any, Any, int]) -> int:
    """`asyncio.run`, o un hilo con su loop y una copia del contexto si ya hay uno (como
    `cli._run`): el reloj y el actor de quien llama llegan al comando."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    contexto = contextvars.copy_context()
    with ThreadPoolExecutor(max_workers=1) as ejecutor:
        return ejecutor.submit(contexto.run, asyncio.run, coro).result()


def _argumentos(argv: Sequence[str] | None) -> argparse.Namespace | int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as salida:  # argparse ya imprimió el uso (o la ayuda, con 0)
        return salida.code if isinstance(salida.code, int) else EXIT_USAGE
    if (args.date is not None or args.simulate) and args.run_once is None:
        # Salida intencional de la CLI del worker, sin PII (excepción S4A-D87).
        print("--date y --simulate solo acompañan a --run-once", file=sys.stderr)
        return EXIT_USAGE
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada; devuelve el código de salida."""
    args = _argumentos(argv)
    if isinstance(args, int):
        return args
    settings = load_settings()
    if args.run_once is not None:
        return _run(
            run_once(args.run_once, date=args.date, simulate=args.simulate, settings=settings)
        )
    if args.status is not None:
        return _run(status(args.status, settings))
    return _run(_serve_until_signal(settings))


if __name__ == "__main__":  # pragma: no cover - entrada del contenedor
    raise SystemExit(main())
