"""Diez salidas erradas en paralelo sobre la misma cookie del quiosco (S7-C4c, L-5; M-1 de C4).

El cupo se reserva de forma atómica ANTES de verificar la contraseña: aunque lleguen diez
peticiones a la vez (cada una con su sesión de base), como mucho `EXIT_LIMIT` llegan a argon2 y el
resto recibe 429.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.errors import TooManyRequestsError
from app.core.security import Principal, hash_opaque_token
from app.modules.auth import kiosk, sessions
from app.modules.auth.exceptions import InvalidPassword
from app.modules.auth.models import RefreshToken
from tests.auth._sesion import politica
from tests.conftest import CLAVE_PRUEBA
from tests.factories.users import make_user

RUTA = "/clases/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/checkin"
PARALELAS = 10


async def test_diez_salidas_erradas_en_paralelo_llegan_como_mucho_cinco_a_argon2(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    engine: AsyncEngine,
    seguridad: object,
    reloj: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primera, _ = dos_sesiones
    usuario = await make_user(primera, role="coach", password=CLAVE_PRUEBA)
    token = secrets.token_urlsafe(32)
    with actor_scope(SYSTEM_USER_ID):
        primera.add(
            RefreshToken(
                user_id=usuario.id,
                token_hash=hash_opaque_token(token),
                expires_at=reloj.now_utc() + timedelta(days=7),
                kiosk_path=RUTA,
                created_by=SYSTEM_USER_ID,
            )
        )
        await primera.commit()
    principal = Principal(usuario.id, "coach", None)
    llamadas: list[int] = []

    async def _verify_errada(user: Any, password: str) -> bool:
        llamadas.append(1)
        await asyncio.sleep(0.01)
        return False

    monkeypatch.setattr(sessions, "verify_password_or_dummy", _verify_errada)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)

    async def _salir() -> str:
        async with fabrica() as sesion:
            try:
                await kiosk.exit_kiosk(sesion, principal, token, "otra-clave", policy=politica())
            except InvalidPassword:
                return "401"
            except TooManyRequestsError:
                await sesion.rollback()
                return "429"
            return "200"

    resultados = await asyncio.gather(*(_salir() for _ in range(PARALELAS)))
    assert len(llamadas) == kiosk.EXIT_LIMIT
    assert resultados.count("401") == len(llamadas)
    assert resultados.count("429") == PARALELAS - len(llamadas) >= PARALELAS - kiosk.EXIT_LIMIT
    async with fabrica() as lectura:
        fila = await lectura.scalar(select(RefreshToken).where(RefreshToken.user_id == usuario.id))
        assert fila is not None and fila.kiosk_path == RUTA  # ninguna salida acertó
