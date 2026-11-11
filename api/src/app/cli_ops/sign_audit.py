"""`sign-audit [--as <correo>]` (S6-A2, US-141; S6-D8, D80, M-2d).

Firma a mano la cadena de auditoría: carga el keyring por `cli_base.crypto_runtime` (sin importar
el bus, S4B-D30) y llama `core.audit_sign.sign_latest` bajo el mismo candado `4_270_004` del job
(si otro firmante lo tiene, espera). Salidas: 0 firmó o sin novedades; 1 falló la firma o la
cadena está rota; 2 custodio sellado/inalcanzable o uso. Con `ENV=production` exige `--as` (un
admin activo). La salida lleva solo el número de registro y el código del error: nunca la
firma, un hash ni lo que dijo el proveedor.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Final

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
    unit_of_work,
)
from app.core.audit_sign import SignOutcome, limit_statement_time, sign_latest
from app.core.config import Settings
from app.core.crypto.errors import CryptoError, CryptoUnavailable

COMMAND = "sign-audit"
SIGN_TIMEOUT_S: Final = 30
"""Tope de la firma manual: un proveedor colgado no retiene el candado `4_270_004` (L1)."""
SEALED: Final = "el custodio de llaves no responde: desellar OpenBao y reintentar"


def _say(texto: str, *, error: bool = False) -> None:
    typer.echo(f"{COMMAND}: {texto}", err=error)


def _report(resultado: SignOutcome) -> int:
    if resultado.kind == "signed":
        _say(f"cadena firmada hasta el registro {resultado.through_seq}")
        return 0
    if resultado.kind == "nothing_new":
        _say(f"sin novedades (última firmada: registro {resultado.through_seq})")
        return 0
    _say(
        f"la cadena está rota en el registro {resultado.through_seq}; no se firmó "
        "(corra verify-audit)",
        error=True,
    )
    return 1


async def _sign(settings: Settings, options: RuntimeOptions, actor_email: str | None) -> int:
    async with crypto_runtime(settings, options) as session:
        async with session.begin():
            actor = await resolve_admin_actor(session, actor_email, required=False)
        try:
            with unit_of_work(actor):
                async with session.begin():
                    await limit_statement_time(session, SIGN_TIMEOUT_S)
                    resultado = await asyncio.wait_for(
                        sign_latest(session, by=actor), SIGN_TIMEOUT_S
                    )
        except CryptoUnavailable:
            _say(SEALED, error=True)
            return 2
        except CryptoError as error:
            _say(f"no se pudo firmar la cadena ({error.code})", error=True)
            return 1
        except Exception as error:  # el proveedor falló: solo el tipo, nunca su texto
            _say(f"no se pudo firmar la cadena ({type(error).__name__})", error=True)
            return 1
    return _report(resultado)


def register(app: typer.Typer) -> None:
    @app.command(COMMAND)
    def sign_audit_command(
        ctx: typer.Context,
        actor: Annotated[str | None, typer.Option("--as")] = None,
    ) -> None:
        """Firma a mano la cadena de auditoría."""
        settings, opciones = cli_base.get_settings(), runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        codigo = _run(_sign(settings, opciones, actor))
        if codigo:
            raise typer.Exit(code=codigo)
