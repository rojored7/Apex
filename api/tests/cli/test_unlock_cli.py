"""`cli unlock-user <correo> [--as <correo>]` (S2-B5; US-050; S2-D10, H-4.5; N-15, L-4 del
Sprint 1).

Contrato:
- desbloquea con `service.unlock`: `locked_at` nulo y `failed_login_count = 0`; sale con 0 y
  dice que la cuenta quedó desbloqueada;
- deja el `update` auditado de `auth.users` con el actor de `--as` o, sin `--as`,
  `SYSTEM_USER_ID` (N-15);
- `--as` con una cuenta que no está activa (o inexistente) sale con 2 y lo dice (`resolve_actor`);
- una cuenta no bloqueada, una inexistente o una borrada salen con 2 y el MISMO mensaje, sin
  repetir el correo y sin tocar nada.
Los contadores en memoria del api viven en otro proceso: los limpia `up -d api` (RUNBOOK).
Commit real contra `db_test`; la limpieza borra solo `@test.apex` y la auditoría que deje.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from typer.testing import CliRunner

from app.cli import app, key_paths_in
from app.core.audit import AuditEntry
from app.core.config import Settings, reset_settings_cache
from app.core.context import SYSTEM_USER_ID
from app.core.security import configure_password_hasher
from app.modules.auth.models import User
from tests.conftest import CLAVE_PRUEBA, LIMPIAR_AUTH
from tests.factories.users import make_user

runner = CliRunner()
BLOQUEO = datetime(2026, 10, 1, tzinfo=UTC)


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
        return await make_user(session, email=email, password=CLAVE_PRUEBA, **cambios)


async def _bloqueado(engine: AsyncEngine, email: str, *, fallos: int = 20) -> User:
    usuario = await _usuario(engine, email, role="coach", locked_at=BLOQUEO)
    async with engine.begin() as conn:
        await conn.execute(
            update(User).where(User.id == usuario.id).values(failed_login_count=fallos)
        )
    return usuario


async def _fila(engine: AsyncEngine, user_id: UUID) -> dict[str, Any]:
    async with engine.connect() as conn:
        fila = (
            await conn.execute(
                select(User.locked_at, User.failed_login_count, User.deleted_at).where(
                    User.id == user_id
                )
            )
        ).one()
    return dict(fila._mapping)


async def _updates(engine: AsyncEngine, user_id: UUID) -> list[dict[str, Any]]:
    t = AuditEntry.__table__
    async with engine.connect() as conn:
        filas = await conn.execute(
            select(t)
            .where(
                t.c.table_name == "auth.users",
                t.c.record_id == user_id,
                t.c.action == "update",
            )
            .order_by(t.c.seq)
        )
        return [dict(f._mapping) for f in filas]


def _invocar(*args: str) -> Any:
    return runner.invoke(app, ["unlock-user", *args])


async def test_desbloquea_y_limpia_el_contador(entorno: AsyncEngine) -> None:
    bloqueado = await _bloqueado(entorno, "bloq-cli@test.apex")
    r = _invocar("bloq-cli@test.apex")
    assert r.exit_code == 0, r.output
    assert r.output.strip(), "debe decir que desbloqueó"
    assert CLAVE_PRUEBA not in r.output
    fila = await _fila(entorno, bloqueado.id)
    assert (fila["locked_at"], fila["failed_login_count"]) == (None, 0)


async def test_normaliza_el_correo(entorno: AsyncEngine) -> None:
    bloqueado = await _bloqueado(entorno, "caja-cli@test.apex")
    r = _invocar("  CAJA-cli@Test.Apex ")
    assert r.exit_code == 0, r.output
    assert (await _fila(entorno, bloqueado.id))["locked_at"] is None


async def test_sin_as_audita_al_usuario_tecnico(entorno: AsyncEngine) -> None:
    bloqueado = await _bloqueado(entorno, "tec-cli@test.apex")
    r = _invocar("tec-cli@test.apex")
    assert r.exit_code == 0, r.output
    (fila,) = await _updates(entorno, bloqueado.id)
    assert fila["user_id"] == SYSTEM_USER_ID
    assert fila["before"]["locked_at"] is not None
    assert fila["after"]["locked_at"] is None


async def test_con_as_audita_a_esa_persona(entorno: AsyncEngine) -> None:
    admin = await _usuario(entorno, "jefa-unlock@test.apex", role="admin")
    bloqueado = await _bloqueado(entorno, "as-cli@test.apex")
    r = _invocar("as-cli@test.apex", "--as", "jefa-unlock@test.apex")
    assert r.exit_code == 0, r.output
    (fila,) = await _updates(entorno, bloqueado.id)
    assert fila["user_id"] == admin.id


@pytest.mark.parametrize("quien", ["inexistente", "bloqueado"])
async def test_as_con_una_cuenta_no_activa_sale_con_2(quien: str, entorno: AsyncEngine) -> None:
    bloqueado = await _bloqueado(entorno, "obj-as-unlock@test.apex")
    await _usuario(entorno, "jefe-bloq-unlock@test.apex", role="admin", locked_at=BLOQUEO)
    actor = {"inexistente": "nadie-unlock@test.apex", "bloqueado": "jefe-bloq-unlock@test.apex"}
    r = _invocar("obj-as-unlock@test.apex", "--as", actor[quien])
    assert r.exit_code == 2, (quien, r.output)
    assert "--as" in r.output
    assert (await _fila(entorno, bloqueado.id))["locked_at"] == BLOQUEO
    assert await _updates(entorno, bloqueado.id) == []


async def test_no_bloqueada_inexistente_y_borrada_dan_2_con_el_mismo_mensaje(
    entorno: AsyncEngine,
) -> None:
    activo = await _usuario(entorno, "libre-unlock@test.apex", role="coach")
    borrado = await _usuario(
        entorno,
        "baja-unlock@test.apex",
        role="coach",
        locked_at=BLOQUEO,
        deleted_at=datetime(2026, 10, 2, tzinfo=UTC),
    )
    salidas = {
        "libre": _invocar("libre-unlock@test.apex"),
        "fantasma": _invocar("fantasma-unlock@test.apex"),
        "baja": _invocar("baja-unlock@test.apex"),
    }
    for nombre, r in salidas.items():
        assert r.exit_code == 2, (nombre, r.output)
        assert f"{nombre}-unlock" not in r.output, (nombre, r.output)
        assert r.output.strip(), "debe decir por qué sale con 2"
    textos = {r.output.strip() for r in salidas.values()}
    assert len(textos) == 1, textos
    assert await _updates(entorno, activo.id) == []
    assert await _updates(entorno, borrado.id) == []
    assert (await _fila(entorno, borrado.id))["locked_at"] == BLOQUEO


async def test_dos_veces_la_segunda_sale_con_2(entorno: AsyncEngine) -> None:
    bloqueado = await _bloqueado(entorno, "rep-unlock@test.apex")
    assert _invocar("rep-unlock@test.apex").exit_code == 0
    segunda = _invocar("rep-unlock@test.apex")
    assert segunda.exit_code == 2, segunda.output
    assert len(await _updates(entorno, bloqueado.id)) == 1
