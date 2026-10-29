"""Alertas internas del equipo (US-113; S4A-D7, G-08).

- `AlertSink`: destino de una alerta (`send(code, context)`). En v0.1 solo `LogAlertSink`
  (`logger.error` de `app.alerts` con `code` y el contexto), registrado por defecto; Telegram
  (v0.2, N-34) agrega su sink sin tocar a los llamadores.
- `alert(code, **context)`: valida que cada clave del contexto esté en `ALERT_CONTEXT_KEYS`
  (conteos y nombres de job, nunca datos de personas; si no, `ValueError` antes de llamar a
  ningún sink) y llama a todos los sinks; un sink que lanza no propaga: se registra en el log de
  `app.alerts` y se sigue con el siguiente.
- `_sinks`: lista del proceso (las pruebas la fotografían y la restauran, como el bus).

No importa `app.modules` ni `core/audit`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Final, Protocol

logger = logging.getLogger("app.alerts")

ALERT_CONTEXT_KEYS: Final[frozenset[str]] = frozenset(
    {"job", "result", "error_type", "attempts", "run_date"}
)
"""Únicas claves de contexto admitidas (S4A-D7, precisión de S4A-D56 a D7)."""


class AlertSink(Protocol):
    """Destino de una alerta interna."""

    def send(self, code: str, context: Mapping[str, object]) -> None: ...


class LogAlertSink:
    """Escribe la alerta con `logger.error` (logger `app.alerts`): `code` y el contexto."""

    def send(self, code: str, context: Mapping[str, object]) -> None:
        logger.error("alert %s", code, extra={"alert_code": code, "alert_context": dict(context)})


_sinks: list[AlertSink] = [LogAlertSink()]


def register_sink(sink: AlertSink) -> None:
    """Agrega un sink al proceso."""
    _sinks.append(sink)


def _check_context(context: Mapping[str, object]) -> None:
    """Claves de `ALERT_CONTEXT_KEYS`, valores `str` o `int` y `error_type` como nombre de tipo
    (S4A-D82): un mensaje de excepción o un objeto con datos nunca llega a un canal."""
    ajenas = sorted(set(context) - ALERT_CONTEXT_KEYS)
    if ajenas:
        raise ValueError(f"alert: claves de contexto no admitidas: {ajenas}")
    for clave, valor in context.items():
        if not isinstance(valor, str | int):
            raise ValueError(f"alert: el valor de {clave} debe ser texto o entero")
    tipo = context.get("error_type")
    if isinstance(tipo, str) and not tipo.isidentifier():
        raise ValueError("alert: error_type debe ser el nombre de un tipo")


def alert(code: str, **context: object) -> None:
    """Valida el contexto (`_check_context`) y llama a todos los sinks."""
    _check_context(context)
    for sink in list(_sinks):
        try:
            sink.send(code, context)
        except Exception as error:
            # Solo el tipo: el mensaje de un canal caído podría traer la URL o un token.
            logger.warning(
                "alert sink failed",
                extra={"alert_code": code, "error_type": type(error).__name__},
            )
