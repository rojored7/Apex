"""`auth.service.reset` y `auth.service.forgot` con PostgreSQL real (S2-B4; US-048; blueprint 7.2
y S2-B4; H-2 / S2-D36, H-3 / S2-D37, S2-D39, S2-D40, L-13).

`reset(session, token, new_password)`, en el orden del blueprint (decisión 7):
1. `hash_opaque_token(token)` y `SELECT ... FOR UPDATE` del token con su usuario; inexistente,
   usado, vencido o de una cuenta que no puede usarlo da `InvalidToken` (400 `invalid_token`,
   siempre el mismo mensaje);
2. la política con `field="new_password"` (422; el token sigue sin usar tras el rollback);
3. bajo `actor_scope(token.user_id)`: `used_at = ahora`, hash nuevo, `must_change_password =
   False` y `failed_login_count = 0`;
4. con propósito `reset`: `revoke_all` (fija `tokens_valid_after` aunque no haya sesiones) y,
   si revocó alguna, `SessionsRevoked(reason="password_reset", by=user_id)`;
5. `PasswordChanged(via=<propósito>, via_link_issued_by=<created_by del token>)`.
No inicia sesión. Auditoría: `update` de `auth.users` (`password_hash = "***"`) y de
`auth.one_time_tokens` (`used_at`, `token_hash = "***"`), ambos del propio usuario.

`forgot(email, *, policy)` en v0.1 (H-2; sin `session` ni `ip` desde la revisión Python, L3):
no escribe nada (ni filas, ni cierre de
tokens abiertos, ni auditoría), normaliza el correo, cuenta el intento en
`ratelimit.enforce("forgot-account", <correo>)` con el tope `FORGOT_ACCOUNT_LIMIT` (5 por
`FORGOT_ACCOUNT_WINDOW_S`), pide al sleeper la espera del piso `policy.min_duration_ms` exista o
no la cuenta (S2-D39) y deja un log sin el correo.

Reloj congelado en `T0`; las pruebas que miden el corte en segundos avanzan 1 s antes del reset.
Cada éxito confirma (una petición, una transacción); cada rechazo hace `rollback` como
`get_session`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditEntry
from app.core.clock import FrozenClock
from app.core.errors import TooManyRequestsError
from app.core.security import hash_opaque_token, verify_password
from app.modules.auth import service
from app.modules.auth.exceptions import AuthError, InvalidToken
from app.modules.auth.models import OneTimeToken
from app.modules.auth.service import PasswordChanged, SessionsRevoked
from tests.auth._cuentas import (
    NUEVA,
    avanzar,
    es_update_del_hook,
    fila_usuario,
    filas_auditoria,
    tokens_de,
)
from tests.auth._sesion import IP_A, politica
from tests.conftest import (
    CLAVE_PRUEBA,
    T0,
    CapturarEventos,
    CrearUsuario,
    SleeperEspia,
    UsuarioPrueba,
)
from tests.factories.users import make_one_time_token, make_user

T1 = T0 + timedelta(seconds=1)
MENSAJE_INVALIDO = "El enlace ya no es válido. Pide uno nuevo al administrador."


async def _reset(session: AsyncSession, token: str, nueva: str = NUEVA) -> None:
    """Como la ruta: el service y el commit de `get_session`."""
    await service.reset(session, token, nueva)
    await session.commit()


async def _rechazo(
    session: AsyncSession, token: str, nueva: str = NUEVA, tipo: type[Exception] = InvalidToken
) -> Any:
    with pytest.raises(tipo) as excinfo:
        await service.reset(session, token, nueva)
    await session.rollback()
    return excinfo.value


async def _entrar(session: AsyncSession, usuario: UsuarioPrueba) -> str:
    resultado = await service.login(
        session, usuario.email, CLAVE_PRUEBA, ip=IP_A, user_agent="pytest", policy=politica()
    )
    await session.commit()
    return resultado.refresh_token


async def _refresh_abiertos(session: AsyncSession, usuario: UsuarioPrueba) -> int:
    from app.modules.auth.models import RefreshToken

    total = await session.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(RefreshToken.user_id == usuario.id, RefreshToken.revoked_at.is_(None))
    )
    return int(total or 0)


async def _total_auditoria(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(AuditEntry)) or 0)


async def _total_tokens(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(OneTimeToken)) or 0)


# Activación (propósito `activate`) --------------------------------------------------------


async def test_activar_deja_la_cuenta_activa_y_el_login_funciona(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    claro, fila = await make_one_time_token(
        session, pendiente, "activate", expires_in=timedelta(hours=72), created_by=admin.id
    )
    await _reset(session, claro)

    datos = await fila_usuario(session, pendiente.id)
    assert datos["password_hash"] is not None
    assert verify_password(datos["password_hash"], NUEVA) is True
    assert datos["must_change_password"] is False
    assert datos["failed_login_count"] == 0
    (usado,) = await tokens_de(session, pendiente.id)
    assert usado.id == fila.id and usado.used_at == T0
    login = await service.login(
        session, pendiente.email, NUEVA, ip=IP_A, user_agent="pytest", policy=politica()
    )
    await session.commit()
    assert login.user.id == pendiente.id
    assert login.must_change_password is False


async def test_activar_no_inicia_sesion_ni_revoca(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    pendiente = await usuario_real("coach", password=None)
    claro, _ = await make_one_time_token(
        session, pendiente, "activate", expires_in=timedelta(hours=72)
    )
    revocadas = capturar_eventos(SessionsRevoked)
    assert await service.reset(session, claro, NUEVA) is None
    await session.commit()
    assert await _refresh_abiertos(session, pendiente) == 0
    assert revocadas == []


async def test_un_segundo_uso_da_invalid_token_y_el_hash_no_cambia(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    pendiente = await usuario_real("coach", password=None)
    claro, _ = await make_one_time_token(
        session, pendiente, "activate", expires_in=timedelta(hours=72)
    )
    await _reset(session, claro)
    hash_tras_activar = (await fila_usuario(session, pendiente.id))["password_hash"]

    error = await _rechazo(session, claro, "Pomelo-Austral-91z")
    assert (error.status, error.code, error.message) == (400, "invalid_token", MENSAJE_INVALIDO)
    assert (await fila_usuario(session, pendiente.id))["password_hash"] == hash_tras_activar


async def test_una_contrasena_corta_da_422_y_el_token_queda_sin_usar(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    pendiente = await usuario_real("coach", password=None)
    claro, fila = await make_one_time_token(
        session, pendiente, "activate", expires_in=timedelta(hours=72)
    )
    error = await _rechazo(session, claro, "corta", tipo=AuthError)
    assert (error.status, error.code, error.field) == (422, "weak_password", "new_password")
    assert "corta" not in error.message
    (sin_usar,) = await tokens_de(session, pendiente.id)
    assert sin_usar.id == fila.id and sin_usar.used_at is None
    assert (await fila_usuario(session, pendiente.id))["password_hash"] is None
    await _reset(session, claro)  # el mismo token sirve después con una contraseña válida


@pytest.mark.parametrize("nueva", ["x" * 129, "password1234"], ids=["129", "comun"])
async def test_la_politica_completa_aplica_con_field_new_password(
    nueva: str, session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    claro, _ = await make_one_time_token(session, coach, "reset", expires_in=timedelta(hours=1))
    error = await _rechazo(session, claro, nueva, tipo=AuthError)
    assert (error.code, error.field) == ("weak_password", "new_password")


# Restablecimiento (propósito `reset`; H-3) ------------------------------------------------


async def test_reset_revoca_las_dos_sesiones_y_fija_tokens_valid_after(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    coach = await usuario_real("coach")
    await _entrar(session, coach)
    await _entrar(session, coach)
    assert await _refresh_abiertos(session, coach) == 2
    claro, _ = await make_one_time_token(session, coach, "reset", expires_in=timedelta(hours=1))
    avanzar(reloj, 1)
    revocadas = capturar_eventos(SessionsRevoked)
    await _reset(session, claro)

    assert await _refresh_abiertos(session, coach) == 0
    datos = await fila_usuario(session, coach.id)
    assert datos["tokens_valid_after"] == T1
    assert verify_password(datos["password_hash"], NUEVA) is True
    assert verify_password(datos["password_hash"], CLAVE_PRUEBA) is False
    assert revocadas == [
        SessionsRevoked(user_id=coach.id, by=coach.id, revoked=2, reason="password_reset")
    ]


async def test_reset_sin_sesiones_fija_el_corte_y_no_emite_sessions_revoked(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    coach = await usuario_real("coach")
    claro, _ = await make_one_time_token(session, coach, "reset", expires_in=timedelta(hours=1))
    avanzar(reloj, 1.5)
    revocadas = capturar_eventos(SessionsRevoked)
    await _reset(session, claro)
    assert (await fila_usuario(session, coach.id))["tokens_valid_after"] == T1  # truncado
    assert revocadas == []


async def test_reset_limpia_must_change_y_el_contador_de_fallos(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    from sqlalchemy import text

    admin = await usuario_real("admin", debe_cambiar=True)
    await session.execute(
        text("UPDATE auth.users SET failed_login_count = 7 WHERE id = :id"), {"id": admin.id}
    )
    await session.commit()
    claro, _ = await make_one_time_token(session, admin, "reset", expires_in=timedelta(hours=1))
    await _reset(session, claro)
    datos = await fila_usuario(session, admin.id)
    assert datos["must_change_password"] is False
    assert datos["failed_login_count"] == 0


async def test_un_token_vencido_hace_mas_de_una_hora_se_rechaza(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    claro, _ = await make_one_time_token(session, coach, "reset", expires_in=timedelta(hours=1))
    avanzar(reloj, 3600)  # `expires_at == ahora`: ya no sirve
    error = await _rechazo(session, claro)
    assert (error.code, error.message) == ("invalid_token", MENSAJE_INVALIDO)
    avanzar(reloj, 1)
    await _rechazo(session, claro)
    (fila,) = await tokens_de(session, coach.id)
    assert fila.used_at is None


async def test_un_segundo_antes_de_vencer_todavia_sirve(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    claro, _ = await make_one_time_token(session, coach, "reset", expires_in=timedelta(hours=1))
    avanzar(reloj, 3599)
    await _reset(session, claro)
    (fila,) = await tokens_de(session, coach.id)
    assert fila.used_at == T0 + timedelta(seconds=3599)


@pytest.mark.parametrize("caso", ["inexistente", "bloqueado", "borrado", "inactivo", "usado"])
async def test_todo_fallo_del_token_es_el_mismo_400(
    caso: str, session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    cambios: dict[str, Any] = {
        "bloqueado": {"bloqueado": True},
        "borrado": {"borrado": True},
        "inactivo": {"activo": False},
    }.get(caso, {})
    usuario = await usuario_real("coach", **cambios)
    claro, _ = await make_one_time_token(
        session,
        usuario,
        "reset",
        expires_in=timedelta(hours=1),
        used_at=T0 - timedelta(minutes=1) if caso == "usado" else None,
    )
    token = "x" * 43 if caso == "inexistente" else claro
    hash_antes = (await fila_usuario(session, usuario.id))["password_hash"]
    error = await _rechazo(session, token)
    assert (error.status, error.code, error.message) == (400, "invalid_token", MENSAJE_INVALIDO)
    assert error.field is None
    assert (await fila_usuario(session, usuario.id))["password_hash"] == hash_antes


async def test_un_reset_sobre_una_cuenta_pendiente_no_sirve(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """S2-D40: un pendiente solo activa con `activate`."""
    pendiente = await usuario_real("coach", password=None)
    claro, _ = await make_one_time_token(session, pendiente, "reset", expires_in=timedelta(hours=1))
    await _rechazo(session, claro)
    assert (await fila_usuario(session, pendiente.id))["password_hash"] is None


async def test_dos_resets_concurrentes_con_el_mismo_token_dan_un_solo_exito(
    dos_sesiones: tuple[AsyncSession, AsyncSession], reloj: FrozenClock, argon2_rapido: None
) -> None:
    """`FOR UPDATE` sobre el token: la segunda transacción ve `used_at` y da `InvalidToken`."""
    primera, segunda = dos_sesiones
    usuario = await make_user(primera, role="coach", password=CLAVE_PRUEBA)
    claro, _ = await make_one_time_token(primera, usuario, "reset", expires_in=timedelta(hours=1))

    async def restablecer(sesion: AsyncSession, nueva: str) -> object:
        try:
            await service.reset(sesion, claro, nueva)
            await sesion.commit()
            return nueva
        except InvalidToken as error:
            await sesion.rollback()
            return error

    resultados = await asyncio.gather(
        restablecer(primera, NUEVA), restablecer(segunda, "Pomelo-Austral-91z")
    )
    exitos = [r for r in resultados if isinstance(r, str)]
    fallos = [r for r in resultados if isinstance(r, InvalidToken)]
    assert len(exitos) == 1 and len(fallos) == 1, resultados
    datos = await fila_usuario(primera, usuario.id)
    assert verify_password(datos["password_hash"], exitos[0]) is True
    (fila,) = await tokens_de(primera, usuario.id)
    assert fila.used_at == T0


# Eventos y auditoría ------------------------------------------------------------------------


@pytest.mark.parametrize(("purpose", "ttl"), [("activate", 72), ("reset", 1)])
async def test_password_changed_lleva_el_proposito_y_quien_emitio_el_enlace(
    purpose: str,
    ttl: int,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    admin = await usuario_real("admin")
    usuario = await usuario_real("coach", password=None if purpose == "activate" else CLAVE_PRUEBA)
    claro, _ = await make_one_time_token(
        session, usuario, purpose, expires_in=timedelta(hours=ttl), created_by=admin.id
    )
    cambios = capturar_eventos(PasswordChanged)
    await _reset(session, claro)
    assert cambios == [
        PasswordChanged(user_id=usuario.id, by=usuario.id, via=purpose, via_link_issued_by=admin.id)
    ]


async def test_la_auditoria_deja_los_dos_updates_del_usuario_sin_el_token(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    claro, fila = await make_one_time_token(
        session, coach, "reset", expires_in=timedelta(hours=1), created_by=admin.id
    )
    await _reset(session, claro)

    del_usuario = [
        f for f in await filas_auditoria(session, "auth.users", coach.id) if es_update_del_hook(f)
    ]
    assert len(del_usuario) == 1
    assert del_usuario[0]["user_id"] == coach.id
    assert del_usuario[0]["before"]["password_hash"] == "***"  # noqa: S105 - redactado
    assert del_usuario[0]["after"]["password_hash"] == "***"  # noqa: S105 - redactado
    del_token = [
        f
        for f in await filas_auditoria(session, "auth.one_time_tokens", fila.id)
        if f["action"] == "update"
    ]
    assert len(del_token) == 1
    assert del_token[0]["user_id"] == coach.id
    assert del_token[0]["before"]["used_at"] is None
    assert del_token[0]["after"]["used_at"] is not None
    # `update` audita solo columnas cambiadas (core/audit.diff_row); si aparece, va redactado.
    assert del_token[0]["after"].get("token_hash", "***") == "***"
    volcado = json.dumps([*del_usuario, *del_token], default=str)
    assert claro not in volcado
    assert hash_opaque_token(claro) not in volcado
    assert NUEVA not in volcado


async def test_el_log_del_reset_no_lleva_el_token_ni_la_contrasena(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    coach = await usuario_real("coach")
    claro, _ = await make_one_time_token(session, coach, "reset", expires_in=timedelta(hours=1))
    caplog.set_level(logging.DEBUG)
    await _reset(session, claro)
    await _rechazo(session, claro)
    texto = caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    assert claro not in texto
    assert NUEVA not in texto


# forgot (H-2: v0.1 no escribe nada) ---------------------------------------------------------


async def _forgot(session: AsyncSession, email: str, **cambios: Any) -> None:
    """`session` queda para leer la base después: `forgot` no la usa (H-2)."""
    assert await service.forgot(email, policy=politica(**cambios)) is None
    await session.commit()


async def test_forgot_con_correo_existente_no_crea_filas_ni_cierra_tokens_ni_audita(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    _, abierto = await make_one_time_token(session, coach, "reset", expires_in=timedelta(hours=1))
    tokens_antes = await _total_tokens(session)
    auditoria_antes = await _total_auditoria(session)
    datos_antes = await fila_usuario(session, coach.id)

    await _forgot(session, f"  {coach.email.upper()} ")

    assert await _total_tokens(session) == tokens_antes
    assert await _total_auditoria(session) == auditoria_antes
    (sigue,) = await tokens_de(session, coach.id)
    assert sigue.id == abierto.id and sigue.used_at is None
    assert await fila_usuario(session, coach.id) == datos_antes


@pytest.mark.parametrize(
    "cambios",
    [{"bloqueado": True}, {"password": None}, {"activo": False}, {"borrado": True}],
    ids=["bloqueado", "pendiente", "inactivo", "borrado"],
)
async def test_forgot_con_cualquier_cuenta_tampoco_escribe(
    cambios: dict[str, Any], session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    usuario = await usuario_real("coach", **cambios)
    tokens_antes = await _total_tokens(session)
    auditoria_antes = await _total_auditoria(session)
    await _forgot(session, usuario.email)
    assert await _total_tokens(session) == tokens_antes
    assert await _total_auditoria(session) == auditoria_antes


async def test_forgot_con_correo_inexistente_no_lanza_ni_escribe(
    session: AsyncSession, reloj: FrozenClock
) -> None:
    tokens_antes = await _total_tokens(session)
    auditoria_antes = await _total_auditoria(session)
    await _forgot(session, "nadie-forgot@test.apex")
    assert await _total_tokens(session) == tokens_antes
    assert await _total_auditoria(session) == auditoria_antes


async def test_forgot_repetido_no_acumula_tokens(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    for _ in range(3):
        await _forgot(session, coach.email)
    assert await tokens_de(session, coach.id) == []


async def test_forgot_pide_la_misma_espera_exista_o_no_el_correo(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    sleeper_nulo: SleeperEspia,
) -> None:
    """S2-D39: el piso aplica a TODO forgot; el espía no duerme."""
    coach = await usuario_real("coach")
    piso_s = 0.4
    await _forgot(session, coach.email, min_duration_ms=400)
    existente = list(sleeper_nulo.llamadas)
    sleeper_nulo.llamadas.clear()
    await _forgot(session, "nadie-espera@test.apex", min_duration_ms=400)
    inexistente = list(sleeper_nulo.llamadas)
    assert len(existente) == 1 and len(inexistente) == 1, (existente, inexistente)
    for espera in (*existente, *inexistente):
        assert 0 < espera <= piso_s


@pytest.mark.parametrize("existe", [True, False], ids=["existente", "inexistente"])
async def test_forgot_account_da_429_al_sexto_intento_por_cuenta(
    existe: bool, session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """S2-D36: tope por cuenta (`FORGOT_ACCOUNT_LIMIT = 5`) además del de IP; cuenta todo
    intento (no hay éxito ni fallo que distinguir) y sobre el correo normalizado, desde
    cualquier IP: así el límite no revela si la cuenta existe."""
    assert service.FORGOT_ACCOUNT_LIMIT == 5
    assert service.FORGOT_ACCOUNT_BUCKET == "forgot-account"
    correo = (await usuario_real("coach")).email if existe else "nadie-limite@test.apex"
    variantes = [correo, correo.upper(), f" {correo} ", correo, correo.title()]
    for variante in variantes:  # la IP ya no llega al service: el tope es solo por correo
        await _forgot(session, variante)
    with pytest.raises(TooManyRequestsError) as excinfo:
        await service.forgot(correo, policy=politica())
    await session.rollback()
    assert excinfo.value.status == 429
    assert int(excinfo.value.headers["Retry-After"]) >= 1


async def test_forgot_account_es_por_cuenta_y_no_frena_otro_correo(
    session: AsyncSession, reloj: FrozenClock
) -> None:
    for _ in range(service.FORGOT_ACCOUNT_LIMIT):
        await _forgot(session, "una-cuenta@test.apex")
    await _forgot(session, "otra-cuenta@test.apex")  # no lanza


async def test_forgot_account_se_libera_al_pasar_la_ventana(
    session: AsyncSession, reloj: FrozenClock
) -> None:
    for _ in range(service.FORGOT_ACCOUNT_LIMIT):
        await _forgot(session, "ventana@test.apex")
    avanzar(reloj, service.FORGOT_ACCOUNT_WINDOW_S)
    await _forgot(session, "ventana@test.apex")  # no lanza


async def test_el_log_de_forgot_no_lleva_el_correo(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    coach = await usuario_real("coach")
    caplog.set_level(logging.DEBUG)
    await _forgot(session, coach.email)
    await _forgot(session, "Nadie-Log@Test.Apex")
    assert caplog.records, "forgot debe dejar un log (S2-D36)"
    texto = (caplog.text + " ".join(str(r.__dict__) for r in caplog.records)).lower()
    assert coach.email not in texto
    assert "nadie-log@test.apex" not in texto
    local = coach.email.split("@")[0]
    assert local not in texto
