"""Fábrica de app para la prueba de arranque fallido (US-020, T8).

La invoca `uvicorn tests.core._app_rota:crear --factory` con la carpeta de
migraciones rota en `APEX_TEST_MIGRATIONS`.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from app.main import create_app


def crear() -> FastAPI:
    return create_app(migrations_script_location=os.environ["APEX_TEST_MIGRATIONS"])
