"""`/docs`, `/redoc` y `/openapi.json` solo con `ENV=dev` (US-035 T5; N-14)."""

from __future__ import annotations

from pathlib import Path

from httpx import ASGITransport, AsyncClient

from app.cli import key_paths_in
from app.core.config import Settings, load_settings
from app.main import create_app


def _settings(tmp_path: Path, base: Settings, claves: Path, env: str) -> Settings:
    rutas = key_paths_in(claves)
    archivo = tmp_path / f".env.{env}"
    archivo.write_text(
        f"DATABASE_URL={base.DATABASE_URL.get_secret_value()}\n"
        f"JWT_PRIVATE_KEY_PATH={rutas.jwt_private}\nCRYPTO_PROVIDER=local\n"
        f"CRYPTO_LOCAL_KEK_PATH={rutas.kek}\nCRYPTO_LOCAL_SIGNING_KEY_PATH={rutas.signing_key}\n"
        f'UPLOADS_DIR=/data\nCORS_ORIGINS=["http://localhost"]\nENV={env}\n'
        "COOKIE_SECURE=true\n",  # M-9 (E3): producción exige la cookie Secure
        encoding="utf-8",
    )
    return load_settings(env_file=archivo)


async def test_docs_apagados_en_produccion_y_abiertos_en_dev(
    tmp_path: Path, settings_prueba: Settings, claves_prueba: Path
) -> None:
    produccion = create_app(
        _settings(tmp_path, settings_prueba, claves_prueba, "production"),
        run_migrations_on_startup=False,
    )
    async with AsyncClient(transport=ASGITransport(app=produccion), base_url="http://t") as c:
        for ruta in ("/docs", "/redoc", "/openapi.json"):
            assert (await c.get(ruta)).status_code == 404, ruta
    desarrollo = create_app(
        _settings(tmp_path, settings_prueba, claves_prueba, "dev"), run_migrations_on_startup=False
    )
    async with AsyncClient(transport=ASGITransport(app=desarrollo), base_url="http://t") as c:
        assert (await c.get("/openapi.json")).status_code == 200
        assert (await c.get("/docs")).status_code == 200
