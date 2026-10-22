"""`seed_admin` con PostgreSQL real (US-041 T9): crea, audita sin el hash e idempotente."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditEntry, install_audit_listeners
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.security import configure_password_hasher
from app.modules.auth.models import User
from app.modules.auth.service import UserCreated, seed_admin
from tests.conftest import CapturarEventos

CLAVE = "Zanahoria-Lunar-42x"


@pytest.fixture
async def db(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    install_audit_listeners()
    configure_password_hasher(time_cost=1, memory_cost_kib=8, parallelism=1)
    await session.execute(text("ALTER TABLE audit.audit_log DISABLE TRIGGER USER"))
    await session.execute(text("TRUNCATE audit.audit_log"))
    await session.execute(text("ALTER TABLE audit.audit_log ENABLE TRIGGER USER"))
    with actor_scope(SYSTEM_USER_ID):
        yield session
    configure_password_hasher(time_cost=3, memory_cost_kib=65536, parallelism=4)


async def _auditoria(session: AsyncSession) -> list[dict[str, Any]]:
    consulta = select(AuditEntry.__table__).order_by(AuditEntry.__table__.c.seq)
    return [dict(m) for m in (await session.execute(consulta)).mappings().all()]


async def test_crea_el_admin_audita_sin_hash_y_emite(
    db: AsyncSession, capturar_eventos: CapturarEventos
) -> None:
    recibidos = capturar_eventos(UserCreated)
    resultado = await seed_admin(db, " Admin@Apex.local ", CLAVE, by=SYSTEM_USER_ID)
    assert resultado.outcome == "created" and resultado.user_id is not None
    usuario = await db.get(User, resultado.user_id)
    assert usuario is not None
    assert usuario.email == "admin@apex.local" and usuario.role == "admin" and usuario.is_active
    assert usuario.password_hash is not None and usuario.password_hash.startswith("$argon2id$")
    assert usuario.created_by == SYSTEM_USER_ID
    filas = await _auditoria(db)
    assert len(filas) == 1 and filas[0]["action"] == "insert"
    assert filas[0]["after"]["password_hash"] == "***"  # noqa: S105 - redactado
    assert filas[0]["user_id"] == SYSTEM_USER_ID
    assert CLAVE not in str(filas) and usuario.password_hash not in str(filas)
    assert [e.user_id for e in recibidos] == [usuario.id] and recibidos[0].by == SYSTEM_USER_ID


async def test_segundo_seed_omite_y_el_tecnico_no_cuenta(db: AsyncSession) -> None:
    tecnico = await db.get(User, SYSTEM_USER_ID)
    assert tecnico is not None and tecnico.is_active is False
    primero = await seed_admin(db, "admin@apex.local", CLAVE, by=SYSTEM_USER_ID)
    assert primero.outcome == "created"
    segundo = await seed_admin(db, "otro@apex.local", CLAVE, by=SYSTEM_USER_ID)
    assert segundo.outcome == "skipped" and segundo.user_id == primero.user_id
    activos = await db.scalar(
        select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))
    )
    assert activos == 1


async def test_contrasena_debil_no_crea_nada(db: AsyncSession) -> None:
    from app.modules.auth.exceptions import AuthError

    with pytest.raises(AuthError):
        await seed_admin(db, "admin@apex.local", "corta", by=SYSTEM_USER_ID)
    assert (
        await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "admin", User.is_active.is_(True))
        )
        == 0
    )


# S2-B2 · M-8 (must_change_password) y L-4 del Sprint 1 (active_user_id_by_email) ----------


async def _debe_cambiar(session: AsyncSession, user_id: object) -> bool:
    valor = await session.scalar(
        text("SELECT must_change_password FROM auth.users WHERE id = :id"), {"id": user_id}
    )
    return bool(valor)


async def test_el_admin_sembrado_debe_cambiar_la_contrasena(db: AsyncSession) -> None:
    resultado = await seed_admin(db, "admin@apex.local", CLAVE, by=SYSTEM_USER_ID)
    assert resultado.user_id is not None
    assert await _debe_cambiar(db, resultado.user_id) is True


async def test_force_change_false_deja_la_contrasena_inicial(db: AsyncSession) -> None:
    resultado = await seed_admin(
        db, "admin@apex.local", CLAVE, by=SYSTEM_USER_ID, force_change=False
    )
    assert await _debe_cambiar(db, resultado.user_id) is False


async def test_active_user_id_by_email_solo_devuelve_cuentas_activas(db: AsyncSession) -> None:
    from datetime import UTC, datetime

    from app.modules.auth.service import active_user_id_by_email

    instante = datetime(2026, 10, 1, tzinfo=UTC)
    hash_falso = "$argon2id$x"
    filas = {
        "activa": User(email="activa@test.apex", password_hash=hash_falso, role="coach"),
        "inactiva": User(
            email="inactiva@test.apex", password_hash=hash_falso, role="coach", is_active=False
        ),
        "bloqueada": User(
            email="bloqueada@test.apex", password_hash=hash_falso, role="coach", locked_at=instante
        ),
        "borrada": User(
            email="borrada@test.apex", password_hash=hash_falso, role="coach", deleted_at=instante
        ),
        "pendiente": User(email="pendiente@test.apex", password_hash=None, role="coach"),
    }
    for fila in filas.values():
        fila.created_by = SYSTEM_USER_ID
        db.add(fila)
    await db.flush()
    assert await active_user_id_by_email(db, " Activa@Test.Apex ") == filas["activa"].id
    for nombre in ("inactiva", "bloqueada", "borrada", "pendiente"):
        assert await active_user_id_by_email(db, f"{nombre}@test.apex") is None, nombre
    assert await active_user_id_by_email(db, "system@apex.local") is None
    assert await active_user_id_by_email(db, "nadie@test.apex") is None
