"""`cli issue-reset-link <correo> --as <correo>` (S2-B4; L-13 / S2-D42; N-15, L-4 del Sprint 1).

La salida de L-13: emite el enlace que `resend-link` rechaza (la propia cuenta del emisor, otro
admin activo con contraseña). Contrato:
- imprime la URL `<FRONT_BASE_URL>/restablecer/<token>` una sola vez y nada más sensible (ni el
  hash ni otra copia del token);
- el propósito es el de `link_purpose_for`: con hash `reset` (1 h), sin hash `activate` (72 h);
- `--as` es obligatorio y debe ser un admin activo (coach, bloqueado o inexistente: sale con 2);
- deja el `insert` auditado de `auth.one_time_tokens` con `created_by` y actor = el admin;
- un correo inexistente sale con 2 sin revelar si existe: el mismo mensaje que una cuenta
  borrada, sin repetir el correo, y sin crear filas.
Commit real contra `db_test`; la limpieza borra solo `@test.apex` y la auditoría que deje.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from typer.testing import CliRunner

from app.cli import app, key_paths_in
from app.core.audit import AuditEntry
from app.core.config import Settings, reset_settings_cache
from app.core.security import configure_password_hasher, hash_opaque_token
from app.modules.auth.models import OneTimeToken, User
from tests.conftest import CLAVE_PRUEBA, LIMPIAR_AUTH
from tests.factories.users import make_user

runner = CliRunner()
FRONT = "http://localhost:8180"
URL = re.compile(r"https?://\S+/restablecer/(\S+)")


async def _limpiar(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for sql in LIMPIAR_AUTH:
            await conn.execute(text(sql))
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
    argon2_rapido: None,
) -> AsyncIterator[AsyncEngine]:
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
    monkeypatch.setenv("FRONT_BASE_URL", f"{FRONT}/")
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    monkeypatch.setenv("ARGON2_MEMORY_COST_KIB", "8")
    monkeypatch.setenv("ARGON2_PARALLELISM", "1")
    reset_settings_cache()
    await _limpiar(engine)
    try:
        yield engine
    finally:
        reset_settings_cache()
        configure_password_hasher(time_cost=1, memory_cost_kib=8, parallelism=1)
        await _limpiar(engine)


async def _usuario(engine: AsyncEngine, email: str, **cambios: Any) -> User:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        return await make_user(session, email=email, **cambios)


async def _tokens(engine: AsyncEngine) -> list[OneTimeToken]:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        return list((await session.scalars(select(OneTimeToken))).all())


async def _auditoria(engine: AsyncEngine, record_id: Any) -> list[dict[str, Any]]:
    t = AuditEntry.__table__
    async with engine.connect() as conn:
        filas = await conn.execute(
            select(t).where(t.c.table_name == "auth.one_time_tokens", t.c.record_id == record_id)
        )
        return [dict(f._mapping) for f in filas]


def _invocar(*args: str) -> Any:
    return runner.invoke(app, ["issue-reset-link", *args])


async def test_sobre_el_propio_admin_imprime_la_url_una_sola_vez(
    entorno: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    admin = await _usuario(entorno, "jefa-cli@test.apex", role="admin", password=CLAVE_PRUEBA)
    with caplog.at_level(logging.DEBUG):
        r = _invocar("jefa-cli@test.apex", "--as", "jefa-cli@test.apex")
    assert r.exit_code == 0, r.output
    encontrados = URL.findall(r.output)
    assert len(encontrados) == 1, r.output
    assert r.output.count("/restablecer/") == 1
    token = encontrados[0]
    assert f"{FRONT}/restablecer/{token}" in r.output  # sin la barra final de la base
    assert r.output.count(token) == 1
    assert hash_opaque_token(token) not in r.output
    assert CLAVE_PRUEBA not in r.output
    assert token not in caplog.text

    (fila,) = await _tokens(entorno)
    assert fila.user_id == admin.id
    assert fila.purpose == "reset"
    assert fila.token_hash == hash_opaque_token(token)
    assert fila.created_by == admin.id
    ahora = datetime.now(UTC)
    assert abs(fila.expires_at - (ahora + timedelta(hours=1))) < timedelta(minutes=5)


async def test_deja_el_insert_auditado_por_el_admin_sin_el_token(entorno: AsyncEngine) -> None:
    admin = await _usuario(entorno, "aud-cli@test.apex", role="admin", password=CLAVE_PRUEBA)
    await _usuario(entorno, "coach-aud-cli@test.apex", role="coach", password=CLAVE_PRUEBA)
    r = _invocar("coach-aud-cli@test.apex", "--as", "aud-cli@test.apex")
    assert r.exit_code == 0, r.output
    (token,) = URL.findall(r.output)
    (fila,) = await _tokens(entorno)
    auditoria = await _auditoria(entorno, fila.id)
    assert [(f["action"], f["user_id"]) for f in auditoria] == [("insert", admin.id)]
    assert auditoria[0]["after"]["token_hash"] == "***"  # noqa: S105 - redactado
    assert token not in str(auditoria)


async def test_funciona_sobre_otro_admin_activo_con_contrasena(entorno: AsyncEngine) -> None:
    """Justo el caso L-13 que `resend-link` rechaza."""
    await _usuario(entorno, "uno-cli@test.apex", role="admin", password=CLAVE_PRUEBA)
    otro = await _usuario(entorno, "dos-cli@test.apex", role="admin", password=CLAVE_PRUEBA)
    r = _invocar("dos-cli@test.apex", "--as", "uno-cli@test.apex")
    assert r.exit_code == 0, r.output
    (fila,) = await _tokens(entorno)
    assert fila.user_id == otro.id and fila.purpose == "reset"


async def test_un_pendiente_recibe_un_enlace_de_activacion(entorno: AsyncEngine) -> None:
    await _usuario(entorno, "jefe-act@test.apex", role="admin", password=CLAVE_PRUEBA)
    await _usuario(entorno, "pend-act@test.apex", role="coach")
    r = _invocar("pend-act@test.apex", "--as", "jefe-act@test.apex")
    assert r.exit_code == 0, r.output
    (fila,) = await _tokens(entorno)
    assert fila.purpose == "activate"


@pytest.mark.parametrize("quien", ["sin-as", "coach", "bloqueado", "inexistente"])
async def test_exige_as_de_un_admin_activo(quien: str, entorno: AsyncEngine) -> None:
    await _usuario(entorno, "objetivo-as@test.apex", role="coach", password=CLAVE_PRUEBA)
    await _usuario(entorno, "coach-as@test.apex", role="coach", password=CLAVE_PRUEBA)
    await _usuario(
        entorno,
        "bloq-as@test.apex",
        role="admin",
        password=CLAVE_PRUEBA,
        locked_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    argumentos = {
        "sin-as": [],
        "coach": ["--as", "coach-as@test.apex"],
        "bloqueado": ["--as", "bloq-as@test.apex"],
        "inexistente": ["--as", "nadie-as@test.apex"],
    }[quien]
    r = _invocar("objetivo-as@test.apex", *argumentos)
    assert r.exit_code == 2, (quien, r.output)
    assert "--as" in r.output
    assert "/restablecer/" not in r.output
    assert await _tokens(entorno) == []


async def test_un_correo_inexistente_sale_con_2_sin_revelar_si_existe(entorno: AsyncEngine) -> None:
    await _usuario(entorno, "jefe-nx@test.apex", role="admin", password=CLAVE_PRUEBA)
    await _usuario(
        entorno,
        "borrado-nx@test.apex",
        role="coach",
        password=CLAVE_PRUEBA,
        deleted_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    inexistente = _invocar("fantasma-nx@test.apex", "--as", "jefe-nx@test.apex")
    borrado = _invocar("borrado-nx@test.apex", "--as", "jefe-nx@test.apex")
    assert inexistente.exit_code == 2, inexistente.output
    assert borrado.exit_code == 2, borrado.output
    assert "fantasma-nx" not in inexistente.output
    assert "borrado-nx" not in borrado.output
    assert inexistente.output.strip() == borrado.output.strip()
    assert inexistente.output.strip(), "debe decir por qué sale con 2"
    assert await _tokens(entorno) == []


async def test_no_deja_mas_de_un_abierto_por_proposito(entorno: AsyncEngine) -> None:
    await _usuario(entorno, "jefe-rep@test.apex", role="admin", password=CLAVE_PRUEBA)
    for _ in range(2):
        r = _invocar("jefe-rep@test.apex", "--as", "jefe-rep@test.apex")
        assert r.exit_code == 0, r.output
    async with entorno.connect() as conn:
        abiertos = await conn.scalar(
            select(func.count()).select_from(OneTimeToken).where(OneTimeToken.used_at.is_(None))
        )
    assert abiertos == 1
