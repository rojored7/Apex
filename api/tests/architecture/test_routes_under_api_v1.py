"""Toda ruta de la app vive bajo `/api/v1`, salvo `/health` (US-020, T10).

La parte que verifica que `worker/main.py` y `cli.py` llaman a
`load_module_services()` e `install_audit_listeners()` se activa cuando existan
(US-113 y US-041).
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from app.core.config import Settings
from app.main import API_PREFIX, create_app

PERMITIDAS_FUERA = {"/health"}


def test_rutas_bajo_api_v1(settings_prueba: Settings) -> None:
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    fuera = [
        r.path
        for r in app.routes
        if isinstance(r, APIRoute)
        and not r.path.startswith(API_PREFIX)
        and r.path not in PERMITIDAS_FUERA
    ]
    assert fuera == []
    rutas = {r.path for r in app.routes if isinstance(r, APIRoute)}
    assert {"/health", f"{API_PREFIX}/health"} <= rutas
