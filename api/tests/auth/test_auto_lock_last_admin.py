"""El bloqueo automático por fallos respeta al último admin también en carrera (revisión de
seguridad S2-B5, MEDIUM-1; S2-D10, H-4.3).

Dos admins activos con `failed_login_count = lock_after - 1` reciben a la vez un fallo de
contraseña. Sin serializar con `tokens.lock_active_admins`, cada login ve dos admins (ninguno
exento) y ambos se bloquean: el sistema queda sin administración. Con el candado de admins
tomado antes de `increment_failures`, el segundo ve el conjunto ya reducido y queda exento.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.modules.auth import service
from app.modules.auth.exceptions import InvalidCredentials
from app.modules.auth.models import User
from tests.auth._cuentas import etiqueta
from tests.auth._sesion import IP_A, IP_B, politica
from tests.conftest import CLAVE_PRUEBA
from tests.factories.users import make_user

LOCK_AFTER = 20


async def test_dos_fallos_simultaneos_no_bloquean_a_los_dos_unicos_admins(
    dos_sesiones: tuple[AsyncSession, AsyncSession], reloj: FrozenClock, argon2_rapido: None
) -> None:
    primera, segunda = dos_sesiones
    tag = etiqueta()
    a = await make_user(primera, role="admin", email=f"al-a-{tag}@test.apex", password=CLAVE_PRUEBA)
    b = await make_user(primera, role="admin", email=f"al-b-{tag}@test.apex", password=CLAVE_PRUEBA)
    ids: list[UUID] = [a.id, b.id]
    await primera.execute(
        update(User).where(User.id.in_(ids)).values(failed_login_count=LOCK_AFTER - 1)
    )
    await primera.commit()

    async def fallar(sesion: AsyncSession, correo: str, ip: str) -> None:
        with pytest.raises(InvalidCredentials):
            await service.login(
                sesion,
                correo,
                "no-es-la-clave-correcta",
                ip=ip,
                user_agent="pytest",
                policy=politica(lock_after=LOCK_AFTER),
            )
        await sesion.rollback()

    await asyncio.gather(fallar(primera, a.email, IP_A), fallar(segunda, b.email, IP_B))

    async with primera.begin():
        bloqueados = await primera.scalar(
            select(func.count())
            .select_from(User)
            .where(User.id.in_(ids), User.locked_at.is_not(None))
        )
    assert bloqueados == 1, "debe quedar un admin activo"
