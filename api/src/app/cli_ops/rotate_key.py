"""`rotate-key <clase> --reason TEXTO --as <correo> [--index] [--batch-size 500]` (S4B-B3b, US-030).

Rota la llave de una clase de dato y recifra sus filas de a lotes; es reanudable (S4B-D39, D40,
D63). Usa `crypto_runtime`, un admin activo en `--as` y `core.crypto.service` (siempre por el
módulo, para que las pruebas lo alcancen).

- `rotate-key: total=N` ANTES de empezar y `rotate-key: hecho=X/N` por lote; la última línea es
  `rotate-key: llave anterior en decrypt_only; retirar con retire-key` (retirar es otro comando).
- `--reason` obligatorio (<= 200 caracteres, sin control, correo ni números largos); queda en la
  auditoría (`update` sobre `crypto.crypto_keys`) en la misma transacción que abre la rotación.
  Ninguna salida repite el motivo recibido.
- `attachment.sensitive`: 2, `esa clase no admite rotación hasta EP-18 (G-09)`.
- Candado de la clase tomado por otro proceso: 1, `rotación en curso`.
- `DatabaseBusy`: un intento y tres reintentos con `asyncio.sleep(1)`; luego 1,
  `la base está ocupada`. No necesita `--db-timeouts off` (cada lote es corto).
- Falla en un lote: el job queda `failed`, 1, `repita el comando` para reanudar ese mismo job.
- `--index` rota la llave de índice ciego y recalcula los `*_idx` en una sola transacción.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
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
from app.core import audit
from app.core.config import Settings
from app.core.crypto import service
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import current_keyring
from app.core.crypto.models import CryptoJob
from app.core.crypto.registry import get_spec
from app.core.db import DatabaseBusy

COMMAND = "rotate-key"
AUDIT_TABLE = "crypto.crypto_keys"
ATTACHMENT_CLASS = "attachment.sensitive"
RETRIES = 3
WAIT_S = 1
MAX_BATCH_SIZE = 5000
FINAL = "llave anterior en decrypt_only; retirar con retire-key"
EMPTY_PASSES = 5


def _say(mensaje: str) -> None:
    typer.echo(f"{COMMAND}: {mensaje}")


def _stop(mensaje: str, code: int = 1) -> typer.Exit:
    typer.echo(f"{COMMAND}: {mensaje}", err=True)
    return typer.Exit(code=code)


async def _retry[T](operation: Callable[[], Awaitable[T]]) -> T:
    """Un intento y `RETRIES` reintentos ante `DatabaseBusy`, con espera de `WAIT_S` s."""
    for intento in range(RETRIES + 1):
        try:
            return await operation()
        except DatabaseBusy:
            if intento == RETRIES:
                break
            await asyncio.sleep(WAIT_S)
    raise _stop("la base está ocupada; repita el comando en unos minutos")


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


async def _in_job[T](
    session: AsyncSession, job_id: UUID, work: Callable[[CryptoJob], Awaitable[T]]
) -> tuple[T, int, int]:
    """Una transacción corta sobre el job (recargado): trabajo y su avance `(hecho, total)`."""
    async with session.begin():
        job = await session.get(CryptoJob, job_id, populate_existing=True)
        if job is None:
            raise _stop("el job de rotación no existe")
        resultado = await work(job)
        return resultado, job.done, job.total


async def _fail(job_id: UUID, error: Exception) -> typer.Exit:
    codigo = getattr(error, "code", None) or type(error).__name__
    with suppress(Exception):  # el job queda como estaba; el aviso sale igual
        await service.fail_job(job_id, str(codigo))
    return _stop("un lote falló; repita el comando para reanudar el mismo job")


async def _rotate_data(
    session: AsyncSession, data_class: str, reason: str, actor_id: UUID, size: int
) -> None:
    job = await _retry(lambda: _start(session, data_class, reason, actor_id))
    keyring = current_keyring()
    if keyring.resolver is not None:
        async with session.begin():
            await keyring.load_all(session, keyring.resolver)
    job_id, total, hecho = job.id, job.total, job.done  # tras un rollback el ORM expira
    _say(f"total={total}")
    if hecho:
        _say(f"reanudando desde hecho={hecho}/{total}")
    vacias = 0
    while True:
        try:
            n, done, total = await _retry(
                lambda: _in_job(
                    session, job_id, lambda j: service.reencrypt_batch(session, j, size)
                )
            )
        except typer.Exit:
            raise
        except Exception as error:
            raise await _fail(job_id, error) from None
        if n:
            _say(f"hecho={done}/{total}")
        if n >= size:
            continue
        cerrada, _, _ = await _retry(
            lambda: _in_job(session, job_id, lambda j: service.finish_rotation(session, j))
        )
        if cerrada:
            return
        vacias += 1  # filas saltadas por estar bloqueadas: se espera y se vuelve a pasar
        await asyncio.sleep(WAIT_S)
        if vacias >= EMPTY_PASSES:
            raise _stop(
                "quedan filas con la llave anterior (bloqueadas por otra escritura); repita"
            )


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
) -> None:
    async with crypto_runtime(settings, options) as session:
        async with session.begin():
            actor_id = await resolve_admin_actor(session, actor, required=True)
        with unit_of_work(actor_id):
            if index:
                await _rotate_index(session, data_class, reason, actor_id)
            else:
                await _rotate_data(session, data_class, reason, actor_id, size)


def _check_arguments(data_class: str, reason: str, index: bool, size: int) -> str:
    if data_class == ATTACHMENT_CLASS:
        reject("esa clase no admite rotación hasta EP-18 (G-09)", COMMAND)
    try:
        spec = get_spec(data_class)
    except CryptoError:
        reject("clase de dato desconocida", COMMAND)
    if not spec.encrypt or (index and spec.index_kind is None):
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
    ) -> None:
        """Rota la llave de una clase de dato y recifra sus filas (reanudable)."""
        settings, opciones = cli_base.get_settings(), runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        limpio = _check_arguments(data_class, reason, index, batch_size)
        try:
            _run(_rotate(settings, opciones, data_class, limpio, actor, index, batch_size))
        except typer.Exit:
            raise
        except service.RotationInProgress:
            raise _stop("rotación en curso en otro proceso; espere a que termine") from None
        except CryptoError as error:
            raise _stop(f"error de llaves ({error.code})") from None
        _say(FINAL)
