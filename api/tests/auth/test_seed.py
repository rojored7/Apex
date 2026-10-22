"""`seed_admin` con PostgreSQL real (US-041 T9): crea, audita sin el hash e idempotente."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.audit import AuditEntry, install_audit_listeners
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.security import configure_password_hasher
from app.modules.auth.models import User
from app.modules.auth.service import UserCreated, seed_admin

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


async def test_crea_el_admin_audita_sin_hash_y_emite(db: AsyncSession) -> None:
    recibidos: list[UserCreated] = []

    async def capturar(evento: UserCreated, sesion: AsyncSession) -> None:
        recibidos.append(evento)

    events.subscribe(UserCreated, capturar)
    try:
        resultado = await seed_admin(db, " Admin@Apex.local ", CLAVE, by=SYSTEM_USER_ID)
    finally:
        events.clear_subscribers()
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
