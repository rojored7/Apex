"""Fachada del service de `athletes` (S9-A1). Lo único que importan los demás módulos."""

from __future__ import annotations

from app.modules.athletes.metrics import add_metric, list_metrics, reveal_metric, void_metric

__all__ = ["add_metric", "list_metrics", "reveal_metric", "void_metric"]
