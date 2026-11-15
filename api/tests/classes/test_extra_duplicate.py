"""Sesión extra sin duplicados (S7-B2b, S7-D38). Rojo.

409 `session_duplicate` si ya existe una extra (`slot_id` nulo) no cancelada con el mismo
`starts_at` y el mismo `coach_id` (nulo igual a nulo); una cancelada no cuenta; dos POST
simultáneos no pasan ambos (candado 4_270_006 antes de comprobar).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.classes import service
from app.modules.classes.exceptions import SessionDuplicate
from app.modules.classes.schemas import SessionCancel, SessionCreate
from tests.conftest import CrearUsuario
from tests.factories.users import make_user

JUEVES_6AM = datetime(2026, 10, 22, 11, 0, tzinfo=UTC)

pytestmark = pytest.mark.usefixtures("reloj")


def _crear(**cambios: Any) -> SessionCreate:
    valores: dict[str, Any] = {"starts_at": JUEVES_6AM, "duration_min": 60}
    valores.update(cambios)
    return SessionCreate.model_validate(valores)


async def _alta(session: AsyncSession, actor: UUID, **cambios: Any) -> Any:
    with actor_scope(actor):
        salida = await service.create_extra(session, _crear(**cambios), by=actor, role="admin")
        await session.commit()
    return salida


async def test_el_segundo_alta_igual_da_409(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    await _alta(session, admin.id)
    with pytest.raises(SessionDuplicate) as error:
        await _alta(session, admin.id)
    assert error.value.status == 409 and error.value.code == "session_duplicate"


async def test_otro_coach_u_otra_hora_no_es_duplicado(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await _alta(session, admin.id)
    await _alta(session, admin.id, coach_id=coach.id)
    await _alta(session, admin.id, starts_at=datetime(2026, 10, 22, 12, 0, tzinfo=UTC))
    with pytest.raises(SessionDuplicate):
        await _alta(session, admin.id, coach_id=coach.id)


async def test_una_cancelada_no_cuenta(session: AsyncSession, usuario_real: CrearUsuario) -> None:
    admin = await usuario_real("admin")
    primera = await _alta(session, admin.id)
    with actor_scope(admin.id):
        await service.cancel_session(
            session, primera.id, SessionCancel.model_validate({"reason": "Error"}), by=admin.id
        )
        await session.commit()
    otra = await _alta(session, admin.id)
    assert otra.id != primera.id


async def test_dos_altas_simultaneas_solo_una_pasa(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    una, otra = dos_sesiones
    admin = await make_user(una, role="admin")

    async def alta(sesion: AsyncSession) -> str:
        try:
            await _alta(sesion, admin.id)
        except SessionDuplicate:
            await sesion.rollback()
            return "duplicado"
        return "creada"

    resultados = await asyncio.wait_for(asyncio.gather(alta(una), alta(otra)), timeout=30)
    assert sorted(resultados) == ["creada", "duplicado"]
    filas = await una.scalar(
        text("SELECT count(*) FROM classes.class_sessions WHERE slot_id IS NULL")
    )
    assert filas == 1
