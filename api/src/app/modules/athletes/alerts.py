"""Alertas del módulo `athletes` (S9-V7b, L5). Privado.

`safe_alert` es el único sitio donde `athletes` avisa al equipo: la alerta va en su propio `try`
(un canal caído o un contexto inválido nunca rompe la operación) y solo registra el tipo del error.
"""

from __future__ import annotations

import logging

from app.core.alerts import alert

logger = logging.getLogger("app.athletes")


def safe_alert(code: str, **context: object) -> None:
    """`alert(code, **context)` sin propagar fallos: el contexto lleva solo conteos, sin ids."""
    try:
        alert(code, **context)
    except Exception as error:
        logger.warning("athletes: alerta omitida", extra={"error_type": type(error).__name__})
