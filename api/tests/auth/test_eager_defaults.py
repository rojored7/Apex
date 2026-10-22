"""`updated_at` queda cargado tras un `UPDATE` por ORM (revisión Python M4).

`CommonColumnsMixin.updated_at` tiene `onupdate=func.now()` del servidor: sin
`eager_defaults=True` el atributo queda expirado tras el flush y leerlo en una sesión async
lanza `MissingGreenlet` (los services repetían `session.refresh(obj, [...])` para evitarlo).
Con `eager_defaults=True` el `UPDATE ... RETURNING` lo trae en el mismo viaje.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth import service
from tests.auth._ciclo import como
from tests.auth._cuentas import etiqueta
from tests.conftest import CrearUsuario


async def test_update_user_deja_updated_at_legible(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    with como(admin):
        usuario = await service.update_user(
            session, coach.id, email=f"m4-{etiqueta()}@test.apex", role=None, by=admin.id
        )
    assert isinstance(usuario.updated_at, datetime)  # sin `await session.refresh`


async def test_lock_deja_updated_at_legible(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    with como(admin):
        usuario = await service.lock(session, coach.id, by=admin.id)
    assert isinstance(usuario.updated_at, datetime)
    assert isinstance(usuario.created_at, datetime)
