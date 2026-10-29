"""`export-openapi` por la CLI real (`CliRunner`; S4A-D39: `cli.py` entra en la cobertura).

Sin variables del api, sin `.env` y sin base: el archivo escrito es el mismo JSON que
`build_openapi_document()` (`app.openapi()` con `info.version` del paquete), con claves ordenadas,
salto de línea final y sin `\\r\\n`; dos corridas dan los mismos bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cli import app, build_openapi_document
from app.core.config import NON_API_ENV_VARS, Settings, reset_settings_cache
from tests.cli._apoyo import correr

VARIABLES_DEL_API = [*Settings.model_fields, *sorted(NON_API_ENV_VARS)]


@pytest.fixture
def sin_entorno(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for nombre in VARIABLES_DEL_API:
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.chdir(tmp_path)
    reset_settings_cache()


def test_export_openapi_escribe_el_mismo_json_que_app_openapi(
    sin_entorno: None, tmp_path: Path
) -> None:
    destino = tmp_path / "salida" / "openapi.json"

    resultado = correr(app, ["export-openapi", str(destino)])

    assert resultado.exit_code == 0, resultado.output
    assert f"openapi: escrito {destino}" in resultado.output
    assert json.loads(destino.read_text(encoding="utf-8")) == build_openapi_document()


def test_export_openapi_es_determinista_y_con_fin_de_linea_unix(
    sin_entorno: None, tmp_path: Path
) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"

    primero = correr(app, ["export-openapi", str(a)])
    segundo = correr(app, ["export-openapi", str(b)])

    assert primero.exit_code == 0 and segundo.exit_code == 0
    datos = a.read_bytes()
    assert datos == b.read_bytes()
    assert datos.endswith(b"\n") and b"\r\n" not in datos
    texto = datos.decode("utf-8")
    assert (
        texto == json.dumps(json.loads(texto), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    )


def test_export_openapi_sin_ruta_es_error_de_uso(sin_entorno: None) -> None:
    resultado = correr(app, ["export-openapi"])

    assert resultado.exit_code == 2
