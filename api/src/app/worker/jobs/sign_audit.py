"""Job diario `sign_audit`: firma la cadena de auditoría (S6-A2, US-141; S6-D8, D9, D42, D100).

`run(ctx)`:
1. mide el atraso (`core.audit_sign.late_hours` contra `current_clock()`); una sola alerta
   `audit_sign_late` por corrida;
2. cada intento carga el keyring SOLO con `CRYPTO_CLASSES` (`recovery.try_load`), firma con
   `sign_latest` (candado `4_270_004`) con `statement_timeout` acotado y confirma; el intento entero
   vence a los `ATTEMPT_TIMEOUT_S` y hace rollback (libera el candado);
3. custodio sellado, inalcanzable o intento vencido: primer intento y hasta tres reintentos con
   esperas `RETRY_WAITS_S` (por `sleep`); agotados, `ok=False` y `audit_sign_failed`;
4. `signature_unverifiable` y cualquier otro `CryptoError` no se reintentan (`attempts = 1`);
5. cadena rota: `ok=False`, `cadena_rota = 1`, `audit_chain_broken`; ni firma ni reintento.
Los `details` son enteros; las alertas y logs no llevan firmas ni hashes (solo tipo y conteos).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Final

from sqlalchemy.exc import DBAPIError

from app.core.alerts import alert
from app.core.audit_sign import SignOutcome, late_hours, limit_statement_time, sign_latest
from app.core.clock import current_clock
from app.core.config import get_settings
from app.core.crypto import recovery
from app.core.crypto.errors import CryptoError
from app.worker.registry import get_registry
from app.worker.runner import JobContext, JobResult

NAME: Final = "sign_audit"
CRYPTO_CLASSES: Final = frozenset({"audit.signature"})
RETRY_WAITS_S: Final = (2, 4, 8)
ATTEMPT_TIMEOUT_S: Final = 10
"""Tope por intento (S6-A1, aceptado con dueño A2): `statement_timeout` y el timeout del proveedor
no pasan de 10 s; un intento colgado vence, hace rollback y libera el candado 4_270_004."""
sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

UNAVAILABLE: Final = "crypto_unavailable"
ATTEMPT_TIMED_OUT: Final = "attempt_timeout"
DB_TIMEOUT: Final = "db_timeout"

logger = logging.getLogger("app.worker")

__all__ = ["ATTEMPT_TIMEOUT_S", "CRYPTO_CLASSES", "NAME", "RETRY_WAITS_S", "run", "sleep"]


class _Retryable(Exception):
    """Fallo que merece reintento; `code` es un nombre de tipo sin texto del proveedor."""

    def __init__(self, code: str, *, sealed: bool) -> None:
        super().__init__(code)
        self.code = code
        self.sealed = sealed


async def _attempt(ctx: JobContext) -> SignOutcome:
    estado = await recovery.try_load(
        ctx.session_factory, get_settings(), create_missing=False, classes=_classes()
    )
    if estado != "ok":
        raise _Retryable(UNAVAILABLE, sealed=True)
    try:
        async with ctx.session_factory() as session:
            await limit_statement_time(session, ATTEMPT_TIMEOUT_S)
            resultado = await sign_latest(session)
            await session.commit()
    except CryptoError as error:
        if error.code == UNAVAILABLE:
            raise _Retryable(UNAVAILABLE, sealed=True) from None
        raise
    return resultado


def _classes() -> frozenset[str]:
    """Las clases de su `JobSpec` (O11); sin registro, las del módulo."""
    return next((s.crypto_classes for s in get_registry() if s.name == NAME), CRYPTO_CLASSES)


async def _bounded_attempt(ctx: JobContext) -> SignOutcome:
    try:
        return await asyncio.wait_for(_attempt(ctx), ATTEMPT_TIMEOUT_S)
    except DBAPIError:  # statement_timeout, conexión caída: reintentable, nunca crudo al runner
        raise _Retryable(DB_TIMEOUT, sealed=False) from None
    except TimeoutError:
        raise _Retryable(ATTEMPT_TIMED_OUT, sealed=False) from None


def _failed(details: dict[str, int], error_type: str, attempts: int) -> JobResult:
    alert("audit_sign_failed", job=NAME, result="error", error_type=error_type, attempts=attempts)
    return JobResult(ok=False, details=details)


async def _late(ctx: JobContext) -> int | None:
    async with ctx.session_factory() as session:
        return await late_hours(session, current_clock().now_utc())


async def run(ctx: JobContext) -> JobResult:
    details = dict.fromkeys(
        ("firmadas", "nada_nuevo", "reintentos", "sellado", "atrasada", "cadena_rota"), 0
    )
    if (horas := await _late(ctx)) is not None:
        details["atrasada"] = 1
        alert("audit_sign_late", job=NAME, age_h=horas)
    reintentos = 0
    while True:
        try:
            resultado = await _bounded_attempt(ctx)
        except _Retryable as fallo:
            details["sellado"] = int(fallo.sealed or bool(details["sellado"]))
            if reintentos >= len(RETRY_WAITS_S):
                logger.warning("sign_audit: agotó los reintentos", extra={"attempts": reintentos})
                return _failed(details, fallo.code, reintentos)
            await sleep(RETRY_WAITS_S[reintentos])
            reintentos += 1
            details["reintentos"] = reintentos
            continue
        except CryptoError as error:
            logger.warning("sign_audit: intento fallido", extra={"error_code": error.code})
            return _failed(details, error.code, 1)
        break
    if resultado.kind == "chain_broken":
        details["cadena_rota"] = 1
        alert("audit_chain_broken", job=NAME, through_seq=resultado.through_seq)
        return JobResult(ok=False, details=details)
    details["firmadas" if resultado.kind == "signed" else "nada_nuevo"] = 1
    return JobResult(ok=True, details=details)
