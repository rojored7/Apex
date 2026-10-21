"""Base de datos async, columnas comunes y sesión por petición (US-012). Stub: S0-B2."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped

from app.core.config import Settings

APP_SCHEMAS: tuple[str, ...] = ()


class Base(DeclarativeBase):
    pass


class CommonColumnsMixin:
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    created_by: Mapped[UUID]

    def __init__(self, **kwargs: Any) -> None:
        raise NotImplementedError


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None]


def create_engine_from(settings: Settings) -> AsyncEngine:
    raise NotImplementedError


def get_engine() -> AsyncEngine:
    raise NotImplementedError


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    raise NotImplementedError


def configure_sessionmaker(factory: async_sessionmaker[AsyncSession] | None) -> None:
    raise NotImplementedError


async def dispose_engine() -> None:
    raise NotImplementedError


async def get_session() -> AsyncIterator[AsyncSession]:
    raise NotImplementedError
    yield  # pragma: no cover
