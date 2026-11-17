"""Fachada del service de `athletes` (S9-A1). Lo único que importan los demás módulos."""

from __future__ import annotations

from app.modules.athletes.events import PersonalRecordSet
from app.modules.athletes.metrics import add_metric, list_metrics, reveal_metric, void_metric
from app.modules.athletes.records import add_record, list_records

__all__ = [
    "PersonalRecordSet",
    "add_metric",
    "add_record",
    "list_metrics",
    "list_records",
    "reveal_metric",
    "void_metric",
]
