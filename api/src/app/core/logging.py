"""Logs JSON a stdout sin datos sensibles (US-018). Stub: se implementa en S0-B3."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.core.config import Settings

SENSITIVE_KEYS: frozenset[str] = frozenset()


def redact(record: Mapping[str, Any]) -> dict[str, Any]:
    raise NotImplementedError


def redact_text(text: str) -> str:
    raise NotImplementedError


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        raise NotImplementedError


def configure_logging(settings: Settings) -> None:
    raise NotImplementedError


class RequestLogMiddleware:
    def __init__(self, app: Any) -> None:
        raise NotImplementedError
