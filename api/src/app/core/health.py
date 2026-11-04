"""Comprobaciones de salud y `GET /health` (US-020; N-16).

`/health` va en la raíz (healthcheck del contenedor) y bajo `/api/v1` (por Nginx).
No lleva rol. Devuelve solo `status`, `db`, `version` y el resultado de cada
comprobación registrada: `critical=True` baja la respuesta a 503 (OpenBao sellado,
US-136); `critical=False` es informativa y mantiene el 200 (backup, US-115).
Nunca expone configuración, trazas ni errores internos.

S4B-B2 (S4B-D60, S4B-D91): cada comprobación tiene `allowed` (valores públicos admitidos; uno
ajeno se degrada a `unknown`, nunca a 500) y `healthy` (los que no bajan el 200 de una crítica), y
su resultado se guarda en una caché en proceso con TTL en `HEALTH_CACHE_TTL_S` (medido con
`current_clock()`) y un `asyncio.Lock` por comprobación: N peticiones simultáneas ejecutan el check
una sola vez. `HealthOut.backup` es `ok | attention | unknown` (por defecto `unknown`); el detalle
de seis estados nunca sale en el cuerpo público. `clear_health_cache()` reinicia la caché (pruebas).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.core.clock import current_clock
from app.core.db import get_engine

CheckResult = Literal["ok", "down", "unknown"]
CheckFn = Callable[[], Awaitable[str]]
DB_TIMEOUT_S = 2.0
HEALTH_CACHE_TTL_S: Final[dict[str, float]] = {"db": 2.0, "backup": 30.0, "migrations": 30.0}
"""Segundos que vive el resultado de cada comprobación en la caché (S4B-D60); una comprobación
sin entrada aquí no se cachea."""
DEFAULT_ALLOWED: Final[frozenset[str]] = frozenset({"ok", "down", "unknown"})
DEFAULT_HEALTHY: Final[frozenset[str]] = frozenset({"ok"})

logger = logging.getLogger("app.health")


@dataclass(frozen=True)
class _Check:
    name: str
    fn: CheckFn
    critical: bool
    allowed: frozenset[str] = DEFAULT_ALLOWED
    healthy: frozenset[str] = DEFAULT_HEALTHY


_checks: dict[str, _Check] = {}


def register_health_check(
    name: str,
    fn: CheckFn,
    *,
    critical: bool,
    allowed: frozenset[str] | set[str] = DEFAULT_ALLOWED,
    healthy: frozenset[str] | set[str] = DEFAULT_HEALTHY,
) -> None:
    """Registra una comprobación. `allowed`: valores que puede mostrar `/health`
    (otro -> `unknown`);
    `healthy`: valores con los que una crítica no baja el 200."""
    _checks[name] = _Check(
        name=name,
        fn=fn,
        critical=critical,
        allowed=frozenset(allowed),
        healthy=frozenset(healthy),
    )


@dataclass(frozen=True)
class _CacheEntry:
    value: str
    expires_at: datetime


_cache: dict[str, _CacheEntry] = {}
_locks: dict[str, asyncio.Lock] = {}


def clear_health_cache() -> None:
    """Vacía la caché y los candados de las comprobaciones (solo pruebas, S4B-D60)."""
    _cache.clear()
    _locks.clear()


def clear_health_checks() -> None:
    """Solo para pruebas."""
    _checks.clear()


class HealthOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Literal["ok", "degraded"]
    db: CheckResult
    version: str
    # S4B-B2 (S4B-D60): estado colapsado de los respaldos; el detalle de seis valores no sale.
    backup: Literal["ok", "attention", "unknown"] = "unknown"
    # S4B-B4 (S4B-D27, S4B-D60): `ok` en head, `mismatch` detrás o delante, `unknown` sin lectura.
    migrations: Literal["ok", "mismatch", "unknown"] = "unknown"


async def check_db() -> CheckResult:
    """`SELECT 1` con límite de 2 s: una base caída responde en menos de 3 s."""
    try:
        async with asyncio.timeout(DB_TIMEOUT_S), get_engine().connect() as conexion:
            await conexion.execute(text("SELECT 1"))
    except Exception:
        logger.warning("health: la base de datos no responde")
        return "down"
    return "ok"


async def check_db_cacheado() -> CheckResult:
    """`check_db` con la caché de 2 s (S4B-D60)."""
    return "ok" if await _con_cache("db", check_db) == "ok" else "down"


async def _con_cache(name: str, producir: Callable[[], Awaitable[str]]) -> str:
    """Resultado de `producir` con TTL de `HEALTH_CACHE_TTL_S` y un candado por comprobación.

    N peticiones simultáneas ejecutan la comprobación una sola vez (S4B-D60); sin TTL no se cachea.
    """
    ttl = HEALTH_CACHE_TTL_S.get(name)
    if ttl is None:
        return await producir()
    entrada = _cache.get(name)
    if entrada is not None and current_clock().now_utc() < entrada.expires_at:
        return entrada.value
    async with _locks.setdefault(name, asyncio.Lock()):
        entrada = _cache.get(name)
        if entrada is not None and current_clock().now_utc() < entrada.expires_at:
            return entrada.value
        valor = await producir()
        _cache[name] = _CacheEntry(valor, current_clock().now_utc() + timedelta(seconds=ttl))
        return valor


async def _ejecutar(check: _Check) -> str:
    try:
        resultado = await check.fn()
    except Exception:
        logger.warning("health: la comprobación %s falló", check.name)
        return "unknown"
    if resultado not in check.allowed:
        logger.warning("health: la comprobación %s devolvió un valor no admitido", check.name)
        return "unknown"
    return resultado


async def _correr(check: _Check) -> str:
    return await _con_cache(check.name, lambda: _ejecutar(check))


async def health_status(version: str) -> tuple[int, HealthOut]:
    registradas = list(_checks.values())
    # En paralelo: con la base caída el total sigue acotado por el mayor de los topes (< 3 s).
    db, *resultados = await asyncio.gather(
        check_db_cacheado(), *(_correr(check) for check in registradas)
    )
    degradado = db != "ok"
    extras: dict[str, str] = {}
    for check, resultado in zip(registradas, resultados, strict=True):
        extras[check.name] = resultado
        if check.critical and resultado not in check.healthy:
            degradado = True
    salida = HealthOut.model_validate(
        {"status": "degraded" if degradado else "ok", "db": db, "version": version, **extras}
    )
    return (503 if degradado else 200), salida


router = APIRouter(tags=["salud"])


@router.get(
    "/health",
    response_model=HealthOut,
    responses={503: {"model": HealthOut, "description": "Degradado"}},
    summary="Estado del api",
)
async def health(request: Request) -> JSONResponse:
    version = str(getattr(request.app.state, "settings").APP_VERSION)  # noqa: B009
    status, cuerpo = await health_status(version)
    return JSONResponse(status_code=status, content=cuerpo.model_dump())
