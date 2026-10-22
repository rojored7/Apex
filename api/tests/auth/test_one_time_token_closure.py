"""Revisión de seguridad de S2-B4: cierre de enlaces abiertos y orden de candados.

- MEDIUM-1: tras fijar la contraseña por enlace (`reset`) o cambiarla desde "Mi cuenta"
  (`change_password`), ningún otro enlace abierto del usuario sirve, sea del propósito que sea
  (`tokens.close_open_one_time_tokens`, por ORM y auditado).
- LOW-1: `reset` bloquea en el orden usuario → token, el mismo de `resend_link`; un `reset` y un
  reenvío concurrentes sobre la misma cuenta terminan sin interbloqueo.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.modules.auth import service
from app.modules.auth.exceptions import InvalidToken
from app.modules.auth.schemas import IssuedLinkOut
from tests.auth._cuentas import NUEVA, filas_auditoria, tokens_de
from tests.auth._sesion import politica
from tests.conftest import CLAVE_PRUEBA, T0, CrearUsuario
from tests.factories.users import make_one_time_token, make_user

FRONT = "http://localhost:8180"


async def test_un_reset_cierra_los_demas_enlaces_abiertos_de_cualquier_proposito(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    claro, usado = await make_one_time_token(session, coach, "reset", expires_in=timedelta(hours=1))
    activar_claro, activar = await make_one_time_token(
        session, coach, "activate", expires_in=timedelta(hours=72)
    )
    await service.reset(session, claro, NUEVA)
    await session.commit()

    por_id = {t.id: t for t in await tokens_de(session, coach.id)}
    assert por_id[usado.id].used_at == T0
    assert por_id[activar.id].used_at == T0
    cierres = [
        f
        for f in await filas_auditoria(session, "auth.one_time_tokens", activar.id)
        if f["action"] == "update"
    ]
    assert [f["user_id"] for f in cierres] == [coach.id]
    try:
        await service.reset(session, activar_claro, "Pomelo-Austral-91z")
    except InvalidToken:
        await session.rollback()
    else:  # pragma: no cover - sería la regresión
        raise AssertionError("el activate abierto sobrevivió al reset")


async def test_cambiar_la_contrasena_cierra_los_enlaces_abiertos(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    claro, abierto = await make_one_time_token(
        session, coach, "reset", expires_in=timedelta(hours=1)
    )
    with actor_scope(coach.id):  # como `current_user` en la ruta
        await service.change_password(
            session, coach.id, CLAVE_PRUEBA, NUEVA, current_refresh=None, policy=politica()
        )
        await session.commit()

    (cerrado,) = await tokens_de(session, coach.id)
    assert cerrado.id == abierto.id and cerrado.used_at == T0
    try:
        await service.reset(session, claro, "Pomelo-Austral-91z")
    except InvalidToken:
        await session.rollback()
    else:  # pragma: no cover - sería la regresión
        raise AssertionError("el reset abierto sobrevivió al cambio de contraseña")


async def test_reset_y_reenvio_concurrentes_no_se_interbloquean(
    dos_sesiones: tuple[AsyncSession, AsyncSession], reloj: FrozenClock, argon2_rapido: None
) -> None:
    primera, segunda = dos_sesiones
    admin = await make_user(primera, role="admin", password=CLAVE_PRUEBA)
    coach = await make_user(primera, role="coach", password=CLAVE_PRUEBA)
    claro, _ = await make_one_time_token(primera, coach, "reset", expires_in=timedelta(hours=1))

    async def restablecer() -> object:
        try:
            await service.reset(primera, claro, NUEVA)
            await primera.commit()
            return "reset"
        except InvalidToken as error:  # el reenvío ganó y cerró el token
            await primera.rollback()
            return error

    async def reenviar() -> object:
        salida = await service.resend_link(segunda, coach.id, by=admin.id, front_base_url=FRONT)
        await segunda.commit()
        return salida

    resultados = await asyncio.wait_for(asyncio.gather(restablecer(), reenviar()), timeout=20)
    assert isinstance(resultados[1], IssuedLinkOut), resultados
    assert resultados[0] == "reset" or isinstance(resultados[0], InvalidToken), resultados
    abiertos = [t for t in await tokens_de(primera, coach.id) if t.used_at is None]
    assert len(abiertos) == 1  # solo el del reenvío


async def test_el_cierre_ignora_los_enlaces_ya_vencidos(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """Revisión Python M10: un enlace vencido ya no sirve; cerrarlo solo agregaba una fila de
    auditoría por cada uno. Se cierran únicamente los abiertos y vigentes (`expires_at > now`)."""
    coach = await usuario_real("coach")
    _, vencido = await make_one_time_token(session, coach, "reset", expires_in=timedelta(hours=-1))
    _, vigente = await make_one_time_token(session, coach, "reset", expires_in=timedelta(hours=1))
    with actor_scope(coach.id):
        await service.change_password(
            session, coach.id, CLAVE_PRUEBA, NUEVA, current_refresh=None, policy=politica()
        )
        await session.commit()
    por_id = {t.id: t for t in await tokens_de(session, coach.id)}
    assert por_id[vigente.id].used_at == T0
    assert por_id[vencido.id].used_at is None
    updates = [
        f
        for f in await filas_auditoria(session, "auth.one_time_tokens", vencido.id)
        if f["action"] == "update"
    ]
    assert updates == []
