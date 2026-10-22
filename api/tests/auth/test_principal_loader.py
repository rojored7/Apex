"""`load_active_principal`: el cargador real del puerto `PrincipalLoader` (US-034 T9, US-041)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.security import Principal, get_principal_loader
from app.modules.auth.models import User
from app.modules.auth.service import load_active_principal


def _user(**cambios: object) -> User:
    valores: dict[str, object] = {
        "email": f"{uuid4().hex[:8]}@apex.local",
        "password_hash": "$argon2id$x",
        "role": "coach",
        "member_id": None,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    return User(**valores)


async def test_activo_devuelve_principal_y_los_demas_none(session: AsyncSession) -> None:
    socio = uuid4()
    with actor_scope(SYSTEM_USER_ID):
        activo = _user(role="member", member_id=socio)
        inactivo = _user(is_active=False)
        bloqueado = _user(locked_at=datetime(2026, 1, 1, tzinfo=UTC))
        baja = _user(deleted_at=datetime(2026, 1, 1, tzinfo=UTC))
        sin_clave = _user(password_hash=None)
        session.add_all([activo, inactivo, bloqueado, baja, sin_clave])
        await session.flush()
    assert await load_active_principal(session, activo.id) == Principal(activo.id, "member", socio)
    for usuario in (inactivo, bloqueado, baja, sin_clave):
        assert await load_active_principal(session, usuario.id) is None
    assert await load_active_principal(session, uuid4()) is None
    assert await load_active_principal(session, SYSTEM_USER_ID) is None


def test_el_service_registra_el_cargador_al_importarse() -> None:
    import app.modules.auth.service as servicio

    servicio.register_principal_loader(servicio.load_active_principal)
    assert get_principal_loader() is load_active_principal
