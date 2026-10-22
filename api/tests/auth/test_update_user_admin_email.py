"""L-13 en el cambio de correo (revisión de seguridad V10, N-8; antes de US-131).

`PATCH /users/{id}` no puede cambiar el correo de OTRO admin activo con contraseña: cuando
`forgot` envíe correos (US-131), redirigir el correo de un admin sería tomar su cuenta. Da 409
`user_not_eligible` y no cambia nada. El propio admin sí cambia su correo (es su cuenta; ya
sabe la contraseña) y un admin pendiente de activación o bloqueado puede corregirse (el enlace
de activación se cierra al cambiar, revisión S2-B5 LOW-3).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth import service
from app.modules.auth.exceptions import UserNotEligible
from tests.auth._ciclo import como, ruta
from tests.auth._cuentas import etiqueta, fila_usuario
from tests.conftest import Cabeceras, CrearUsuario


async def test_cambiar_el_correo_de_otro_admin_activo_da_409(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    with como(admin), pytest.raises(UserNotEligible):
        await service.update_user(
            session, otro.id, email=f"toma-{etiqueta()}@test.apex", role=None, by=admin.id
        )
    assert (await fila_usuario(session, otro.id))["email"] == otro.email


async def test_el_admin_cambia_su_propio_correo(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    nuevo = f"propio-{etiqueta()}@test.apex"
    with como(admin):
        usuario = await service.update_user(session, admin.id, email=nuevo, role=None, by=admin.id)
    assert usuario.email == nuevo


async def test_un_admin_pendiente_de_activacion_si_se_corrige(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    pendiente = await usuario_real("admin", password=None)
    nuevo = f"corregido-{etiqueta()}@test.apex"
    with como(admin):
        usuario = await service.update_user(
            session, pendiente.id, email=nuevo, role=None, by=admin.id
        )
    assert usuario.email == nuevo


async def test_cambiar_solo_el_rol_de_otro_admin_sigue_permitido(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    with como(admin):
        usuario = await service.update_user(session, otro.id, email=None, role="coach", by=admin.id)
    assert usuario.role == "coach"


async def test_por_http_da_409_user_not_eligible(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    r = await app_http.patch(
        ruta(otro.id), headers=cabeceras(admin), json={"email": f"toma-{etiqueta()}@test.apex"}
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "user_not_eligible"
