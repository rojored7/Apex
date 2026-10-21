"""El marcador de `app.main` expone una app de FastAPI (US-005, T2).

US-020 reemplaza esta prueba por las de `create_app()`.
"""

from fastapi import FastAPI

from app.main import app


def test_app_es_fastapi() -> None:
    assert isinstance(app, FastAPI)
    assert app.title == "APEX"
