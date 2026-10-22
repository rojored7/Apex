"""Comportamientos que fija la revisión de seguridad de S2-B6 (US-107).

- MEDIUM-1 (aceptado como diseño, fail-closed): si un handler de `LoginAttempted` falla, el login
  fallido no responde 401 sino el error, y su transacción se revierte entera: ni la fila `login`
  ni el contador `failed_login_count` quedan escritos. La auditoría es parte del login; una caída
  de la cadena rompe el login (docs/RUNBOOK.md).
- MEDIUM-2: el último admin activo, exento del límite por cuenta (S2-D10), sigue cortado por el
  límite por IP antes del service: desde una IP, cinco 401 dejan cinco filas y el sexto 429 no
  deja ninguna, así que los fallos sobre la cuenta exenta no inflan la cadena sin tope.
Reloj congelado en `T0`, argon2 en mínimos y sin el piso de login (`sleeper_nulo`).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.modules.auth import service
from app.modules.auth.models import User
from app.modules.auth.service import LoginAttempted
from tests.auth._cuentas import fila_usuario, filas_auditoria
from tests.auth._sesion import IP_A, LOGIN, politica, post_auth
from tests.conftest import ClienteDesde, CrearUsuario

pytestmark = pytest.mark.usefixtures("sleeper_nulo")

ERRADA = "Otra-Clave-Distinta-77"


class HandlerRoto(Exception):
    """Doble de un handler que falla."""


async def _filas_login(session: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    filas = await filas_auditoria(session, "auth.users", user_id)
    return [f for f in filas if f["action"] == "login"]


async def test_si_la_auditoria_del_login_fallido_falla_no_cuenta_el_fallo_ni_deja_fila(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")

    async def falla(event: LoginAttempted, s: AsyncSession) -> None:
        raise HandlerRoto("auditoría caída")

    events.subscribe(LoginAttempted, falla)
    with pytest.raises(HandlerRoto):
        await service.login(
            session, coach.email, ERRADA, ip=IP_A, user_agent="ua", policy=politica()
        )
    await session.rollback()
    assert (await fila_usuario(session, coach.id))["failed_login_count"] == 0
    assert await _filas_login(session, coach.id) == []


async def test_el_ultimo_admin_exento_sigue_cortado_por_ip_y_no_infla_la_cadena(
    session: AsyncSession, usuario_real: CrearUsuario, cliente_desde: ClienteDesde
) -> None:
    admin = await usuario_real("admin")
    activos = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.role == "admin",
            User.is_active.is_(True),
            User.locked_at.is_(None),
            User.deleted_at.is_(None),
            User.password_hash.is_not(None),
        )
    )
    assert activos == 1, "la prueba exige un único admin activo (exento del límite por cuenta)"
    cliente = cliente_desde(IP_A)
    cuerpo = {"email": admin.email, "password": ERRADA}
    for _ in range(5):
        assert (await post_auth(cliente, LOGIN, json=cuerpo)).status_code == 401
    assert (await post_auth(cliente, LOGIN, json=cuerpo)).status_code == 429
    filas = await _filas_login(session, admin.id)
    assert len(filas) == 5
    assert {f["after"]["result"] for f in filas} == {"failed"}
