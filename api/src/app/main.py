"""Punto de entrada del api: `create_app()` (US-020). Stub: S0-B4."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Final

from fastapi import APIRouter, FastAPI

from app.core.config import Settings

MODULES: Final[tuple[str, ...]] = ()
API_PREFIX = "/api/v1"
MIGRATION_LOCK_KEY: Final[int] = 0
StartupStep = Callable[[Settings], Awaitable[None]]


def register_startup_step(name: str, fn: StartupStep) -> None:
    raise NotImplementedError


def clear_startup_steps() -> None:
    raise NotImplementedError


def load_module_services() -> None:
    raise NotImplementedError


def include_module_routers(router: APIRouter) -> None:
    raise NotImplementedError


def run_migrations(settings: Settings, script_location: str | None = None) -> None:
    raise NotImplementedError


def create_app(
    settings: Settings | None = None,
    *,
    run_migrations_on_startup: bool = True,
    migrations_script_location: str | None = None,
) -> FastAPI:
    raise NotImplementedError


def __getattr__(name: str) -> Any:
    if name == "app":
        return create_app()
    raise AttributeError(name)
