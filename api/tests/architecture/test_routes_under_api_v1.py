"""Toda ruta publicada vive bajo `/api/v1`, salvo `/health` (US-020, T10).

FastAPI incluye los routers de forma perezosa (`_IncludedRouter`), así que las
rutas efectivas se leen del OpenAPI, que es la vista pública. La parte que verifica
que `worker/main.py` y `cli.py` llaman a `load_module_services()` e
`install_audit_listeners()` se activa cuando existan (US-113 y US-041).
"""

from __future__ import annotations

from app.core.config import Settings
from app.main import API_PREFIX, create_app

PERMITIDAS_FUERA = {"/health"}


def test_rutas_bajo_api_v1(settings_prueba: Settings) -> None:
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    rutas = set(app.openapi()["paths"])
    fuera = sorted(r for r in rutas if not r.startswith(API_PREFIX) and r not in PERMITIDAS_FUERA)
    assert fuera == []
    assert {"/health", f"{API_PREFIX}/health"} <= rutas
