"""`cli seed` (US-041 T11, T14; S2-B2: M-8, L-9, L-4): códigos de salida, sin contraseña en
la salida, `SeedSettings`, `must_change_password`, `--no-force-change` y `--as` solo activo."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
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


# S2-B2 · M-8 (SeedSettings y must_change_password), L-9 y L-4 ---------------------------


async def _debe_cambiar(engine: AsyncEngine) -> list[bool]:
    async with engine.connect() as conexion:
        filas = await conexion.execute(
            text(
                "SELECT must_change_password FROM auth.users "
                "WHERE role = 'admin' AND is_active AND id <> :s"
            ),
            {"s": SYSTEM_USER_ID},
        )
        return [bool(f[0]) for f in filas]


def _sin_admin_en_el_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)
    reset_settings_cache()


async def test_seed_lee_admin_de_env_seed(
    entorno: AsyncEngine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """M-8 (S2-D12): `ADMIN_*` salen de `.env.seed` (solo `tools`) vía `SeedSettings`."""
    _sin_admin_en_el_entorno(monkeypatch)
    (tmp_path / ".env.seed").write_text(
        f"ADMIN_EMAIL=semilla@apex.local\nADMIN_INITIAL_PASSWORD={CLAVE}\n", encoding="utf-8"
    )
    resultado = runner.invoke(app, ["seed"])
    assert resultado.exit_code == 0 and "creado" in resultado.output, resultado.output
    assert CLAVE not in resultado.output
    [admin] = await _admins(entorno)
    assert admin.email == "semilla@apex.local"


async def test_admin_en_el_env_del_api_ya_no_siembra(
    entorno: AsyncEngine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`Settings` ignora `ADMIN_*` (están en `NON_API_ENV_VARS`): sin `.env.seed`, sale con 2."""
    _sin_admin_en_el_entorno(monkeypatch)
    (tmp_path / ".env").write_text(
        f"ADMIN_EMAIL=viejo@apex.local\nADMIN_INITIAL_PASSWORD={CLAVE}\n", encoding="utf-8"
    )
    resultado = runner.invoke(app, ["seed"])
    assert resultado.exit_code == 2, resultado.output
    assert await _admins(entorno) == []


async def test_el_admin_sembrado_debe_cambiar_la_contrasena(
    entorno: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", CLAVE)
    reset_settings_cache()
    resultado = runner.invoke(app, ["seed"])
    assert resultado.exit_code == 0, resultado.output
    assert await _debe_cambiar(entorno) == [True]


async def test_no_force_change_en_dev_deja_la_contrasena_inicial(
    entorno: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", CLAVE)
    reset_settings_cache()
    resultado = runner.invoke(app, ["seed", "--no-force-change"])
    assert resultado.exit_code == 0, resultado.output
    assert await _debe_cambiar(entorno) == [False]


async def test_no_force_change_fuera_de_dev_sale_con_2_sin_crear_nada(
    entorno: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S2-D12 y L-9: `--no-force-change` solo con `ENV=dev`, leído de `Settings`."""
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", CLAVE)
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    for nombre in ("ARGON2_TIME_COST", "ARGON2_MEMORY_COST_KIB", "ARGON2_PARALLELISM"):
        monkeypatch.delenv(nombre, raising=False)
    reset_settings_cache()
    resultado = runner.invoke(app, ["seed", "--no-force-change"])
    assert resultado.exit_code == 2, resultado.output
    assert "ENV=dev" in resultado.output
    assert await _admins(entorno) == []


async def test_rechaza_el_literal_del_ejemplo(
    entorno: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L-9: el literal histórico del ejemplo (`cambiar-esto`) se rechaza sin repetirlo. Ya está
    en `common_passwords.txt` desde el Sprint 1; esta prueba lo deja fijado para el seed."""
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "cambiar-esto")
    reset_settings_cache()
    resultado = runner.invoke(app, ["seed"])
    assert resultado.exit_code == 2, resultado.output
    assert "cambiar-esto" not in resultado.output
    assert await _admins(entorno) == []


async def test_as_con_cuenta_inactiva_bloqueada_o_tecnica_sale_con_2(
    entorno: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L-4 del Sprint 1: `--as` solo con una persona en estado `active`."""
    with actor_scope(SYSTEM_USER_ID):
        async with (
            async_sessionmaker(entorno, expire_on_commit=False)() as session,
            session.begin(),
        ):
            session.add_all(
                [
                    User(
                        email="inactiva@apex.co",
                        password_hash="$argon2id$x",  # noqa: S106 - no es una contraseña
                        role="coach",
                        is_active=False,
                        created_by=SYSTEM_USER_ID,
                    ),
                    User(
                        email="bloqueada@apex.co",
                        password_hash="$argon2id$x",  # noqa: S106 - no es una contraseña
                        role="coach",
                        locked_at=datetime(2026, 10, 1, tzinfo=UTC),
                        created_by=SYSTEM_USER_ID,
                    ),
                ]
            )
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", CLAVE)
    reset_settings_cache()
    for correo in ("inactiva@apex.co", "bloqueada@apex.co", "system@apex.local"):
        resultado = runner.invoke(app, ["seed", "--as", correo])
        assert resultado.exit_code == 2, (correo, resultado.output)
        assert "--as" in resultado.output
    assert await _admins(entorno) == []
