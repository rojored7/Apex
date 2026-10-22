"""Auditoría de los eventos de seguridad de `auth` (S2-B6; US-107; S2-D43, S2-D49, L-8, L-13).

Contrato que fijan estas pruebas (plan S2-B6 y blueprint 7.5):
- `LoginAttempted` deja una fila `login` sobre `auth.users` con `record_id` y `user_id` del propio
  usuario y `after = {result, reason, ip, user_agent}` (el agente ya truncado a 120 por el
  evento); nunca el correo tecleado. Un correo inexistente no emite nada (N-31).
- La fila del login fallido sobrevive al 401: el service confirma antes de lanzar (S2-D8).
- `UserLocked` deja `update` con `after = {"event": "UserLocked", "reason": ...}` y
  `SessionsRevoked` deja `update` con `after = {"event": "SessionsRevoked", "reason": ...,
  "revoked": n}`; `user_id` es quien actúa (`by`) y `record_id` el afectado. El reuso de refresh
  y el bloqueo automático actúan como `SYSTEM_USER_ID`.
- `PasswordChanged` deja `update` con `after.event = "PasswordChanged"`, `via` y
  `via_link_issued_by` (el `created_by` del enlace; L-13).
- Los handlers corren en la transacción del emisor: si otro handler falla, la fila de
  auditoría ya escrita se revierte con el bloqueo.
- La cadena queda íntegra (`verify_chain`) tras todos los eventos.
Reloj congelado en `T0`, argon2 en mínimos y sin el piso de login (`sleeper_nulo`).
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.audit import AuditEntry, verify_chain
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.core.errors import TooManyRequestsError
from app.core.security import hash_opaque_token
from app.modules.auth import service
from app.modules.auth.exceptions import InvalidCredentials, InvalidRefresh
from app.modules.auth.service import SessionsRevoked
from tests.auth._ciclo import como, entrar
from tests.auth._cuentas import avanzar, fila_usuario, filas_auditoria
from tests.auth._sesion import IP_A, politica
from tests.conftest import CLAVE_PRUEBA, T0, CrearUsuario
from tests.factories.users import make_one_time_token

pytestmark = pytest.mark.usefixtures("sleeper_nulo")

ERRADA = "Otra-Clave-Distinta-77"
NUEVA = "Cometa-Violeta-Firme-58"
UA = "pytest-auditoria/1.0"
CLAVES_LOGIN = {"result", "reason", "ip", "user_agent"}


class HandlerRoto(Exception):
    """Doble de un handler que falla (no `RuntimeError`: `NotImplementedError` lo es)."""


# Ayudas -----------------------------------------------------------------------------------


async def _login(
    session: AsyncSession,
    email: str,
    password: str = CLAVE_PRUEBA,
    *,
    ua: str | None = UA,
    **cambios: Any,
) -> service.LoginResult:
    """Un login y su commit (una petición, una transacción)."""
    resultado = await service.login(
        session, email, password, ip=IP_A, user_agent=ua, policy=politica(**cambios)
    )
    await session.commit()
    return resultado


async def _falla(session: AsyncSession, email: str, password: str = ERRADA, **cambios: Any) -> None:
    with pytest.raises(InvalidCredentials):
        await _login(session, email, password, **cambios)
    await session.rollback()  # lo que hace `get_session` ante el 401


async def _filas_login(session: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    filas = await filas_auditoria(session, "auth.users", user_id)
    return [f for f in filas if f["action"] == "login"]


async def _filas_evento(session: AsyncSession, user_id: UUID, evento: str) -> list[dict[str, Any]]:
    return [
        f
        for f in await filas_auditoria(session, "auth.users", user_id)
        if f["action"] == "update" and (f["after"] or {}).get("event") == evento
    ]


async def _filas_de_eventos(session: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    """Las filas que escriben los handlers (no las del hook ORM)."""
    return [
        f
        for f in await filas_auditoria(session, "auth.users", user_id)
        if f["action"] == "login" or (f["after"] or {}).get("event")
    ]


async def _total_filas(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(AuditEntry)) or 0)


async def _cadena(session: AsyncSession) -> list[dict[str, Any]]:
    t = AuditEntry.__table__
    return [dict(f) for f in (await session.execute(select(t).order_by(t.c.seq))).mappings()]


async def _refrescar(session: AsyncSession, token: str) -> str:
    resultado = await service.refresh(session, token, user_agent=UA, policy=politica())
    await session.commit()
    return resultado.refresh_token


async def _reusar(session: AsyncSession, token: str) -> None:
    with pytest.raises(InvalidRefresh):
        await service.refresh(session, token, user_agent=UA, policy=politica())
    await session.rollback()  # el reuso confirma antes del 401 (N-13)


# Login ------------------------------------------------------------------------------------


async def test_login_correcto_deja_una_fila_login_ok_del_propio_usuario(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    await _login(session, coach.email)
    (fila,) = await _filas_login(session, coach.id)
    assert fila["table_name"] == "auth.users"
    assert fila["record_id"] == coach.id
    assert fila["user_id"] == coach.id
    assert fila["before"] is None
    assert set(fila["after"]) <= CLAVES_LOGIN
    assert fila["after"]["result"] == "ok"
    assert fila["after"].get("reason") is None


async def test_after_de_login_trae_ip_y_user_agent_truncado_a_120(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """L-8: la fila guarda `ip` y `user_agent` (el del evento, ya truncado a 120)."""
    coach = await usuario_real("coach")
    await _login(session, coach.email, ua="A" * 300)
    (fila,) = await _filas_login(session, coach.id)
    assert fila["after"]["ip"] == IP_A
    assert fila["after"]["user_agent"] == "A" * 120


async def test_login_fallido_de_correo_existente_deja_failed_aunque_se_revierta(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    await _falla(session, coach.email)
    (fila,) = await _filas_login(session, coach.id)
    assert fila["user_id"] == coach.id
    assert set(fila["after"]) <= CLAVES_LOGIN
    assert fila["after"]["result"] == "failed"
    assert fila["after"]["reason"] == "bad_password"
    assert fila["after"]["ip"] == IP_A
    assert fila["after"]["user_agent"] == UA


async def test_login_de_correo_inexistente_no_deja_ninguna_fila(session: AsyncSession) -> None:
    antes = await _total_filas(session)
    await _falla(session, "nadie-existe@test.apex")
    assert await _total_filas(session) == antes


async def test_cinco_fallidos_dejan_cinco_filas_y_el_sexto_429_ninguna(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """La auditoría no cuenta intentos: el tope por cuenta (5 aquí) corta antes de argon2."""
    coach = await usuario_real("coach")
    for _ in range(5):
        await _falla(session, coach.email, account_limit=5)
    assert len(await _filas_login(session, coach.id)) == 5
    with pytest.raises(TooManyRequestsError):
        await _login(session, coach.email, ERRADA, account_limit=5)
    await session.rollback()
    assert len(await _filas_login(session, coach.id)) == 5


# Bloqueo y revocación ---------------------------------------------------------------------


async def test_lock_de_un_admin_deja_user_locked_y_sessions_revoked_por_el_admin(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await entrar(session, coach)
    avanzar(reloj, 1)
    with como(admin):
        await service.lock(session, coach.id, by=admin.id)
        await session.commit()
    (bloqueo,) = await _filas_evento(session, coach.id, "UserLocked")
    assert bloqueo["user_id"] == admin.id and bloqueo["record_id"] == coach.id
    assert bloqueo["after"] == {"event": "UserLocked", "reason": "admin"}
    (revocacion,) = await _filas_evento(session, coach.id, "SessionsRevoked")
    assert revocacion["user_id"] == admin.id and revocacion["record_id"] == coach.id
    assert revocacion["after"] == {"event": "SessionsRevoked", "reason": "lock", "revoked": 1}


async def test_revoke_sessions_de_un_admin_deja_sessions_revoked_por_el_admin(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await entrar(session, coach)
    await entrar(session, coach)
    avanzar(reloj, 1)
    with como(admin):
        await service.revoke_sessions(session, coach.id, by=admin.id)
        await session.commit()
    (fila,) = await _filas_evento(session, coach.id, "SessionsRevoked")
    assert fila["user_id"] == admin.id and fila["record_id"] == coach.id
    assert fila["after"] == {"event": "SessionsRevoked", "reason": "admin", "revoked": 2}


async def test_reuso_de_refresh_deja_sessions_revoked_del_sistema_y_sobrevive_al_401(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    rotado = await entrar(session, coach)
    await _refrescar(session, rotado)
    reloj.set(T0 + timedelta(seconds=11))  # fuera de la gracia de 10 s: reuso real
    await _reusar(session, rotado)
    (fila,) = await _filas_evento(session, coach.id, "SessionsRevoked")
    assert fila["user_id"] == SYSTEM_USER_ID and fila["record_id"] == coach.id
    assert fila["after"] == {"event": "SessionsRevoked", "reason": "refresh_reuse", "revoked": 1}


async def test_bloqueo_automatico_deja_user_locked_too_many_failures_del_sistema(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    for _ in range(3):
        await _falla(session, coach.email, lock_after=3)
    assert (await fila_usuario(session, coach.id))["locked_at"] is not None
    (bloqueo,) = await _filas_evento(session, coach.id, "UserLocked")
    assert bloqueo["user_id"] == SYSTEM_USER_ID and bloqueo["record_id"] == coach.id
    assert bloqueo["after"] == {"event": "UserLocked", "reason": "too_many_failures"}
    (revocacion,) = await _filas_evento(session, coach.id, "SessionsRevoked")
    assert revocacion["user_id"] == SYSTEM_USER_ID
    assert revocacion["after"] == {"event": "SessionsRevoked", "reason": "lock", "revoked": 0}


# Cambio de contraseña (L-13) --------------------------------------------------------------


async def test_password_changed_por_enlace_deja_via_y_via_link_issued_by(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    claro, _ = await make_one_time_token(
        session, coach, "reset", expires_in=timedelta(hours=1), created_by=admin.id
    )
    await service.reset(session, claro, NUEVA)
    await session.commit()
    (fila,) = await _filas_evento(session, coach.id, "PasswordChanged")
    assert fila["user_id"] == coach.id and fila["record_id"] == coach.id
    assert fila["after"]["via"] == "reset"
    assert fila["after"]["via_link_issued_by"] == str(admin.id)


async def test_password_changed_desde_mi_cuenta_deja_via_change_sin_enlace(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    with como(coach):
        await service.change_password(
            session, coach.id, CLAVE_PRUEBA, NUEVA, current_refresh=None, policy=politica()
        )
        await session.commit()
    (fila,) = await _filas_evento(session, coach.id, "PasswordChanged")
    assert fila["user_id"] == coach.id
    assert fila["after"]["via"] == "change"
    assert fila["after"]["via_link_issued_by"] is None


# Datos sensibles, transacción y cadena ----------------------------------------------------


async def test_ninguna_fila_de_evento_lleva_contrasena_hash_token_ni_correo_tecleado(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    tecleado = f"  {coach.email.upper()} "
    rotado = (await _login(session, tecleado)).refresh_token
    await _falla(session, tecleado)
    sucesor = await _refrescar(session, rotado)
    reloj.set(T0 + timedelta(seconds=11))
    await _reusar(session, rotado)
    with como(admin):
        await service.lock(session, coach.id, by=admin.id)
        await session.commit()
    hash_actual = (await fila_usuario(session, coach.id))["password_hash"]

    filas = await _filas_de_eventos(session, coach.id)
    assert {f["action"] for f in filas} == {"login", "update"}
    volcado = json.dumps([[f["before"], f["after"]] for f in filas], ensure_ascii=False)
    prohibidos = [
        CLAVE_PRUEBA,
        ERRADA,
        hash_actual,
        rotado,
        sucesor,
        hash_opaque_token(rotado),
        hash_opaque_token(sucesor),
        coach.email,
        coach.email.upper(),
        coach.email.split("@")[0],
    ]
    assert [p for p in prohibidos if p and p in volcado] == []


async def test_si_un_handler_posterior_falla_se_revierte_el_bloqueo_y_su_fila(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """Los handlers comparten la transacción del emisor: la fila `UserLocked` que el handler de
    auditoría ya escribió se va con el rollback, igual que `locked_at`."""
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    vistas: list[int] = []

    async def falla(evento: SessionsRevoked, sesion: AsyncSession) -> None:
        vistas.append(len(await _filas_evento(sesion, coach.id, "UserLocked")))
        raise HandlerRoto("handler roto")

    events.subscribe(SessionsRevoked, falla)
    avanzar(reloj, 1)
    with como(admin), pytest.raises(HandlerRoto):
        await service.lock(session, coach.id, by=admin.id)
    await session.rollback()
    assert vistas == [1], "la fila UserLocked debía existir dentro de la transacción"
    assert (await fila_usuario(session, coach.id))["locked_at"] is None
    assert await _filas_evento(session, coach.id, "UserLocked") == []
    assert await _filas_evento(session, coach.id, "SessionsRevoked") == []


async def test_la_cadena_queda_integra_tras_todos_los_eventos(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    claro, _ = await make_one_time_token(
        session, coach, "reset", expires_in=timedelta(hours=1), created_by=admin.id
    )
    await _login(session, coach.email)
    await _falla(session, coach.email)
    await service.reset(session, claro, NUEVA)
    await session.commit()
    avanzar(reloj, 1)
    with como(admin):
        await service.lock(session, coach.id, by=admin.id)
        await session.commit()
    acciones = sorted(
        (f["action"], (f["after"] or {}).get("event", ""))
        for f in await _filas_de_eventos(session, coach.id)
    )
    # login ok y failed; el reset revoca la sesión del login (SessionsRevoked password_reset) y
    # cambia la clave; el lock deja UserLocked y SessionsRevoked (lock).
    assert acciones == sorted(
        [
            ("login", ""),
            ("login", ""),
            ("update", "PasswordChanged"),
            ("update", "SessionsRevoked"),
            ("update", "UserLocked"),
            ("update", "SessionsRevoked"),
        ]
    )
    cadena = await _cadena(session)
    resultado = verify_chain(cadena)
    assert resultado.ok, resultado
    assert resultado.rows_checked == len(cadena)
