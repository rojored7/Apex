"""`core/alerts.py` (US-113; S4A-D7, precisión de S4A-D56 a D7).

- `register_sink` agrega un sink y `alert(code, **context)` llama a todos, en orden;
- un sink que lanza no propaga: el siguiente igual recibe la alerta y el fallo queda en el log de
  `app.alerts`;
- `LogAlertSink` (registrado por defecto) escribe `logger.error` en `app.alerts` con el código y el
  contexto;
- una clave de contexto fuera de `ALERT_CONTEXT_KEYS` lanza `ValueError` antes de llamar a ningún
  sink (así un documento o un nombre nunca llega a un canal);
- `core/alerts.py` no importa `app.modules` ni `core/audit`.
`sinks_aislados` fotografía `alerts._sinks` y la restaura al salir (como `restaurar_bus`).
"""

from __future__ import annotations

import ast
import logging
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from app.core import alerts
from app.core.alerts import ALERT_CONTEXT_KEYS, LogAlertSink, alert, register_sink

ALERTS_PY = Path(alerts.__file__)


class SinkEspia:
    def __init__(self, nombre: str, bitacora: list[tuple[str, str, dict[str, object]]]) -> None:
        self.nombre = nombre
        self.bitacora = bitacora

    def send(self, code: str, context: Mapping[str, object]) -> None:
        self.bitacora.append((self.nombre, code, dict(context)))


class SinkRoto:
    def send(self, code: str, context: Mapping[str, object]) -> None:
        raise RuntimeError("canal caído")


@pytest.fixture
def sinks_aislados() -> Iterator[None]:
    foto = list(alerts._sinks)
    alerts._sinks[:] = []
    try:
        yield
    finally:
        alerts._sinks[:] = foto


def _texto(registro: logging.LogRecord) -> str:
    return registro.getMessage() + " " + str(vars(registro))


def test_las_claves_de_contexto_son_las_del_plan() -> None:
    assert frozenset({"job", "result", "error_type", "attempts", "run_date"}) == ALERT_CONTEXT_KEYS


def test_log_alert_sink_esta_registrado_por_defecto() -> None:
    assert any(isinstance(s, LogAlertSink) for s in alerts._sinks)


def test_alert_llama_a_todos_los_sinks_en_orden(sinks_aislados: None) -> None:
    bitacora: list[tuple[str, str, dict[str, object]]] = []
    register_sink(SinkEspia("a", bitacora))
    register_sink(SinkEspia("b", bitacora))

    alert("job_failed", job="expirations", result="error", error_type="RuntimeError")

    contexto = {"job": "expirations", "result": "error", "error_type": "RuntimeError"}
    assert bitacora == [("a", "job_failed", contexto), ("b", "job_failed", contexto)]


def test_un_sink_que_lanza_no_propaga_y_queda_en_el_log(
    sinks_aislados: None, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="app.alerts")
    bitacora: list[tuple[str, str, dict[str, object]]] = []
    register_sink(SinkRoto())
    register_sink(SinkEspia("despues", bitacora))

    alert("job_failed", job="expirations", result="error")

    assert [n for n, _, _ in bitacora] == ["despues"]
    del_modulo = [r for r in caplog.records if r.name == "app.alerts"]
    assert del_modulo, "el fallo del sink no quedó registrado"
    assert any(r.levelno >= logging.WARNING for r in del_modulo)


def test_log_alert_sink_escribe_error_con_codigo_y_contexto(
    sinks_aislados: None, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="app.alerts")
    register_sink(LogAlertSink())

    alert("job_failed", job="expirations", result="error", error_type="TimeoutError", attempts=2)

    errores = [r for r in caplog.records if r.name == "app.alerts" and r.levelno == logging.ERROR]
    assert len(errores) == 1
    texto = _texto(errores[0])
    for valor in ("job_failed", "expirations", "TimeoutError"):
        assert valor in texto


def test_clave_fuera_de_la_lista_lanza_sin_llamar_a_ningun_sink(
    sinks_aislados: None,
) -> None:
    bitacora: list[tuple[str, str, dict[str, object]]] = []
    register_sink(SinkEspia("a", bitacora))

    with pytest.raises(ValueError):
        alert("job_failed", job="expirations", documento="1020304417")

    assert bitacora == []


def test_sin_contexto_tambien_es_valido(sinks_aislados: None) -> None:
    bitacora: list[tuple[str, str, dict[str, object]]] = []
    register_sink(SinkEspia("a", bitacora))

    alert("worker_started")

    assert bitacora == [("a", "worker_started", {})]


def test_core_alerts_no_importa_modulos_ni_audit() -> None:
    arbol = ast.parse(ALERTS_PY.read_text(encoding="utf-8"))
    nombres = [a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names] + [
        n.module or "" for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)
    ]
    assert [n for n in nombres if n.startswith(("app.modules", "app.core.audit"))] == []


@pytest.mark.parametrize(
    "contexto",
    [
        {"job": "expirations", "error_type": "documento 1020304417"},
        {"job": "expirations", "error_type": "RuntimeError: documento"},
        {"job": {"socio": "Laura"}},
        {"attempts": [1, 2]},
        {"run_date": None},
        {"result": 1.5},
    ],
    ids=["error_type_con_mensaje", "tipo_y_mensaje", "dict", "lista", "none", "decimal"],
)
def test_valores_que_no_son_texto_entero_o_nombre_de_tipo_se_rechazan(
    sinks_aislados: None, contexto: dict[str, object]
) -> None:
    bitacora: list[tuple[str, str, dict[str, object]]] = []
    register_sink(SinkEspia("a", bitacora))

    with pytest.raises(ValueError):
        alert("job_failed", **contexto)

    assert bitacora == []


def test_valores_de_texto_y_enteros_pasan(sinks_aislados: None) -> None:
    bitacora: list[tuple[str, str, dict[str, object]]] = []
    register_sink(SinkEspia("a", bitacora))

    alert("job_failed", job="expirations", attempts=3, run_date="2026-10-21", error_type="OSError")

    assert len(bitacora) == 1
