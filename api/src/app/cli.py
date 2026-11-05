"""Comandos del api (`python -m app.cli`; en Compose, `docker compose run --rm tools <cmd>`).

- `export-openapi <ruta>` (US-021): construye `create_app()` con una configuración de
  exportación (sin `.env`, sin base y sin llaves), llama a `app.openapi()` y escribe JSON
  con claves ordenadas, sangría de 2 y salto de línea final. `info.version` es la versión
  del paquete, no `APP_VERSION`, para que la salida no cambie con cada commit. No escribe
  en tablas, así que no necesita actor.

Comandos siguientes: `init-keys` (US-023), `seed --as` (US-041), `issue-reset-link --as`
(S2-B4, L-13), `unlock-user --as` (S2-B5; `--as` obligatorio desde la revisión V10, N-4),
`import-members`, `rotate-key`, `sign-audit`. Todo comando que escriba tablas acepta
`--as <email>` (N-15) y abre la base con `cli_runtime(settings, runtime_options(ctx))`
(revisión Python M8; las opciones globales van en `ctx.obj`, PL1 de Fase 4 del Sprint 3): instala
los listeners de auditoría, bitácora del bus y cifrado, carga los services de los módulos
(`_load_module_services`, S2-B6) para que los eventos que emite queden auditados, y libera el
engine al terminar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from app.cli_base import (
    DB_TIMEOUTS_CHOICES,
    RuntimeOptions,
    _load_module_services,
    _run,
    _sin_tiempos_de_espera,
    cli_runtime,
    get_settings,
    production_guard_error,
    reject,
    resolve_actor,
    runtime_options,
    unit_of_work,
)
from app.cli_ops import register_ops
from app.cli_ops.accounts import (
    _LINK_REJECTED,
    _UNLOCK_REJECTED,
    SeedNotificationsFailed,
    _issue_reset_link,
    _seed,
    _unlock_user,
)
from app.cli_ops.keys import (
    KEK_LEN,
    SEED_LEN,
    KeyPaths,
    init_keys_files,
    key_paths_from_settings,
    key_paths_in,
)
from app.cli_ops.openapi import (
    build_openapi_document,
    export_settings,
    write_openapi,
)
from app.cli_ops.recompute import (
    RECOMPUTE_KEYS,
    _recompute,
    _recompute_target,
)
from app.cli_ops.seed_demo import run_seed_demo
from app.cli_ops.verify_audit import _verify_audit

__all__ = [
    "DB_TIMEOUTS_CHOICES",
    "KEK_LEN",
    "SEED_LEN",
    "KeyPaths",
    "RuntimeOptions",
    "_load_module_services",
    "_run",
    "_sin_tiempos_de_espera",
    "app",
    "build_openapi_document",
    "cli_runtime",
    "export_settings",
    "get_settings",
    "init_keys_files",
    "key_paths_from_settings",
    "key_paths_in",
    "production_guard_error",
    "reject",
    "resolve_actor",
    "runtime_options",
    "unit_of_work",
    "write_openapi",
]

app = typer.Typer(no_args_is_help=True, add_completion=False)

_SEED_OUTCOMES = {
    "created": "seed: admin inicial creado",
    "skipped": "seed: omitido: ya existe un admin activo",
}


@app.callback()
def main(
    ctx: typer.Context,
    db_timeouts: Annotated[
        str,
        typer.Option(
            "--db-timeouts",
            help="off pone en 0 los tres DB_*_TIMEOUT_MS (rotate-key, sign-audit, importación).",
        ),
    ] = "on",
) -> None:
    """Comandos de APEX. `--db-timeouts off` va antes del comando (S3-D43, E7)."""
    if db_timeouts not in DB_TIMEOUTS_CHOICES:
        raise typer.BadParameter(
            f"use {' u '.join(DB_TIMEOUTS_CHOICES)}", param_hint="--db-timeouts"
        )
    # Por invocación (`ctx.obj`): un `off` anterior nunca se arrastra.
    ctx.obj = RuntimeOptions(db_timeouts=db_timeouts == "on")


@app.command("export-openapi")
def export_openapi(output: Path) -> None:
    """Exporta el contrato OpenAPI a `output`, sin `.env`, base ni llaves."""
    write_openapi(build_openapi_document(), output)
    typer.echo(f"openapi: escrito {output}")


@app.command("init-keys")
def init_keys(
    directory: Annotated[Path | None, typer.Option("--dir")] = None,
    actor: Annotated[str | None, typer.Option("--as")] = None,
    data_class: Annotated[str | None, typer.Option("--data-class")] = None,
) -> None:
    """Crea la KEK, la llave de firma del bus y el par JWT Ed25519 (modo 600), sin sobrescribir.

    Idempotente (A-1): lo que ya existe se conserva. No crea las DEK: las crea el api al
    arrancar (`ensure_keys`, US-025). `--as` solo se anota en el log porque no escribe en
    la base. `--data-class` queda reservado para US-140.
    """
    if data_class is not None:
        typer.echo("init-keys --data-class no implementado todavía (US-140)", err=True)
        raise typer.Exit(code=2)
    rutas = (
        key_paths_in(directory)
        if directory is not None
        else key_paths_from_settings(get_settings())
    )
    estado = init_keys_files(rutas)
    quien = f" (por {actor})" if actor else ""
    for nombre, resultado in estado.items():
        typer.echo(f"init-keys: {nombre}: {resultado}{quien}")


@app.command("seed")
def seed(
    ctx: typer.Context,
    actor: Annotated[str | None, typer.Option("--as")] = None,
    no_force_change: Annotated[bool, typer.Option("--no-force-change")] = False,
    demo: Annotated[bool, typer.Option("--demo")] = False,
    force_demo_on_non_empty: Annotated[bool, typer.Option("--force-demo-on-non-empty")] = False,
    allow_production: Annotated[bool, typer.Option("--allow-production")] = False,
) -> None:
    """Crea el primer admin activo con ADMIN_EMAIL y ADMIN_INITIAL_PASSWORD (idempotente).

    Con `--demo` siembra los datos de demostración en su lugar (S4B-D32; no lee `.env.seed`).

    Las dos variables salen de `.env.seed` o del entorno del servicio tools (`SeedSettings`,
    M-8), nunca de `Settings`. El admin sembrado debe cambiar la contraseña al entrar; solo con
    `ENV=dev` se acepta `--no-force-change`. Sale con 2 si falta el correo, falta la
    contraseña o es débil (L-9: el literal histórico del ejemplo está en la lista de comunes);
    nunca imprime la contraseña.
    """
    if demo:
        run_seed_demo(ctx, actor, force_demo_on_non_empty, allow_production)
        return
    _seed_admin(ctx, actor, no_force_change=no_force_change)


def _seed_admin(ctx: typer.Context, actor: str | None, *, no_force_change: bool) -> None:
    """Cuerpo de `seed` sin `--demo`: el primer admin desde `.env.seed` (US-041)."""
    from app.core.config import load_seed_settings
    from app.core.security import WeakPasswordError, validate_password_policy
    from app.modules.auth.exceptions import AuthError

    settings = get_settings()
    if no_force_change and settings.ENV != "dev":
        typer.echo("seed: --no-force-change solo se acepta con ENV=dev", err=True)
        raise typer.Exit(code=2)
    semilla = load_seed_settings()
    if not semilla.ADMIN_EMAIL or semilla.ADMIN_INITIAL_PASSWORD is None:
        typer.echo("seed: faltan ADMIN_EMAIL o ADMIN_INITIAL_PASSWORD en .env.seed", err=True)
        raise typer.Exit(code=2)
    clave = semilla.ADMIN_INITIAL_PASSWORD.get_secret_value()
    try:
        validate_password_policy(clave)
    except WeakPasswordError as error:
        typer.echo(f"seed: ADMIN_INITIAL_PASSWORD no cumple la política ({error.reason})", err=True)
        raise typer.Exit(code=2) from None
    try:
        resultado = _run(
            _seed(
                settings,
                semilla.ADMIN_EMAIL,
                clave,
                actor,
                force_change=not no_force_change,
                options=runtime_options(ctx),
            )
        )
    except AuthError as error:
        typer.echo(f"seed: {error.code}", err=True)
        raise typer.Exit(code=2) from None
    except SeedNotificationsFailed as error:
        typer.echo(_SEED_OUTCOMES.get(error.outcome, "seed: administrador listo"))
        typer.echo(
            "seed: la siembra de avisos falló; ejecute seed-notifications (el administrador no "
            "se revirtió)",
            err=True,
        )
        raise typer.Exit(code=1) from None
    if resultado == "created":
        typer.echo("seed: admin inicial creado")
    else:
        typer.echo("seed: omitido: ya existe un admin activo")


@app.command("issue-reset-link")
def issue_reset_link(
    ctx: typer.Context,
    email: str,
    actor: Annotated[str | None, typer.Option("--as")] = None,
) -> None:
    """Emite el enlace de activación o restablecimiento de `email` y lo imprime una sola vez
    (S2-B4, L-13): la salida para recuperar a un admin, incluida la propia cuenta de quien lo
    invoca, que `POST /users/{id}/resend-link` rechaza. `--as` es obligatorio y debe ser un
    admin activo; deja el `insert` auditado con su `created_by`. Sale con 2 si falta `--as`, si
    no es un admin activo o si la cuenta no puede recibir el enlace (sin revelar si existe).
    """
    if actor is None:
        typer.echo("issue-reset-link: --as <correo de un admin activo> es obligatorio", err=True)
        raise typer.Exit(code=2)
    settings = get_settings()
    salida = _run(_issue_reset_link(settings, email, actor, runtime_options(ctx)))
    if salida is None:
        typer.echo(_LINK_REJECTED, err=True)
        raise typer.Exit(code=2)
    url, purpose, expires_at = salida
    typer.echo(f"issue-reset-link: enlace de {purpose} válido hasta {expires_at}")
    typer.echo(url)


@app.command("unlock-user")
def unlock_user(
    ctx: typer.Context,
    email: str,
    actor: Annotated[str | None, typer.Option("--as")] = None,
) -> None:
    """Desbloquea la cuenta de `email` (S2-B5, US-050; S2-D10): limpia `locked_at` y
    `failed_login_count` con `service.unlock` y deja el `update` auditado con el actor de `--as`,
    obligatorio y admin activo como en `issue-reset-link` (revisión de seguridad V10, N-4: sin él
    el desbloqueo quedaba atribuido al usuario técnico). Corre en otro proceso que el api: los
    contadores en memoria del api se limpian con `up -d api` (docs/RUNBOOK.md). Sale con 2 si
    falta `--as` o no es un admin activo, y con el mismo mensaje y sin repetir el correo si la
    cuenta no existe, está borrada o no está bloqueada.
    """
    if actor is None:
        typer.echo("unlock-user: --as <correo de un admin activo> es obligatorio", err=True)
        raise typer.Exit(code=2)
    settings = get_settings()
    if not _run(_unlock_user(settings, email, actor, runtime_options(ctx))):
        typer.echo(_UNLOCK_REJECTED, err=True)
        raise typer.Exit(code=2)
    typer.echo("unlock-user: cuenta desbloqueada")


@app.command("recompute-memberships")
def recompute_memberships(
    ctx: typer.Context,
    on_date: Annotated[str | None, typer.Option("--date")] = None,
    simulate: Annotated[bool, typer.Option("--simulate")] = False,
    actor: Annotated[str | None, typer.Option("--as")] = None,
) -> None:
    """Recalcula la columna `status` de las membresías (S4A-B2, US-094; S4A-D15, S4A-D48,
    S4A-D53, E5): `memberships.service.recompute_statuses` con `db.get_sessionmaker()` como
    fábrica, bajo `unit_of_work(actor)` (`--as`, o `SYSTEM_USER_ID` sin él).

    - `--date AAAA-MM-DD` distinto de hoy exige `--simulate`, `ENV=dev` y una base de
      `DATABASE_URL` que termine en `_sim` o sea `apex_test` (guarda dura de E5); con
      `--simulate` el reloj es `FrozenClock` a las 12:00 de Bogotá de esa fecha, la primera línea
      de la salida es `RELOJ SIMULADO: <fecha>` y la corrida reclama `expirations_sim`;
    - con `ENV=production` exige `--as` y rechaza `--db-timeouts off` (S4A-D53);
    - imprime solo los conteos de `RecomputeSummary` (nunca ids ni nombres);
    - sale 0, o 1 si `busy_omitidos + errores > 0`, o 2 por argumento inválido, `--as` inválido o
      una guarda incumplida; con `--simulate`, 3 si otra corrida `expirations_sim` del mismo día
      sigue vigente (como `--run-once` del worker).

    Con `--simulate` la corrida pasa por `app.worker.runner.run_job(..., simulated=True)` (S4A-D89):
    el runner reclama `expirations_sim`, fija el reloj solo dentro de la corrida y atribuye la
    auditoría al usuario técnico; por eso `--simulate` con `--as` sale con 2. Sin `--simulate` no
    se toca `worker.job_runs`.
    """
    settings = get_settings()
    opciones = runtime_options(ctx)
    objetivo = _recompute_target(settings, opciones, on_date, simulate=simulate, actor=actor)
    if simulate:
        typer.echo(f"RELOJ SIMULADO: {objetivo.isoformat()}")
    conteos, codigo = _run(_recompute(settings, opciones, objetivo, simulate, actor))
    texto = " ".join(f"{clave}={conteos.get(clave, 0)}" for clave in RECOMPUTE_KEYS)
    typer.echo(f"recompute-memberships: {texto}")
    raise typer.Exit(code=codigo)


@app.command("verify-audit")
def verify_audit(
    ctx: typer.Context,
    actor: Annotated[str | None, typer.Option("--as")] = None,
    wait_timeout: Annotated[int, typer.Option("--wait-timeout", min=0)] = 300,
) -> None:
    """Verifica la cadena de auditoría (S4A-B3, US-105; S4A-D15, S4A-D43, S4A-D44, S4A-D53).

    - toma el candado `4_270_003` con `pg_try_advisory_lock` cada `VERIFY_LOCK_POLL_S` segundos
      hasta `--wait-timeout` (por `audit.service.acquire_verify_lock`: conexión `AUTOCOMMIT` que
      `release_verify_lock` invalida al terminar);
    - corre `core.audit_verify.run_verification(session, source="cli", by=actor)` bajo
      `unit_of_work(actor)` (`--as`, o `SYSTEM_USER_ID` sin él) y confirma;
    - imprime `format_verify_message` (nunca `before` ni `after`) y sale 0 (íntegra) o 1 (rota);
    - sale 2 si `--as` no sirve, si la base no responde (mensaje genérico, sin URL ni contraseña),
      si `--wait-timeout` se agota, o con `ENV=production` sin `--as` o con `--db-timeouts off`.
    """
    from sqlalchemy.exc import SQLAlchemyError

    settings = get_settings()
    opciones = runtime_options(ctx)
    if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
        reject(rechazo, "verify-audit")
    try:
        texto, codigo = _run(_verify_audit(settings, opciones, actor, wait_timeout))
    except (OSError, SQLAlchemyError):
        reject("la base de datos no responde", "verify-audit")
    typer.echo(texto)
    raise typer.Exit(code=codigo)


register_ops(app)


if __name__ == "__main__":
    app()
