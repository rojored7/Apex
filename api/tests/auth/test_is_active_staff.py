"""`auth.service.is_active_staff` (S7-A2, S7-D7): admin o coach activos; nadie más."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID
from app.modules.auth import service as auth_service
from tests.conftest import CrearUsuario


@pytest.mark.parametrize(("rol", "esperado"), [("admin", True), ("coach", True), ("member", False)])
async def test_por_rol(
    session: AsyncSession, usuario_real: CrearUsuario, rol: str, esperado: bool
) -> None:
    usuario = await usuario_real(rol)
    assert await auth_service.is_active_staff(session, usuario.id) is esperado


async def test_bloqueado_no_es_personal_activo(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    usuario = await usuario_real("coach", bloqueado=True)
    assert await auth_service.is_active_staff(session, usuario.id) is False


async def test_borrado_no_es_personal_activo(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    usuario = await usuario_real("admin", borrado=True)
    assert await auth_service.is_active_staff(session, usuario.id) is False


async def test_inactivo_no_es_personal_activo(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    usuario = await usuario_real("coach", activo=False)
    assert await auth_service.is_active_staff(session, usuario.id) is False


async def test_inexistente_y_usuario_tecnico(session: AsyncSession) -> None:
    assert await auth_service.is_active_staff(session, uuid4()) is False
    assert await auth_service.is_active_staff(session, SYSTEM_USER_ID) is False
