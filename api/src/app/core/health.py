"""Comprobaciones de salud y `GET /health` (US-020; N-16).

`/health` va en la raíz (healthcheck del contenedor) y bajo `/api/v1` (por Nginx).
No lleva rol. Devuelve solo `status`, `db`, `version` y el resultado de cada
comprobación registrada: `critical=True` baja la respuesta a 503 (OpenBao sellado,
US-136); `critical=False` es informativa y mantiene el 200 (backup, US-115).
Nunca expone configuración, trazas ni errores internos.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.core.db import get_engine

CheckResult = Literal["ok", "down", "unknown"]
CheckFn = Callable[[], Awaitable[CheckResult]]
DB_TIMEOUT_S = 2.0

logger = logging.getLogger("app.health")


@dataclass(frozen=True)
class _Check:
    name: str
    fn: CheckFn
    critical: bool


_checks: dict[str, _Check] = {}


def register_health_check(name: str, fn: CheckFn, *, critical: bool) -> None:
    _checks[name] = _Check(name=name, fn=fn, critical=critical)


def clear_health_checks() -> None:
    """Solo para pruebas."""
    _checks.clear()


class HealthOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Literal["ok", "degraded"]
    db: CheckResult
    version: str


async def check_db() -> CheckResult:
    """`SELECT 1` con límite de 2 s: una base caída responde en menos de 3 s."""
    try:
        async with asyncio.timeout(DB_TIMEOUT_S), get_engine().connect() as conexion:
            await conexion.execute(text("SELECT 1"))
    except Exception:
        logger.warning("health: la base de datos no responde")
        return "down"
    return "ok"


async def _correr(check: _Check) -> CheckResult:
    try:
        return await check.fn()
    except Exception:
        logger.warning("health: la comprobación %s falló", check.name)
        return "unknown"


async def health_status(version: str) -> tuple[int, HealthOut]:
    db = await check_db()
    degradado = db != "ok"
    extras: dict[str, CheckResult] = {}
    for check in list(_checks.values()):
        resultado = await _correr(check)
        extras[check.name] = resultado
        if check.critical and resultado != "ok":
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
