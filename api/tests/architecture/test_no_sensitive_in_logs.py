"""Ningún dato sensible en claro en los logs de un flujo real (US-018, T8).

Centinela de extremo a extremo: login (US-042, Sprint 1), crear socio (US-069,
Sprint 2) y revelar un dato (US-074, Sprint 3) con captura de stdout. Hasta que
existan esas rutas queda saltada con dueña explícita; la unitaria de redacción
(`tests/core/test_logging_redact.py`) ya corre.
"""

from __future__ import annotations

import importlib.util

import pytest


def _existe(modulo: str) -> bool:
    try:
        return importlib.util.find_spec(modulo) is not None
    except ModuleNotFoundError:
        return False


RUTAS_LISTAS = _existe("app.modules.auth.router") and _existe("app.modules.members.router")


@pytest.mark.skipif(not RUTAS_LISTAS, reason="se activa con US-042, US-069 y US-074")
async def test_login_crear_socio_y_reveal_no_dejan_datos_en_logs() -> None:
    raise AssertionError("implementar al activar: token, documento y blob ausentes del stdout")
