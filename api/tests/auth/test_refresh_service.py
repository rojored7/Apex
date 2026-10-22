"""`auth.service.refresh` con PostgreSQL real (S2-B2; US-043; N-13, M-2, L-4 y H-3).

Valores calculados a mano: `T0 = 2026-10-21T15:00:00Z`, gracia `REFRESH_REUSE_GRACE_S = 10`,
TTL de 7 días y tope absoluto de 30 días desde `family_started_at`. El reloj se mueve con
`reloj.set(...)` (segundos) o `reloj.advance(...)`.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.core.security import decode_access_token, hash_opaque_token
from app.modules.auth import service
from app.modules.auth.exceptions import InvalidRefresh
from app.modules.auth.models import RefreshToken
from app.modules.auth.service import SessionsRevoked
from tests.auth._sesion import IP_A, politica
from tests.conftest import CLAVE_PRUEBA, T0, CapturarEventos, CrearUsuario


async def _login(session: AsyncSession, email: str) -> str:
    """Un login correcto y su commit, como el de `get_session` al cerrar la petición."""
    resultado = await service.login(
        session, email, CLAVE_PRUEBA, ip=IP_A, user_agent="pytest", policy=politica()
    )
    await session.commit()
    return resultado.refresh_token


async def _refresh(
    session: AsyncSession, token: str | None, **cambios: Any
) -> service.RefreshResult:
    """Un refresh y su commit si tuvo éxito (una petición, una transacción)."""
    resultado = await service.refresh(
        session, token, user_agent="pytest", policy=politica(**cambios)
    )
    await session.commit()
    return resultado


async def _rechazo(session: AsyncSession, token: str | None, **cambios: Any) -> InvalidRefresh:
    with pytest.raises(InvalidRefresh) as excinfo:
        await _refresh(session, token, **cambios)
    await session.rollback()  # lo que hace `get_session` ante la excepción
    return excinfo.value


async def _fila(session: AsyncSession, token: str) -> RefreshToken:
    fila = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_opaque_token(token))
        .execution_options(populate_existing=True)
    )
    assert fila is not None
    return fila


async def _vivas(session: AsyncSession, user_id: UUID) -> int:
    return int(
        await session.scalar(
            text(
                "SELECT count(*) FROM auth.refresh_tokens WHERE user_id = :u AND revoked_at IS NULL"
            ),
            {"u": user_id},
        )
        or 0
    )


async def test_la_rotacion_revoca_el_anterior_y_lo_enlaza_al_nuevo(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    viejo = await _login(session, coach.email)
    reloj.advance(minutes=14)
    resultado = await _refresh(session, viejo)
    assert resultado.refresh_token != viejo
    assert resultado.expires_in == 900
    assert decode_access_token(resultado.access_token, reloj).sub == coach.id
    anterior, nuevo = await _fila(session, viejo), await _fila(session, resultado.refresh_token)
    assert anterior.revoked_at == T0 + timedelta(minutes=14)
    assert anterior.replaced_by_id == nuevo.id
    assert nuevo.revoked_at is None
    assert nuevo.expires_at == T0 + timedelta(minutes=14, days=7)
    familia = await session.execute(
        text("SELECT id, family_started_at FROM auth.refresh_tokens WHERE id IN (:a, :b)"),
        {"a": anterior.id, "b": nuevo.id},
    )
    assert {fila.family_started_at for fila in familia} == {T0}  # la familia hereda su inicio


async def test_reusar_un_rotado_fuera_de_la_gracia_revoca_todo_y_sobrevive_al_401(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    coach = await usuario_real("coach")
    rotado = await _login(session, coach.email)
    await _login(session, coach.email)  # otra sesión viva
    await _login(session, coach.email)  # y otra
    await _refresh(session, rotado)  # tres vivas: el sucesor y las dos sesiones
    assert await _vivas(session, coach.id) == 3
    eventos = capturar_eventos(SessionsRevoked)
    reloj.set(T0 + timedelta(seconds=11, milliseconds=750))
    error = await _rechazo(session, rotado)
    assert error.code == "invalid_refresh" and error.status == 401
    assert await _vivas(session, coach.id) == 0
    assert [(e.user_id, e.by, e.reason, e.revoked) for e in eventos] == [
        (coach.id, SYSTEM_USER_ID, "refresh_reuse", 3)
    ]
    corte = await session.scalar(
        text("SELECT tokens_valid_after FROM auth.users WHERE id = :id"), {"id": coach.id}
    )
    assert corte == T0 + timedelta(seconds=11)  # H-3 y E8: truncado a segundos


async def test_reuso_dentro_de_la_gracia_da_401_sin_revocar_y_a_los_11_s_revoca(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    """M-2: el rotado a T0; a T0+5 s es concurrencia benigna; a T0+11 s, reuso real."""
    coach = await usuario_real("coach")
    rotado = await _login(session, coach.email)
    await _login(session, coach.email)
    sucesor = (await _refresh(session, rotado)).refresh_token
    eventos = capturar_eventos(SessionsRevoked)

    reloj.set(T0 + timedelta(seconds=5))
    await _rechazo(session, rotado)
    assert await _vivas(session, coach.id) == 2
    assert eventos == []
    assert (await _fila(session, sucesor)).revoked_at is None
    corte = await session.scalar(
        text("SELECT tokens_valid_after FROM auth.users WHERE id = :id"), {"id": coach.id}
    )
    assert corte is None

    reloj.set(T0 + timedelta(seconds=11))
    await _rechazo(session, rotado)
    assert await _vivas(session, coach.id) == 0
    assert [e.revoked for e in eventos] == [2]


@pytest.mark.parametrize("caso", ["sin-token", "inexistente", "no-ascii", "vencido", "bloqueado"])
async def test_tokens_que_no_sirven_dan_invalid_refresh(
    caso: str, session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    token: str | None
    if caso == "sin-token":
        token = None
    elif caso == "inexistente":
        token = "no-existe-este-token"  # noqa: S105 - token de prueba
    elif caso == "no-ascii":
        token = "ñandú-token"  # noqa: S105 - token de prueba
    elif caso == "vencido":
        coach = await usuario_real("coach")
        token = await _login(session, coach.email)
        reloj.advance(days=7)  # expires_at == ahora: ya no sirve
    else:
        coach = await usuario_real("coach")
        token = await _login(session, coach.email)
        await session.execute(
            text("UPDATE auth.users SET locked_at = :t WHERE id = :id"), {"t": T0, "id": coach.id}
        )
        await session.commit()
    error = await _rechazo(session, token)
    assert error.code == "invalid_refresh"


async def test_la_familia_muere_a_los_30_dias_aunque_rote(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """L-4: cada rotación da 7 días nuevos, pero el tope absoluto cuenta desde el login."""
    coach = await usuario_real("coach")
    token = await _login(session, coach.email)
    for _ in range(4):  # días 6, 12, 18 y 24: cada token vive 7 días
        reloj.advance(days=6)
        token = (await _refresh(session, token)).refresh_token
    reloj.advance(days=6)  # día 30: el token del día 24 vence el 31, la familia ya no
    error = await _rechazo(session, token)
    assert error.code == "invalid_refresh"


async def test_un_token_cerrado_por_logout_no_es_reuso(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    coach = await usuario_real("coach")
    cerrado = await _login(session, coach.email)
    await _login(session, coach.email)
    await service.logout(session, cerrado)
    await session.commit()
    eventos = capturar_eventos(SessionsRevoked)
    reloj.advance(minutes=5)
    await _rechazo(session, cerrado)
    assert eventos == [] and await _vivas(session, coach.id) == 1


async def test_dos_refresh_concurrentes_con_el_mismo_token_rotan_una_sola_vez(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    seguridad: object,
    reloj: FrozenClock,
) -> None:
    """`SELECT ... FOR UPDATE` serializa: uno rota y el otro cae dentro de la gracia (M-2),
    así que da 401 sin revocar la familia ni el sucesor."""
    from tests.factories.users import make_user

    primera, segunda = dos_sesiones
    usuario = await make_user(primera, role="coach", password=CLAVE_PRUEBA)
    usuario_id, correo = usuario.id, usuario.email
    token = await _login(primera, correo)
    resultados = await asyncio.gather(
        _refresh(primera, token), _refresh(segunda, token), return_exceptions=True
    )
    exitos = [r for r in resultados if isinstance(r, service.RefreshResult)]
    rechazos = [r for r in resultados if isinstance(r, InvalidRefresh)]
    assert len(exitos) == 1 and len(rechazos) == 1, resultados
    await primera.rollback()
    await segunda.rollback()
    filas = (
        await primera.execute(
            text(
                "SELECT revoked_at IS NULL AS viva, replaced_by_id FROM auth.refresh_tokens "
                "WHERE user_id = :u"
            ),
            {"u": usuario_id},
        )
    ).all()
    assert sorted(f.viva for f in filas) == [False, True]  # el rotado y su único sucesor
