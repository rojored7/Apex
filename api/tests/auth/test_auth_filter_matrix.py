"""M-7 (S2-D40): un solo predicado de "esta cuenta puede autenticarse" en los cuatro caminos.

Para cada uno de los cinco estados de S2-D1 (más el usuario técnico) coinciden:
`rules.account_may_authenticate`, `rules.AUTH_FILTER` en SQL, el cargador
`load_active_principal`, `login` y `refresh`. Y `rules.status_filter` (SQL) coincide con
`rules.user_status` (Python) fila por fila.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.security import hash_opaque_token
from app.modules.auth import service
from app.modules.auth.exceptions import InvalidCredentials, InvalidRefresh
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.rules import AUTH_FILTER, account_may_authenticate, status_filter, user_status
from tests.auth._sesion import IP_A, politica
from tests.conftest import CLAVE_PRUEBA, T0, CrearUsuario

ESTADOS = ("active", "inactive", "locked", "pending_activation", "deleted")


async def _matriz(session: AsyncSession, usuario_real: CrearUsuario) -> dict[str, UUID]:
    """Un usuario por estado (más el técnico), cada uno con un refresh vigente conocido."""
    ids = {
        "active": (await usuario_real("coach")).id,
        "inactive": (await usuario_real("coach", activo=False)).id,
        "locked": (await usuario_real("coach", bloqueado=True)).id,
        "pending_activation": (await usuario_real("coach", password=None)).id,
        "deleted": (await usuario_real("coach", borrado=True)).id,
        "tecnico": SYSTEM_USER_ID,
    }
    with actor_scope(SYSTEM_USER_ID):
        for nombre, user_id in ids.items():
            session.add(
                RefreshToken(
                    user_id=user_id,
                    token_hash=hash_opaque_token(f"matriz-{nombre}"),
                    expires_at=T0 + timedelta(days=7),
                    created_by=SYSTEM_USER_ID,
                )
            )
        await session.flush()
        await session.commit()
    return ids


async def test_los_cuatro_caminos_coinciden_en_los_cinco_estados(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    ids = await _matriz(session, usuario_real)
    pasan_sql = set(
        (await session.scalars(select(User.id).where(User.id.in_(ids.values()), AUTH_FILTER))).all()
    )
    for nombre, user_id in ids.items():
        usuario = await session.get(User, user_id)
        assert usuario is not None
        esperado = nombre == "active"
        assert account_may_authenticate(usuario) is esperado, nombre
        assert (user_id in pasan_sql) is esperado, nombre
        principal = await service.load_active_principal(session, user_id)
        assert (principal is not None) is esperado, nombre

        try:
            await service.login(
                session,
                usuario.email,
                CLAVE_PRUEBA,
                ip=IP_A,
                user_agent="matriz",
                policy=politica(),
            )
            await session.commit()
            entro = True
        except InvalidCredentials:
            await session.rollback()
            entro = False
        assert entro is esperado, f"login de {nombre}"

        try:
            await service.refresh(
                session, f"matriz-{nombre}", user_agent="matriz", policy=politica()
            )
            await session.commit()
            renovo = True
        except InvalidRefresh:
            await session.rollback()
            renovo = False
        assert renovo is esperado, f"refresh de {nombre}"


@pytest.mark.parametrize("estado", ESTADOS)
async def test_status_filter_coincide_con_user_status(
    estado: str, session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    ids = await _matriz(session, usuario_real)
    usuarios = {user_id: await session.get(User, user_id) for user_id in ids.values()}
    en_sql = set(
        (
            await session.scalars(
                select(User.id).where(
                    User.id.in_(ids.values()),
                    status_filter(estado),  # type: ignore[arg-type]
                )
            )
        ).all()
    )
    en_python = {uid for uid, u in usuarios.items() if u is not None and user_status(u) == estado}
    assert en_sql == en_python
    if estado != "inactive":
        assert en_python == {ids[estado]}
    else:
        assert en_python == {ids["inactive"], SYSTEM_USER_ID}
