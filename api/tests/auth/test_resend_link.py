"""`auth.service.resend_link` y `auth.tokens.get_alive_or_404` con PostgreSQL real (S2-B4;
US-052; blueprint S2-B4 y 7.2; L-13 / S2-D42).

`resend_link(session, user_id, *, by, front_base_url) -> IssuedLinkOut`:
- `get_alive_or_404(include_deleted=True)`: el técnico y un id inexistente dan `UserNotFound`
  (404 `user_not_found`);
- bloqueado o borrado dan `UserNotEligible` (409 `user_not_eligible`); L-13: también la propia
  cuenta de `by` y otro admin activo con contraseña (para esos, `cli issue-reset-link`);
- propósito `link_purpose_for(user)`: pendiente (sin hash) → `activate` a 72 h; con hash →
  `reset` a 1 h; el abierto anterior del mismo propósito queda cerrado (`used_at = ahora`) y da
  `InvalidToken` en `reset`;
- `url = <front_base_url sin barras finales>/restablecer/<token>`, `purpose`, `expires_at`;
- auditoría `insert` (y `update` del cierre) de `auth.one_time_tokens` atribuidas al admin, sin
  el token ni su hash; el log no lleva el token.
La prueba abre `actor_scope(admin)` como haría `current_user` y confirma tras el éxito.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.security import hash_opaque_token
from app.modules.auth import service, tokens
from app.modules.auth.exceptions import InvalidToken, UserNotEligible, UserNotFound
from app.modules.auth.schemas import IssuedLinkOut
from tests.auth._cuentas import NUEVA, filas_auditoria, tokens_de
from tests.conftest import T0, CrearUsuario, UsuarioPrueba
from tests.factories.users import make_one_time_token

FRONT = "http://localhost:8180"
PREFIJO = f"{FRONT}/restablecer/"


async def _reenviar(
    session: AsyncSession, admin: UsuarioPrueba, user_id: Any, *, front: str = FRONT
) -> IssuedLinkOut:
    with actor_scope(admin.id):
        salida = await service.resend_link(session, user_id, by=admin.id, front_base_url=front)
        await session.commit()
    return salida


async def _rechazo(
    session: AsyncSession, admin: UsuarioPrueba, user_id: Any, tipo: type[Exception]
) -> Any:
    with actor_scope(admin.id), pytest.raises(tipo) as excinfo:
        await service.resend_link(session, user_id, by=admin.id, front_base_url=FRONT)
    await session.rollback()
    return excinfo.value


def _token(salida: IssuedLinkOut) -> str:
    assert salida.url.startswith(PREFIJO), salida.url
    return salida.url.removeprefix(PREFIJO)


# Propósito y vencimiento ---------------------------------------------------------------------


async def test_un_pendiente_con_enlace_vencido_recibe_activate_a_72_horas(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    _, vencido = await make_one_time_token(
        session, pendiente, "activate", expires_in=timedelta(hours=-1)
    )
    salida = await _reenviar(session, admin, pendiente.id)

    assert isinstance(salida, IssuedLinkOut)
    assert set(salida.model_dump()) == {"url", "purpose", "expires_at"}
    assert salida.purpose == "activate"
    assert salida.expires_at == T0 + timedelta(hours=72)
    claro = _token(salida)
    por_id = {t.id: t for t in await tokens_de(session, pendiente.id)}
    assert por_id[vencido.id].used_at == T0
    (nuevo,) = [t for t in por_id.values() if t.id != vencido.id]
    assert nuevo.purpose == "activate"
    assert nuevo.token_hash == hash_opaque_token(claro)
    assert nuevo.expires_at == T0 + timedelta(hours=72)
    assert nuevo.created_by == admin.id
    assert nuevo.used_at is None


async def test_un_activo_recibe_reset_a_una_hora_e_invalida_el_anterior(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    viejo_claro, viejo = await make_one_time_token(
        session, coach, "reset", expires_in=timedelta(hours=1)
    )
    salida = await _reenviar(session, admin, coach.id)
    assert salida.purpose == "reset"
    assert salida.expires_at == T0 + timedelta(hours=1)
    por_id = {t.id: t for t in await tokens_de(session, coach.id)}
    assert por_id[viejo.id].used_at == T0
    abiertos = [t for t in por_id.values() if t.used_at is None]
    assert [t.token_hash for t in abiertos] == [hash_opaque_token(_token(salida))]

    with pytest.raises(InvalidToken):
        await service.reset(session, viejo_claro, NUEVA)
    await session.rollback()
    await service.reset(session, _token(salida), NUEVA)  # el nuevo sí sirve
    await session.commit()


async def test_un_coach_activo_con_contrasena_si_recibe_reset(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    assert (await _reenviar(session, admin, coach.id)).purpose == "reset"


async def test_otro_admin_pendiente_si_recibe_activate(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """L-13 solo cubre admins activos CON contraseña: activar a uno nuevo es el caso normal."""
    admin = await usuario_real("admin")
    nuevo_admin = await usuario_real("admin", password=None)
    assert (await _reenviar(session, admin, nuevo_admin.id)).purpose == "activate"


async def test_la_url_quita_las_barras_finales_del_front(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    salida = await _reenviar(session, admin, coach.id, front=f"{FRONT}//")
    assert salida.url.startswith(PREFIJO)
    assert "//restablecer" not in salida.url
    assert len(_token(salida)) >= 43


# Elegibilidad -------------------------------------------------------------------------------


@pytest.mark.parametrize("cambios", [{"bloqueado": True}, {"borrado": True}], ids=["bloq", "borr"])
async def test_bloqueado_o_borrado_da_409_user_not_eligible(
    cambios: dict[str, Any], session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    usuario = await usuario_real("coach", **cambios)
    error = await _rechazo(session, admin, usuario.id, UserNotEligible)
    assert (error.status, error.code) == (409, "user_not_eligible")
    assert await tokens_de(session, usuario.id) == []


async def test_l13_sobre_la_propia_cuenta_da_409(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    error = await _rechazo(session, admin, admin.id, UserNotEligible)
    assert (error.status, error.code) == (409, "user_not_eligible")
    assert await tokens_de(session, admin.id) == []


async def test_l13_sobre_otro_admin_activo_con_contrasena_da_409(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    _, abierto = await make_one_time_token(session, otro, "reset", expires_in=timedelta(hours=1))
    error = await _rechazo(session, admin, otro.id, UserNotEligible)
    assert error.code == "user_not_eligible"
    (sigue,) = await tokens_de(session, otro.id)
    assert sigue.id == abierto.id and sigue.used_at is None  # no cierra el abierto


@pytest.mark.parametrize("quien", ["tecnico", "inexistente"])
async def test_el_tecnico_o_un_id_inexistente_da_404(
    quien: str, session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    objetivo = SYSTEM_USER_ID if quien == "tecnico" else uuid4()
    error = await _rechazo(session, admin, objetivo, UserNotFound)
    assert (error.status, error.code) == (404, "user_not_found")


# Auditoría y logs ---------------------------------------------------------------------------


async def test_la_auditoria_deja_insert_y_update_del_admin_sin_el_token(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    viejo_claro, viejo = await make_one_time_token(
        session, pendiente, "activate", expires_in=timedelta(hours=72)
    )
    salida = await _reenviar(session, admin, pendiente.id)
    claro = _token(salida)
    (nuevo,) = [t for t in await tokens_de(session, pendiente.id) if t.id != viejo.id]

    del_nuevo = await filas_auditoria(session, "auth.one_time_tokens", nuevo.id)
    assert [(f["action"], f["user_id"]) for f in del_nuevo] == [("insert", admin.id)]
    assert del_nuevo[0]["after"]["token_hash"] == "***"  # noqa: S105 - redactado
    del_viejo = [
        f
        for f in await filas_auditoria(session, "auth.one_time_tokens", viejo.id)
        if f["action"] == "update"
    ]
    assert [(f["action"], f["user_id"]) for f in del_viejo] == [("update", admin.id)]
    volcado = json.dumps([*del_nuevo, *del_viejo], default=str)
    for secreto in (claro, hash_opaque_token(claro), viejo_claro, salida.url):
        assert secreto not in volcado


async def test_el_log_no_lleva_el_token_ni_la_url(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    caplog.set_level(logging.DEBUG)
    salida = await _reenviar(session, admin, coach.id)
    texto = caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    assert _token(salida) not in texto
    assert salida.url not in texto


# get_alive_or_404 ------------------------------------------------------------------------


async def test_get_alive_devuelve_el_usuario_vivo(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    usuario = await tokens.get_alive_or_404(session, coach.id)
    assert usuario.id == coach.id


async def test_get_alive_un_borrado_es_404_salvo_con_include_deleted(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    borrado = await usuario_real("coach", borrado=True)
    with pytest.raises(UserNotFound):
        await tokens.get_alive_or_404(session, borrado.id)
    usuario = await tokens.get_alive_or_404(session, borrado.id, include_deleted=True)
    assert usuario.id == borrado.id and usuario.deleted_at is not None


@pytest.mark.parametrize("include_deleted", [False, True])
async def test_get_alive_el_tecnico_y_el_inexistente_son_404(
    include_deleted: bool, session: AsyncSession, migrated_database: str
) -> None:
    for objetivo in (SYSTEM_USER_ID, uuid4()):
        with pytest.raises(UserNotFound) as excinfo:
            await tokens.get_alive_or_404(session, objetivo, include_deleted=include_deleted)
        assert (excinfo.value.status, excinfo.value.code) == (404, "user_not_found")
