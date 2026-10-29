"""`import-members <archivo> --as <correo> [--dry-run] [--report <nombre>]` (S4B-B1, US-112;
S4B-D34, D35, D64).

Salida (stdout, solo conteos): `import-members: created=N skipped_existing=N rejected=N
consent_missing=N notes_ignored=N contacts_omitted=N`, más una advertencia que nombra
`consent_missing` y otra que nombra `notes_ignored` cuando son mayores que 0. Códigos: 0 cabecera
válida (aunque haya filas rechazadas), 2 uso o límites, 1 falla de una escritura. El archivo y el
reporte van dentro de `IMPORT_DIR`; ningún mensaje repite una ruta, un nombre o un valor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from app import cli_base
from app.cli_base import (
    RuntimeOptions,
    _run,
    crypto_runtime,
    production_guard_error,
    reject,
    resolve_admin_actor,
    runtime_options,
)
from app.core.config import Settings
from app.imports.members_xlsx import HeaderError, ImportResult, LimitError, import_members

COMMAND = "import-members"
WRITE_FAILED = "falló una escritura; repita el comando (lo ya importado se omite)"


async def _import(
    settings: Settings,
    options: RuntimeOptions,
    file: Path,
    actor: str,
    dry_run: bool,
    report: str | None,
) -> ImportResult:
    async with crypto_runtime(settings, options, persist_keys=not dry_run) as session:
        async with session.begin():
            actor_id = await resolve_admin_actor(session, actor, required=True)
        return await import_members(settings, file, actor_id, dry_run=dry_run, report=report)


def _summary_lines(result: ImportResult, *, dry_run: bool) -> list[str]:
    lineas = [
        f"{COMMAND}: created={result.created} skipped_existing={result.skipped_existing} "
        f"rejected={result.rejected} consent_missing={result.consent_missing} "
        f"notes_ignored={result.notes_ignored} contacts_omitted={result.contacts_omitted}"
    ]
    if dry_run:
        lineas.append(f"{COMMAND}: simulación (--dry-run): no se escribió nada")
    if result.consent_missing:
        lineas.append(
            f"{COMMAND}: advertencia: consent_missing={result.consent_missing} socios quedaron "
            "sin autorización de tratamiento de datos; no se les puede avisar sin ella"
        )
    if result.notes_ignored:
        lineas.append(
            f"{COMMAND}: advertencia: notes_ignored={result.notes_ignored} filas traían notas "
            "y no se guardaron (v0.1 no tiene ese campo)"
        )
    return lineas


def register(app: typer.Typer) -> None:
    @app.command(COMMAND)
    def import_members_command(
        ctx: typer.Context,
        file: Annotated[Path, typer.Argument(help="Archivo .xlsx dentro de IMPORT_DIR.")],
        actor: Annotated[str | None, typer.Option("--as")] = None,
        dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
        report: Annotated[str | None, typer.Option("--report")] = None,
    ) -> None:
        """Importa socios desde la plantilla Q17 (idempotente por documento)."""
        settings = cli_base.get_settings()  # por el módulo: las pruebas lo reemplazan (S4B-D29)
        opciones = runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        if actor is None:
            reject("--as <correo de un admin activo> es obligatorio", COMMAND)
        try:
            resultado = _run(_import(settings, opciones, file, actor, dry_run, report))
        except (LimitError, HeaderError) as error:
            reject(str(error), COMMAND)
        except typer.Exit:
            raise
        except Exception:
            typer.echo(f"{COMMAND}: {WRITE_FAILED}", err=True)
            raise typer.Exit(code=1) from None
        for linea in _summary_lines(resultado, dry_run=dry_run):
            typer.echo(linea)
