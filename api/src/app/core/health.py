"""Comprobaciones de salud y `GET /health` (US-020). Stub: S0-B4."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

CheckResult = Literal["ok", "down", "unknown"]
CheckFn = Callable[[], Awaitable[CheckResult]]


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    db: CheckResult
    version: str


def register_health_check(name: str, fn: CheckFn, *, critical: bool) -> None:
    raise NotImplementedError


def clear_health_checks() -> None:
    raise NotImplementedError


async def health_status(version: str) -> tuple[int, HealthOut]:
    raise NotImplementedError


router = APIRouter()
