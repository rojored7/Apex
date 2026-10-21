"""Comandos del api (`python -m app.cli`; en Compose, `docker compose run --rm tools <cmd>`).

- `export-openapi <ruta>` (US-021): construye `create_app()` con una configuración de
  exportación (sin `.env`, sin base y sin llaves), llama a `app.openapi()` y escribe JSON
  con claves ordenadas, sangría de 2 y salto de línea final. `info.version` es la versión
  del paquete, no `APP_VERSION`, para que la salida no cambie con cada commit. No escribe
  en tablas, así que no necesita actor.

Comandos siguientes: `init-keys` (US-023), `seed --as` (US-041), `import-members`,
`rotate-key`, `sign-audit`. Todo comando que escriba tablas acepta `--as <email>` (N-15).
"""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import typer
from pydantic import SecretStr

from app.core.config import Settings

PACKAGE_NAME = "apex-api"

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
    """Comandos de APEX. Con un solo comando, Typer exige el callback para usar subcomandos."""


def export_settings() -> Settings:
    """`Settings` sin validar, con marcadores que no son secretos y no llegan al documento."""
    return Settings.model_construct(
        DATABASE_URL=SecretStr("postgresql+asyncpg://export-no-secret@localhost/export"),
        JWT_PRIVATE_KEY_PATH=Path("export-no-secret.pem"),
        JWT_PUBLIC_KEY_PATH=None,
        CRYPTO_PROVIDER="local",
        CRYPTO_LOCAL_KEK_PATH=Path("export-no-secret.bin"),
        ENV="dev",
        TZ_DISPLAY="America/Bogota",
        UPLOADS_DIR=Path("export-uploads"),
        CORS_ORIGINS=[],
        LOG_LEVEL="WARNING",
        TRUSTED_PROXIES="",
        COOKIE_SECURE=False,
        FRONT_BASE_URL="http://localhost",
        APP_VERSION="export",
    )


def _package_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:  # pragma: no cover - solo sin instalar el paquete
        return "0.0.0"


def build_openapi_document() -> dict[str, Any]:
    """El contrato, desde el código: no entra al `lifespan` ni abre conexiones."""
    from app.main import create_app  # import perezoso: el CLI arranca rápido sin la app

    aplicacion = create_app(export_settings(), run_migrations_on_startup=False)
    doc = aplicacion.openapi()
    doc["info"]["version"] = _package_version()
    return doc


def write_openapi(doc: dict[str, Any], output: Path) -> None:
    """JSON determinista: claves ordenadas, sangría de 2, UTF-8 y fin de línea `\\n`."""
    texto = json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as archivo:
        archivo.write(texto)


@app.command("export-openapi")
def export_openapi(output: Path) -> None:
    """Exporta el contrato OpenAPI a `output`, sin `.env`, base ni llaves."""
    write_openapi(build_openapi_document(), output)
    typer.echo(f"openapi: escrito {output}")


if __name__ == "__main__":
    app()
