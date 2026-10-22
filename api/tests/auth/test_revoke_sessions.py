"""`auth.service.revoke_sessions` con PostgreSQL real (S2-B5; US-051; H-3, S2-D37, S2-D49;
DECISIONES S2-B3, MEDIUM-2: orden de candados usuario → token).

- Revoca todos los refresh vivos del usuario (no los de otros) y devuelve cuántos.
- Fija `tokens_valid_after` = ahora truncado a segundos, también sin sesiones (H-3).
- Emite `SessionsRevoked(user_id, by, revoked=n, reason="admin")` también con `n = 0`.
- No bloquea: `locked_at` sigue nulo y la cuenta puede volver a entrar.
- Un admin que cierra sus propias sesiones deja su refresh revocado y `refresh` da 401.
- Borrada, técnico e inexistente: `UserNotFound`.
- Concurrencia con `refresh` (`dos_sesiones`): sea cual sea el orden, no queda ninguna sesión
  viva al terminar (`revoke_sessions` toma el usuario antes que sus refresh y `refresh` debe
  respetar el mismo orden; si no, un sucesor creado durante la revocación sobrevive).
Reloj congelado en `T0`; la revocación ocurre en `T0 + 1 s`.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID
from app.modules.auth import service
from app.modules.auth.exceptions import InvalidRefresh, UserNotFound
from app.modules.auth.service import SessionsRevoked
from tests.auth._ciclo import como, entrar, sesiones_vivas
from tests.auth._cuentas import avanzar, etiqueta, fila_usuario, filas_refresh
from tests.auth._sesion import IP_A, politica
from tests.conftest import CLAVE_PRUEBA, T0, CapturarEventos, CrearUsuario, UsuarioPrueba
from tests.factories.users import make_user

T1 = T0 + timedelta(seconds=1)
RONDAS_DE_CARRERA = 6


async def _revocar(session: AsyncSession, admin: UsuarioPrueba | UUID, objetivo: UUID) -> int:
    quien = admin if isinstance(admin, UUID) else admin.id
    with como(quien):
        revocadas = await service.revoke_sessions(session, objetivo, by=quien)
        await session.commit()
    return revocadas


async def test_revoca_todas_las_sesiones_del_usuario_y_devuelve_cuantas(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    otro = await usuario_real("coach")
    for _ in range(3):
        await entrar(session, coach)
    await entrar(session, otro)
    avanzar(reloj, 1)
    assert await _revocar(session, admin, coach.id) == 3
    assert await sesiones_vivas(session, coach.id, T1) == 0
    assert all(f.revoked_at == T1 for f in await filas_refresh(session, coach.id))
    assert await sesiones_vivas(session, otro.id, T1) == 1


async def test_fija_tokens_valid_after_tambien_sin_sesiones(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    reloj.set(T0 + timedelta(seconds=1, microseconds=750_000))
    assert await _revocar(session, admin, coach.id) == 0
    assert (await fila_usuario(session, coach.id))["tokens_valid_after"] == T1


@pytest.mark.parametrize("sesiones", [0, 2])
async def test_emite_sessions_revoked_admin_tambien_con_cero(
    sesiones: int,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    for _ in range(sesiones):
        await entrar(session, coach)
    recibidos = capturar_eventos(SessionsRevoked)
    avanzar(reloj, 1)
    await _revocar(session, admin, coach.id)
    assert recibidos == [
        SessionsRevoked(user_id=coach.id, by=admin.id, revoked=sesiones, reason="admin")
    ]


async def test_no_bloquea_la_cuenta(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await entrar(session, coach)
    avanzar(reloj, 1)
    await _revocar(session, admin, coach.id)
    fila = await fila_usuario(session, coach.id)
    assert fila["locked_at"] is None
    assert fila["failed_login_count"] == 0
    assert await service.load_active_principal(session, coach.id) is not None
    assert await entrar(session, coach)
    assert await sesiones_vivas(session, coach.id, T1) == 1


async def test_el_admin_que_cierra_sus_propias_sesiones_pierde_su_refresh(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    propio = await entrar(session, admin)
    avanzar(reloj, 1)
    assert await _revocar(session, admin, admin.id) == 1
    with pytest.raises(InvalidRefresh):
        await service.refresh(session, propio, user_agent="pytest", policy=politica())
    await session.rollback()
    assert await sesiones_vivas(session, admin.id, T1) == 0


@pytest.mark.parametrize("objetivo", ["borrado", "tecnico", "inexistente"])
async def test_borrada_tecnico_o_inexistente_dan_404(
    objetivo: str, session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    borrado = await usuario_real("coach", borrado=True)
    destino = {"borrado": borrado.id, "tecnico": SYSTEM_USER_ID, "inexistente": uuid4()}[objetivo]
    with como(admin), pytest.raises(UserNotFound):
        await service.revoke_sessions(session, destino, by=admin.id)
    await session.rollback()


async def test_revocar_y_refrescar_a_la_vez_no_deja_ninguna_sesion_viva(
    dos_sesiones: tuple[AsyncSession, AsyncSession], reloj: FrozenClock, seguridad: Settings
) -> None:
    """Orden de candados usuario → token (B3 MEDIUM-2 diferido a B5): un `refresh` que rota
    mientras corre la revocación no puede dejar un sucesor vivo. Varias rondas para cubrir los
    dos órdenes posibles; en cada una, al final, cero refresh vivos."""
    primera, segunda = dos_sesiones
    usuario = await make_user(
        primera, role="coach", email=f"carrera-{etiqueta()}@test.apex", password=CLAVE_PRUEBA
    )
    usuario_id, correo = usuario.id, usuario.email

    async def revocar() -> Any:
        with como(SYSTEM_USER_ID):
            n = await service.revoke_sessions(primera, usuario_id, by=SYSTEM_USER_ID)
            await primera.commit()
        return n

    async def refrescar(token: str) -> Any:
        try:
            salida = await service.refresh(segunda, token, user_agent="pytest", policy=politica())
            await segunda.commit()
            return salida
        except InvalidRefresh as error:
            await segunda.rollback()
            return error

    for ronda in range(RONDAS_DE_CARRERA):
        avanzar(reloj, 1)
        acceso = await service.login(
            primera, correo, CLAVE_PRUEBA, ip=IP_A, user_agent="pytest", policy=politica()
        )
        await primera.commit()
        orden = (revocar(), refrescar(acceso.refresh_token))
        if ronda % 2:
            orden = (orden[1], orden[0])
        resultados = await asyncio.gather(*orden, return_exceptions=True)
        inesperados = [
            r
            for r in resultados
            if isinstance(r, BaseException) and not isinstance(r, InvalidRefresh)
        ]
        assert inesperados == [], f"ronda {ronda}: {inesperados!r}"
        async with primera.begin():
            vivas = await sesiones_vivas(primera, usuario_id, reloj.now_utc())
        assert vivas == 0, f"ronda {ronda}: quedó una sesión viva"
