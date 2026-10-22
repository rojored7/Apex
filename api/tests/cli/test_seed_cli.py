"""`cli seed` (US-041 T11, T14): códigos de salida, sin contraseña en la salida y `--as`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from typer.testing import CliRunner

from app.cli import app, key_paths_in
from app.core.config import Settings, reset_settings_cache
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.security import configure_password_hasher
from app.modules.auth.models import User

runner = CliRunner()
CLAVE = "Zanahoria-Lunar-42x"


async def _limpiar_usuarios(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM auth.refresh_tokens"))
        await conn.execute(text("DELETE FROM auth.one_time_tokens"))
        await conn.execute(text("DELETE FROM auth.users WHERE id <> :s"), {"s": SYSTEM_USER_ID})
        await conn.execute(text("ALTER TABLE audit.audit_log DISABLE TRIGGER USER"))
        await conn.execute(text("DELETE FROM audit.audit_log"))
        await conn.execute(text("ALTER TABLE audit.audit_log ENABLE TRIGGER USER"))


@pytest.fixture
async def entorno(
    engine: AsyncEngine,
    settings_prueba: Settings,
    claves_prueba: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncEngine]:
    """Variables del api en el entorno (sin .env en cwd) y usuarios limpios con commit real."""
    rutas = key_paths_in(claves_prueba)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", settings_prueba.DATABASE_URL.get_secret_value())
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(rutas.jwt_private))
    monkeypatch.setenv("CRYPTO_PROVIDER", "local")
    monkeypatch.setenv("CRYPTO_LOCAL_KEK_PATH", str(rutas.kek))
    monkeypatch.setenv("CRYPTO_LOCAL_SIGNING_KEY_PATH", str(rutas.signing_key))
    monkeypatch.setenv("UPLOADS_DIR", "/data")
    monkeypatch.setenv("CORS_ORIGINS", "")
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8")
    monkeypatch.setenv("ARGON2_PARALLELISM", "1")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@apex.local")
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)
    reset_settings_cache()
    await _limpiar_usuarios(engine)
    try:
        yield engine
    finally:
        reset_settings_cache()
        configure_password_hasher(time_cost=3, memory_cost_kib=65536, parallelism=4)
        await _limpiar_usuarios(engine)


async def _admins(engine: AsyncEngine) -> list[User]:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        return list(
            (
                await session.scalars(
                    select(User).where(User.role == "admin", User.is_active.is_(True))
                )
            ).all()
        )


async def test_sin_contrasena_o_debil_no_crea_nada(
    entorno: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sin = runner.invoke(app, ["seed"])
    assert sin.exit_code == 2, sin.output
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "corta")
    reset_settings_cache()
    debil = runner.invoke(app, ["seed"])
    assert debil.exit_code == 2 and "corta" not in debil.output
    assert await _admins(entorno) == []


async def test_crea_el_admin_una_sola_vez_sin_mostrar_la_contrasena(
    entorno: AsyncEngine, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", CLAVE)
    reset_settings_cache()
    with caplog.at_level(logging.DEBUG):
        primero = runner.invoke(app, ["seed"])
        segundo = runner.invoke(app, ["seed"])
    assert primero.exit_code == 0 and "creado" in primero.output, primero.output
    assert segundo.exit_code == 0 and "omitido" in segundo.output
    assert CLAVE not in primero.output + segundo.output + caplog.text
    admins = await _admins(entorno)
    assert len(admins) == 1 and admins[0].email == "admin@apex.local"
    assert admins[0].created_by == SYSTEM_USER_ID


async def test_as_atribuye_el_created_by(
    entorno: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        async with (
            async_sessionmaker(entorno, expire_on_commit=False)() as session,
            session.begin(),
        ):
            duena = User(
                email="dueno@apex.co",
                password_hash="$argon2id$x",  # noqa: S106 - no es una contraseña
                role="coach",
                created_by=SYSTEM_USER_ID,
            )
            session.add(duena)
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", CLAVE)
    reset_settings_cache()
    resultado = runner.invoke(app, ["seed", "--as", "dueno@apex.co"])
    assert resultado.exit_code == 0, resultado.output
    [admin] = await _admins(entorno)
    assert admin.created_by == duena.id
    desconocido = runner.invoke(app, ["seed", "--as", "nadie@apex.co"])
    assert desconocido.exit_code == 2
