"""`parse_origins` y CORS cerrado en `create_app` (US-037 T4, T5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.cli import key_paths_in
from app.core.config import ConfigError, Settings, load_settings, parse_origins
from app.main import create_app


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("http://apex.local", ["http://apex.local"]),
        (" http://a.local , https://b.local:8443 ", ["http://a.local", "https://b.local:8443"]),
        ("", []),
        ("   ", []),
        ('["http://localhost"]', ["http://localhost"]),
        ("http://a.local,http://a.local", ["http://a.local"]),
        ("http://a.local/", ["http://a.local"]),
    ],
)
def test_parse_origins(valor: str, esperado: list[str]) -> None:
    assert parse_origins(valor) == esperado


@pytest.mark.parametrize(
    "valor",
    ["*", "null", "http://a.local/ruta", "apex.local", "http://a.local?x=1", "ftp://a.local"],
)
def test_parse_origins_rechaza(valor: str) -> None:
    with pytest.raises(ValueError):
        parse_origins(valor)


def _settings(tmp_path: Path, base: Settings, claves: Path, origins: str) -> Settings:
    rutas = key_paths_in(claves)
    archivo = tmp_path / ".env.cors"
    archivo.write_text(
        f"DATABASE_URL={base.DATABASE_URL.get_secret_value()}\n"
        f"JWT_PRIVATE_KEY_PATH={rutas.jwt_private}\nCRYPTO_PROVIDER=local\n"
        f"CRYPTO_LOCAL_KEK_PATH={rutas.kek}\nCRYPTO_LOCAL_SIGNING_KEY_PATH={rutas.signing_key}\n"
        f"UPLOADS_DIR=/data\nCORS_ORIGINS={origins}\nENV=dev\n",
        encoding="utf-8",
    )
    return load_settings(env_file=archivo)


async def _preflight(app: object, origen: str) -> dict[str, str]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:  # type: ignore[arg-type]
        r = await c.options(
            "/api/v1/health",
            headers={"Origin": origen, "Access-Control-Request-Method": "POST"},
        )
    return {k.lower(): v for k, v in r.headers.items()}


async def test_preflight_solo_para_el_origen_permitido(
    tmp_path: Path, settings_prueba: Settings, claves_prueba: Path
) -> None:
    app = create_app(
        _settings(tmp_path, settings_prueba, claves_prueba, "http://apex.local"),
        run_migrations_on_startup=False,
    )
    permitido = await _preflight(app, "http://apex.local")
    assert permitido["access-control-allow-origin"] == "http://apex.local"
    assert "access-control-allow-credentials" not in permitido
    ajeno = await _preflight(app, "https://evil.example")
    assert "access-control-allow-origin" not in ajeno


async def test_sin_origenes_no_hay_cors(
    tmp_path: Path, settings_prueba: Settings, claves_prueba: Path
) -> None:
    app = create_app(
        _settings(tmp_path, settings_prueba, claves_prueba, ""), run_migrations_on_startup=False
    )
    assert "access-control-allow-origin" not in await _preflight(app, "http://apex.local")


def test_asterisco_hace_fallar_la_configuracion(
    tmp_path: Path, settings_prueba: Settings, claves_prueba: Path
) -> None:
    with pytest.raises(ConfigError) as excinfo:
        _settings(tmp_path, settings_prueba, claves_prueba, "*")
    assert "CORS_ORIGINS" in str(excinfo.value)
