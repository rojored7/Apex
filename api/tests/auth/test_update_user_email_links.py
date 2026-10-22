"""Cambiar el correo cierra los enlaces abiertos (revisión de seguridad S2-B5, LOW-3).

Un enlace de activación o restablecimiento se entregó a quien tenía el correo anterior; tras
corregir el correo (mal escrito o de otra persona) ninguno debe seguir sirviendo. El cierre va
por ORM (`used_at = ahora`, `update` auditado por el admin). Un cambio solo de rol no los toca.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.modules.auth import service
from tests.auth._ciclo import como
from tests.auth._cuentas import avanzar, etiqueta, filas_auditoria, tokens_de
from tests.conftest import T0, CrearUsuario
from tests.factories.users import make_one_time_token

T1 = T0 + timedelta(seconds=1)


async def test_cambiar_el_correo_cierra_los_enlaces_abiertos(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    await make_one_time_token(session, pendiente, "activate", expires_in=timedelta(hours=72))
    avanzar(reloj, 1)
    with como(admin):
        await service.update_user(
            session, pendiente.id, email=f"corregido-{etiqueta()}@test.apex", role=None, by=admin.id
        )
        await session.commit()
    (enlace,) = await tokens_de(session, pendiente.id)
    assert enlace.used_at == T1
    cierres = [
        f
        for f in await filas_auditoria(session, "auth.one_time_tokens", enlace.id)
        if f["action"] == "update"
    ]
    assert [f["user_id"] for f in cierres] == [admin.id]


async def test_cambiar_solo_el_rol_no_cierra_los_enlaces(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    await make_one_time_token(session, pendiente, "activate", expires_in=timedelta(hours=72))
    with como(admin):
        await service.update_user(session, pendiente.id, email=None, role="admin", by=admin.id)
        await session.commit()
    (enlace,) = await tokens_de(session, pendiente.id)
    assert enlace.used_at is None
