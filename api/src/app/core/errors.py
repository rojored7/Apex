"""Envelope único de errores (US-017). Stub: se implementa en S0-B3."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    field: str | None = None
    existing_id: UUID | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class DomainError(Exception):
    status: int = 400
    code: str = "domain_error"

    def __init__(
        self,
        code: str | None = None,
        message: str = "",
        *,
        field: str | None = None,
        existing_id: UUID | None = None,
        status: int | None = None,
    ) -> None:
        raise NotImplementedError


class UnauthorizedError(DomainError):
    status = 401
    code = "unauthorized"


class ForbiddenError(DomainError):
    status = 403
    code = "forbidden"


class NotFoundError(DomainError):
    status = 404
    code = "not_found"


class ConflictError(DomainError):
    status = 409
    code = "conflict"


class ValidationFailed(DomainError):
    status = 422
    code = "validation_error"


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {}


def validation_field(errors: Sequence[Mapping[str, Any]]) -> str | None:
    raise NotImplementedError


def register_error_handlers(app: FastAPI) -> None:
    raise NotImplementedError
