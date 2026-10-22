"""`auth.service.change_password` con PostgreSQL real (S2-B3; US-046; H-3 / S2-D37, M-8, L-5).

Reloj congelado en `T0` y movido 1 s antes del cambio: `tokens_valid_after` queda en
`T0 + 1 s` (truncado a segundos) y el access nuevo sale con `iat = T0 + 1 s`, así el corte en
segundos enteros es determinista. Orden de las reglas: primero la contraseña actual
(`InvalidCurrentPassword`, 422 `current_password`), luego la política con
`field="new_password"` (incluida "distinta de la actual"). El cambio:
- guarda el hash nuevo, pone `must_change_password = False` y `failed_login_count = 0`;
- llama a `revoke_all(except_id=<refresh de la cookie>)`: la sesión de la cookie sigue viva,
  las demás se revocan (sin cookie, todas) y `tokens_valid_after` corta los access emitidos;
- emite `PasswordChanged(via="change", via_link_issued_by=None)` y, si revocó alguna,
  `SessionsRevoked(reason="password_changed")`;
- devuelve `AccessTokenOut` (`token_type="bearer"`, `expires_in = 900`).
Una regla incumplida no cambia nada; la prueba hace `rollback` como `get_session`.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.security import decode_access_token, hash_opaque_token, verify_password
from app.modules.auth import service
from app.modules.auth.exceptions import AuthError, InvalidCurrentPassword
from app.modules.auth.schemas import AccessTokenOut
from app.modules.auth.service import PasswordChanged, SessionsRevoked
from tests.auth._cuentas import (
    NUEVA,
    avanzar,
    es_update_del_hook,
    fila_usuario,
    filas_auditoria,
    filas_refresh,
)
from tests.auth._sesion import IP_A, politica
from tests.conftest import CLAVE_PRUEBA, T0, CapturarEventos, CrearUsuario, UsuarioPrueba

T1 = T0 + timedelta(seconds=1)


async def _entrar(session: AsyncSession, usuario: UsuarioPrueba) -> str:
    """Un login real (una sesión más) y su commit; devuelve el refresh en claro."""
    resultado = await service.login(
        session, usuario.email, CLAVE_PRUEBA, ip=IP_A, user_agent="pytest", policy=politica()
    )
    await session.commit()
    return resultado.refresh_token


async def _cambiar(
    session: AsyncSession,
    usuario: UsuarioPrueba,
    actual: str = CLAVE_PRUEBA,
    nueva: str = NUEVA,
    *,
    cookie: str | None = None,
) -> AccessTokenOut:
    """El cambio como lo haría la ruta: actor = el propio usuario y commit al terminar."""
    with actor_scope(usuario.id):
        salida = await service.change_password(
            session, usuario.id, actual, nueva, current_refresh=cookie, policy=politica()
        )
        await session.commit()
    return salida


async def _rechazo(
    session: AsyncSession, usuario: UsuarioPrueba, actual: str, nueva: str, tipo: type[Exception]
) -> Any:
    with actor_scope(usuario.id), pytest.raises(tipo) as excinfo:
        await service.change_password(
            session, usuario.id, actual, nueva, current_refresh=None, policy=politica()
        )
    await session.rollback()
    return excinfo.value


async def _id_del_refresh(session: AsyncSession, token: str) -> UUID:
    valor = await session.scalar(
        text("SELECT id FROM auth.refresh_tokens WHERE token_hash = :h"),
        {"h": hash_opaque_token(token)},
    )
    assert valor is not None
    return UUID(str(valor))


async def test_devuelve_un_access_nuevo_de_900_segundos_emitido_ahora(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    avanzar(reloj, 1)
    salida = await _cambiar(session, coach)
    assert isinstance(salida, AccessTokenOut)
    assert salida.token_type == "bearer"  # noqa: S105 - tipo de token
    assert salida.expires_in == 900
    claims = decode_access_token(salida.access_token, reloj)
    assert claims.sub == coach.id and claims.role == "coach"
    assert claims.iat == int(T1.timestamp())
    assert salida.access_token != coach.token


async def test_guarda_el_hash_nuevo_y_limpia_must_change_y_el_contador(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    usuario = await usuario_real("admin", debe_cambiar=True)
    await session.execute(
        text("UPDATE auth.users SET failed_login_count = 3 WHERE id = :id"), {"id": usuario.id}
    )
    await session.commit()
    avanzar(reloj, 1)
    await _cambiar(session, usuario)
    fila = await fila_usuario(session, usuario.id)
    assert verify_password(fila["password_hash"], NUEVA) is True
    assert verify_password(fila["password_hash"], CLAVE_PRUEBA) is False
    assert fila["must_change_password"] is False
    assert fila["failed_login_count"] == 0
    assert fila["tokens_valid_after"] == T1


async def test_la_sesion_de_la_cookie_sigue_viva_y_las_demas_se_revocan(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    coach = await usuario_real("coach")
    de_la_cookie = await _entrar(session, coach)
    otra = await _entrar(session, coach)
    id_cookie, id_otra = (
        await _id_del_refresh(session, de_la_cookie),
        await _id_del_refresh(session, otra),
    )
    avanzar(reloj, 1)
    recibidos = capturar_eventos(PasswordChanged, SessionsRevoked)
    await _cambiar(session, coach, cookie=de_la_cookie)

    por_id = {f.id: f for f in await filas_refresh(session, coach.id)}
    assert por_id[id_cookie].revoked_at is None
    assert por_id[id_otra].revoked_at == T1
    assert por_id[id_otra].replaced_by_id is None  # revocada, no rotada: nunca es reuso
    assert recibidos == [
        PasswordChanged(user_id=coach.id, by=coach.id, via="change", via_link_issued_by=None),
        SessionsRevoked(user_id=coach.id, by=coach.id, revoked=1, reason="password_changed"),
    ]


async def test_sin_cookie_revoca_todas_las_sesiones(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    coach = await usuario_real("coach")
    await _entrar(session, coach)
    await _entrar(session, coach)
    avanzar(reloj, 1)
    revocadas = capturar_eventos(SessionsRevoked)
    await _cambiar(session, coach, cookie=None)
    assert all(f.revoked_at == T1 for f in await filas_refresh(session, coach.id))
    assert revocadas == [
        SessionsRevoked(user_id=coach.id, by=coach.id, revoked=2, reason="password_changed")
    ]


async def test_sin_otras_sesiones_no_emite_sessions_revoked(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    coach = await usuario_real("coach")
    unica = await _entrar(session, coach)
    avanzar(reloj, 1)
    recibidos = capturar_eventos(PasswordChanged, SessionsRevoked)
    await _cambiar(session, coach, cookie=unica)
    assert recibidos == [
        PasswordChanged(user_id=coach.id, by=coach.id, via="change", via_link_issued_by=None)
    ]
    # El corte de H-3 se fija igual: el access viejo deja de valer aunque no hubiera otras.
    assert (await fila_usuario(session, coach.id))["tokens_valid_after"] == T1


async def test_la_auditoria_registra_el_update_con_el_hash_redactado(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    usuario = await usuario_real("coach", debe_cambiar=True)
    avanzar(reloj, 1)
    await _cambiar(session, usuario)
    updates = [
        f for f in await filas_auditoria(session, "auth.users", usuario.id) if es_update_del_hook(f)
    ]
    assert len(updates) == 1, updates
    fila = updates[0]
    assert fila["user_id"] == usuario.id
    assert fila["before"]["password_hash"] == "***"  # noqa: S105 - redactado (S2-D2)
    assert fila["after"]["password_hash"] == "***"  # noqa: S105 - redactado (S2-D2)
    assert fila["before"]["must_change_password"] is True
    assert fila["after"]["must_change_password"] is False
    # Contador y corte quedan fuera del diff (S2-D49); ninguna contraseña en claro.
    assert "failed_login_count" not in fila["after"]
    assert "tokens_valid_after" not in fila["after"]
    volcado = json.dumps([fila["before"], fila["after"]], default=str)
    assert NUEVA not in volcado and CLAVE_PRUEBA not in volcado


async def test_la_actual_errada_da_invalid_current_password_y_no_cambia_nada(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    coach = await usuario_real("coach")
    await _entrar(session, coach)
    antes = await fila_usuario(session, coach.id)
    avanzar(reloj, 1)
    recibidos = capturar_eventos(PasswordChanged, SessionsRevoked)
    error = await _rechazo(session, coach, "No-Es-La-Actual-1", NUEVA, InvalidCurrentPassword)
    assert error.code == "invalid_current_password"
    assert error.status == 422
    assert error.field == "current_password"
    despues = await fila_usuario(session, coach.id)
    assert despues["password_hash"] == antes["password_hash"]
    assert despues["tokens_valid_after"] is None
    assert all(f.revoked_at is None for f in await filas_refresh(session, coach.id))
    assert recibidos == []


async def test_la_actual_se_revisa_antes_que_la_politica(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    error = await _rechazo(session, coach, "No-Es-La-Actual-1", "corta", InvalidCurrentPassword)
    assert error.field == "current_password"


@pytest.mark.parametrize(
    "nueva",
    ["Once-letra1", CLAVE_PRUEBA, ("Ab1-" * 33)[:129], "password1234"],
    ids=["once-caracteres", "igual-a-la-actual", "129-caracteres", "comun"],
)
async def test_una_nueva_que_no_cumple_da_weak_password_en_new_password(
    nueva: str,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    coach = await usuario_real("coach", debe_cambiar=True)
    antes = await fila_usuario(session, coach.id)
    recibidos = capturar_eventos(PasswordChanged, SessionsRevoked)
    error = await _rechazo(session, coach, CLAVE_PRUEBA, nueva, AuthError)
    assert error.code == "weak_password"
    assert error.field == "new_password"
    assert nueva not in error.message
    despues = await fila_usuario(session, coach.id)
    assert despues["password_hash"] == antes["password_hash"]
    assert despues["must_change_password"] is True
    assert despues["tokens_valid_after"] is None
    assert recibidos == []


async def test_el_log_no_lleva_ninguna_de_las_dos_contrasenas(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    coach = await usuario_real("coach")
    avanzar(reloj, 1)
    caplog.set_level(logging.DEBUG)
    await _cambiar(session, coach)
    await _rechazo(session, coach, "No-Es-La-Actual-1", NUEVA, InvalidCurrentPassword)
    texto = caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    assert NUEVA not in texto
    assert CLAVE_PRUEBA not in texto
    assert "No-Es-La-Actual-1" not in texto
