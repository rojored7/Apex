"""Punto de entrada del api.

Marcador mínimo (US-005, T1) para que `uvicorn app.main:app` arranque dentro del
contenedor antes de US-020. Reemplazado por `create_app()` en US-020.
"""

from fastapi import FastAPI

app = FastAPI(title="APEX")
