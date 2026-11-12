"""`rotate-key <clase> --reason TEXTO --as <correo> [--index] [--batch-size 500]` (S4B-B3b, US-030).

Rota la llave de una clase de dato y recifra sus filas de a lotes; reanudable (S4B-D39, D40, D63).
Usa `crypto_runtime`, un admin activo en `--as` y `core.crypto.service` (siempre por el módulo).

- `rotate-key: total=N` ANTES de empezar y `rotate-key: hecho=X/N` por lote; la última línea es
  `rotate-key: llave anterior en decrypt_only; retirar con retire-key` (retirar es otro comando).
- `--reason` obligatorio (<= 200 caracteres, sin control, correo ni números largos); queda en la
  auditoría (`update` sobre `crypto.crypto_keys`); ninguna salida lo repite.
- clase que cifra sin columnas ni puerto `Reencryptor`: 2 `rotation_not_supported` (S6-B1, D14).
- Candado de la clase tomado por otro proceso: 1, `rotación en curso`. `DatabaseBusy`: un intento y
  tres reintentos con `asyncio.sleep(1)`; luego 1. Falla en un lote: `failed`, 1, repetir reanuda.
- `--provider <local|openbao>` (solo `audit.signature`, S6-D81): llave de firma nueva allí; la
  anterior queda `decrypt_only`; sin él esa clase sale 2 `purpose_not_rotatable`.
- `--index` rota la llave de índice ciego y recalcula los `*_idx` en una sola transacción.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

import typer
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.core import audit, db
from app.core.config import Settings
from app.core.crypto import rotate_job, service
from app.core.crypto.errors import CryptoError
from app.core.crypto.models import CryptoJob
from app.core.crypto.registry import get_spec
from app.core.crypto.sign_rotation import SignRotationError, not_rotatable, switch_provider

COMMAND = "rotate-key"
AUDIT_TABLE = "crypto.crypto_keys"
RETRIES = rotate_job.RETRIES
WAIT_S = rotate_job.WAIT_S
MAX_BATCH_SIZE = 5000
FINAL = "llave anterior en decrypt_only; retirar con retire-key"
EMPTY_PASSES = rotate_job.EMPTY_PASSES


def _say(mensaje: str) -> None:
    typer.echo(f"{COMMAND}: {mensaje}")


def _stop(mensaje: str, code: int = 1) -> typer.Exit:
    typer.echo(f"{COMMAND}: {mensaje}", err=True)
    return typer.Exit(code=code)


async def _retry[T](operation: Callable[[], Awaitable[T]]) -> T:
    """Un intento y tres reintentos ante `DatabaseBusy` (`core.crypto.rotate_job.retry`)."""
    try:
        return await rotate_job.retry(operation)
    except rotate_job.RotationBusy:
        raise _stop("la base está ocupada; repita el comando en unos minutos") from None


async def _start(session: AsyncSession, data_class: str, reason: str, actor_id: UUID) -> CryptoJob:
    async with session.begin():
        job = await service.start_rotation(session, data_class, reason, actor_id)
        detalle = {"op": "rotate", "data_class": data_class, "reason": reason, "job": str(job.id)}
        await audit.record(
            session,
            action="update",
            table_name=AUDIT_TABLE,
            record_id=None,
            before=None,
            after=detalle,
            user_id=actor_id,
        )
    return job


async def _rotate_data(
    session: AsyncSession, data_class: str, reason: str, actor_id: UUID, size: int
) -> None:
    job = await _retry(lambda: _start(session, data_class, reason, actor_id))
    job_id, total, hecho = job.id, job.total, job.done  # tras un rollback el ORM expira
    _say(f"total={total}")
    if hecho:
        _say(f"reanudando desde hecho={hecho}/{total}")
    try:  # el bucle es el mismo de la pantalla (S6-R1, E5): sesiones propias, un lote por vez
        await rotate_job.execute_rotation(
            db.get_sessionmaker(),
            job_id,
            batch_size=size,
            on_progress=lambda hecho, total: _say(f"hecho={hecho}/{total}"),
        )
    except rotate_job.RotationBusy as error:
        if error.lock:
            raise service.RotationInProgress from None
        raise _stop("la base está ocupada; repita el comando en unos minutos") from None
    except rotate_job.RotationFailed as error:
        if error.code == "pending_records":
            raise _stop(
                "quedan filas con la llave anterior (bloqueadas por otra escritura); repita"
            ) from None
        raise _stop("un lote falló; repita el comando para reanudar el mismo job") from None


async def _rotate_index(
    session: AsyncSession, data_class: str, reason: str, actor_id: UUID
) -> None:
    async def una_transaccion() -> int:
        async with session.begin():
            filas = await service.rotate_index(session, data_class, reason, actor_id)
            detalle = {"op": "rotate_index", "data_class": data_class, "reason": reason}
            await audit.record(
                session,
                action="update",
                table_name=AUDIT_TABLE,
                record_id=None,
                before=None,
                after=detalle,
                user_id=actor_id,
            )
        return filas

    try:
        filas = await _retry(una_transaccion)
    except ValueError:
        raise _stop("--index se niega: la clase supera el tope de filas", 2) from None
    _say(f"índice rotado ({filas} filas)")


async def _rotate(
    settings: Settings,
    options: RuntimeOptions,
    data_class: str,
    reason: str,
    actor: str | None,
    index: bool,
    size: int,
    provider: str | None = None,
) -> None:
    async with crypto_runtime(settings, options) as session:
        async with session.begin():
            actor_id = await resolve_admin_actor(session, actor, required=True)
        with unit_of_work(actor_id):
            if provider:
                await switch_provider(session, settings, data_class, provider, reason, actor_id)
            elif index:
                await _rotate_index(session, data_class, reason, actor_id)
            else:
                await _rotate_data(session, data_class, reason, actor_id, size)


def _check_arguments(
    data_class: str, reason: str, index: bool, size: int, provider: str | None
) -> str:
    try:
        spec = get_spec(data_class)
    except CryptoError:
        reject("clase de dato desconocida", COMMAND)
    if (rechazo := not_rotatable(data_class, with_provider=provider is not None)) is not None:
        reject(rechazo, COMMAND)
    if not provider and (not spec.encrypt or (index and spec.index_kind is None)):
        reject("esa clase no admite este tipo de rotación", COMMAND)
    if not 1 <= size <= MAX_BATCH_SIZE:
        reject(f"--batch-size debe estar entre 1 y {MAX_BATCH_SIZE}", COMMAND)
    try:
        return service.validate_reason(reason)
    except ValueError as error:
        reject(f"--reason no es válido: {error}", COMMAND)


def register(app: typer.Typer) -> None:
    @app.command("rotate-key")
    def rotate_key_command(
        ctx: typer.Context,
        data_class: Annotated[
            str, typer.Argument(help="Clase de dato, por ejemplo member.document.")
        ],
        reason: Annotated[
            str, typer.Option("--reason", help="Motivo (sin datos personales).")
        ] = "",
        actor: Annotated[str | None, typer.Option("--as")] = None,
        index: Annotated[
            bool, typer.Option("--index", help="Rota la llave de índice ciego.")
        ] = False,
        batch_size: Annotated[int, typer.Option("--batch-size")] = service.BATCH_SIZE,
        provider: Annotated[str | None, typer.Option("--provider")] = None,
    ) -> None:
        """Rota la llave de una clase de dato y recifra sus filas (reanudable)."""
        settings, opciones = cli_base.get_settings(), runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        limpio = _check_arguments(data_class, reason, index, batch_size, provider)
        try:
            _run(
                _rotate(settings, opciones, data_class, limpio, actor, index, batch_size, provider)
            )
        except typer.Exit:
            raise
        except SignRotationError as error:  # solo los rechazos de --provider (texto fijo)
            raise _stop(str(error), 2) from None
        except service.RotationInProgress:
            raise _stop("rotación en curso en otro proceso; espere a que termine") from None
        except CryptoError as error:
            codigo = 2 if error.code == "rotation_not_supported" else 1
            raise _stop(f"error de llaves ({error.code})", codigo) from None
        _say(FINAL)
