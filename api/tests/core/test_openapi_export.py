"""Exportación de OpenAPI sin `.env`, base ni llaves (US-021 T4)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.cli import build_openapi_document, export_settings, write_openapi
from app.core.config import NON_API_ENV_VARS, Settings, reset_settings_cache
from app.main import API_PREFIX

API_ROOT = Path(__file__).resolve().parents[2]
COMANDO = "cd api && uv run python -m app.cli export-openapi ../docs/openapi.json"
VARIABLES_DEL_API = [nombre for nombre in Settings.model_fields] + sorted(NON_API_ENV_VARS)


@pytest.fixture
def sin_entorno(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Sin variables del api, sin `.env` en el directorio actual y sin caché de Settings."""
    for nombre in VARIABLES_DEL_API:
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.chdir(tmp_path)
    reset_settings_cache()


def test_dos_exportaciones_son_identicas_byte_a_byte(sin_entorno: None, tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    write_openapi(build_openapi_document(), a)
    write_openapi(build_openapi_document(), b)
    assert a.read_bytes() == b.read_bytes()
    assert a.read_bytes().endswith(b"\n") and b"\r\n" not in a.read_bytes()


def test_el_documento_tiene_error_response_y_rutas_bajo_api_v1(sin_entorno: None) -> None:
    doc = build_openapi_document()
    assert "ErrorResponse" in doc["components"]["schemas"]
    assert "HTTPValidationError" not in doc["components"]["schemas"]
    fuera = [r for r in doc["paths"] if not r.startswith(API_PREFIX) and r != "/health"]
    assert fuera == []
    assert f"{API_PREFIX}/health" in doc["paths"]


def test_info_version_no_depende_de_app_version(sin_entorno: None) -> None:
    assert export_settings().APP_VERSION != build_openapi_document()["info"]["version"]
    assert build_openapi_document()["info"]["version"] != "dev"


def test_los_marcadores_no_aparecen_en_el_documento(sin_entorno: None, tmp_path: Path) -> None:
    salida = tmp_path / "openapi.json"
    write_openapi(build_openapi_document(), salida)
    texto = salida.read_text(encoding="utf-8")
    assert export_settings().DATABASE_URL.get_secret_value() not in texto
    assert "export-no-secret" not in texto


def test_el_comando_cli_escribe_el_archivo(sin_entorno: None, tmp_path: Path) -> None:
    salida = tmp_path / "contrato.json"
    entorno = {k: v for k, v in os.environ.items() if k not in VARIABLES_DEL_API}
    resultado = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.cli", "export-openapi", str(salida)],
        cwd=API_ROOT,
        env=entorno,
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert salida.is_file()
    write_openapi(build_openapi_document(), tmp_path / "ref.json")
    assert salida.read_bytes() == (tmp_path / "ref.json").read_bytes()


def test_docs_openapi_json_esta_al_dia(sin_entorno: None, tmp_path: Path) -> None:
    """Lo mismo que el paso de CI: el archivo versionado coincide con la exportación."""
    versionado = API_ROOT.parent / "docs" / "openapi.json"
    assert versionado.is_file(), f"falta docs/openapi.json. Corra: {COMANDO}"
    write_openapi(build_openapi_document(), tmp_path / "actual.json")
    assert versionado.read_bytes() == (tmp_path / "actual.json").read_bytes(), (
        f"docs/openapi.json está desactualizado. Corra: {COMANDO}"
    )
