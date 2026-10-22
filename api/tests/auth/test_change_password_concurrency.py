"""`change_password` no retiene el candado de la cuenta durante argon2 (revisión Python M1).

Antes: `SELECT ... FOR UPDATE` y luego tres argon2 (verificar la actual, la política "distinta
de la actual" y el hash nuevo) con la fila y la conexión tomadas. Ahora verifica y hashea sin
candado, toma `FOR UPDATE` al final y comprueba que `password_hash` no cambió entretanto; si
cambió (otro cambio ganó la carrera) la contraseña "actual" que tecleó ya no lo es: 422
`invalid_current_password`, sin tocar nada y sin sumar al tope de intentos (no es un intento
fallido de adivinar).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.security import verify_password
from app.modules.auth import service, users
from app.modules.auth.exceptions import InvalidCurrentPassword
from tests.auth._sesion import politica
from tests.conftest import CLAVE_PRUEBA
from tests.factories.users import make_user

NUEVA_A = "Mandarina-Solar-58q"
NUEVA_B = "Guayaba-Lunar-91x"


async def _cambiar(session: AsyncSession, user_id: Any, nueva: str) -> Any:
    with actor_scope(user_id):
        salida = await service.change_password(
            session, user_id, CLAVE_PRUEBA, nueva, current_refresh=None, policy=politica()
        )
        await session.commit()
    return salida


async def test_la_verificacion_corre_sin_el_candado_de_la_cuenta(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    seguridad: object,
    reloj: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primera, segunda = dos_sesiones
    usuario = await make_user(primera, role="coach", password=CLAVE_PRUEBA)
    await primera.commit()
    usuario_id = usuario.id
    candado_tomado: list[bool] = []
    verificar = users.verify_password_or_dummy

    async def _verify_que_sondea(user: Any, password: str) -> bool:
        try:
            await segunda.execute(
                text("SELECT id FROM auth.users WHERE id = :id FOR UPDATE NOWAIT"),
                {"id": usuario_id},
            )
            candado_tomado.append(False)
        except DBAPIError:
            candado_tomado.append(True)
        finally:
            await segunda.rollback()
        return await verificar(user, password)

    monkeypatch.setattr(users, "verify_password_or_dummy", _verify_que_sondea)
    await _cambiar(primera, usuario_id, NUEVA_A)
    assert candado_tomado == [False], "argon2 corrió con la fila bloqueada"


async def test_dos_cambios_concurrentes_el_segundo_falla_sin_tocar_nada(
    dos_sesiones: tuple[AsyncSession, AsyncSession], seguridad: object, reloj: FrozenClock
) -> None:
    primera, segunda = dos_sesiones
    usuario = await make_user(primera, role="coach", password=CLAVE_PRUEBA)
    await primera.commit()
    usuario_id = usuario.id
    resultados = await asyncio.gather(
        _cambiar(primera, usuario_id, NUEVA_A),
        _cambiar(segunda, usuario_id, NUEVA_B),
        return_exceptions=True,
    )
    fallos = [r for r in resultados if isinstance(r, BaseException)]
    assert len(fallos) == 1, resultados
    assert isinstance(fallos[0], InvalidCurrentPassword)
    await primera.rollback()
    await segunda.rollback()
    hash_final = await primera.scalar(
        text("SELECT password_hash FROM auth.users WHERE id = :id"), {"id": usuario_id}
    )
    ganadora = NUEVA_A if not isinstance(resultados[0], BaseException) else NUEVA_B
    assert verify_password(hash_final, ganadora)
    assert not verify_password(hash_final, CLAVE_PRUEBA)
