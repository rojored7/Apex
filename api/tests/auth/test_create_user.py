"""`auth.service.create_user` y `auth.tokens.issue_one_time_token` con PostgreSQL real (S2-B3;
US-047; blueprint 7.2; L-2, L-6 del Sprint 1).

Alta (`create_user`):
- normaliza el correo; crea la cuenta sin hash (`pending_activation`), con
  `must_change_password = False` (la persona elige su contraseña al activar) y `created_by` =
  quien crea;
- emite un token `activate` de 72 h guardado solo como hash y devuelve `CreateUserOut` con
  `activation_url = <front_base_url>/restablecer/<token>` y su `expires_at`;
- deja dos filas `insert` de auditoría (`auth.users` y `auth.one_time_tokens`), atribuidas al
  admin, sin el token en claro y con `token_hash = "***"`;
- emite `UserCreated(role, by)`;
- un correo de una cuenta no borrada da `EmailTaken` (409, `field="email"`, `existing_id`);
  uno de una cuenta borrada se permite; la carrera (dos altas a la vez) también da `EmailTaken`;
- el log no lleva el token ni la URL.

Emisión (`issue_one_time_token`): cierra con `used_at = ahora` (por ORM, auditado) los tokens
abiertos del mismo usuario y propósito, nunca los del otro propósito; TTL 72 h o 1 h.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.security import hash_opaque_token
from app.modules.auth import service, tokens
from app.modules.auth.exceptions import EmailTaken
from app.modules.auth.models import OneTimeToken, User
from app.modules.auth.schemas import CreateUserOut
from app.modules.auth.service import UserCreated
from tests.auth._cuentas import (
    CAMPOS_USER_OUT,
    etiqueta,
    fila_usuario,
    filas_auditoria,
    tokens_de,
)
from tests.conftest import T0, CapturarEventos, CrearUsuario, UsuarioPrueba
from tests.factories.users import make_one_time_token

FRONT = "http://localhost:8180"
PREFIJO = f"{FRONT}/restablecer/"


async def _crear(
    session: AsyncSession, admin: UsuarioPrueba, email: str, role: str = "coach"
) -> CreateUserOut:
    with actor_scope(admin.id):
        salida = await service.create_user(
            session,
            email=email,
            role=role,  # type: ignore[arg-type]
            by=admin.id,
            front_base_url=FRONT,
        )
        await session.commit()
    return salida


def _token_de(salida: CreateUserOut) -> str:
    assert salida.activation_url.startswith(PREFIJO), salida.activation_url
    return salida.activation_url.removeprefix(PREFIJO)


async def test_crea_la_cuenta_pendiente_sin_hash_y_con_el_correo_normalizado(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    tag = etiqueta()
    salida = await _crear(session, admin, f"  Nuevo.Coach-{tag}@Test.Apex ")
    assert isinstance(salida, CreateUserOut)
    assert set(salida.user.model_dump()) == CAMPOS_USER_OUT
    assert salida.user.email == f"nuevo.coach-{tag}@test.apex"
    assert salida.user.role == "coach"
    assert salida.user.member_id is None
    assert salida.user.status == "pending_activation"
    assert salida.user.must_change_password is False
    fila = await fila_usuario(session, salida.user.id)
    assert fila["password_hash"] is None
    assert fila["is_active"] is True
    assert fila["created_by"] == admin.id
    assert fila["email"] == f"nuevo.coach-{tag}@test.apex"


async def test_tambien_crea_admins(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    salida = await _crear(session, admin, f"jefe-{etiqueta()}@test.apex", role="admin")
    assert salida.user.role == "admin" and salida.user.status == "pending_activation"


async def test_emite_un_token_activate_de_72_horas_guardado_como_hash(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    salida = await _crear(session, admin, f"tok-{etiqueta()}@test.apex")
    token = _token_de(salida)
    assert len(token) >= 43
    assert salida.expires_at == T0 + timedelta(hours=72)
    filas = await tokens_de(session, salida.user.id)
    assert len(filas) == 1
    fila = filas[0]
    assert fila.purpose == "activate"
    assert fila.token_hash == hash_opaque_token(token)
    assert fila.token_hash != token
    assert fila.expires_at == T0 + timedelta(hours=72)
    assert fila.used_at is None
    assert fila.created_by == admin.id
    # El token en claro no está en ninguna columna de la tabla.
    crudo = await session.execute(text("SELECT * FROM auth.one_time_tokens"))
    assert token not in json.dumps([dict(f._mapping) for f in crudo], default=str)


async def test_deja_dos_inserts_de_auditoria_sin_el_token(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    salida = await _crear(session, admin, f"aud-{etiqueta()}@test.apex")
    token = _token_de(salida)
    del_usuario = await filas_auditoria(session, "auth.users", salida.user.id)
    assert [(f["action"], f["user_id"]) for f in del_usuario] == [("insert", admin.id)]
    assert del_usuario[0]["after"]["password_hash"] == "***"  # noqa: S105 - redactado (S2-D2)
    (fila_token,) = await tokens_de(session, salida.user.id)
    del_token = await filas_auditoria(session, "auth.one_time_tokens", fila_token.id)
    assert [(f["action"], f["user_id"]) for f in del_token] == [("insert", admin.id)]
    assert del_token[0]["after"]["token_hash"] == "***"  # noqa: S105 - redactado (L-6)
    volcado = json.dumps([*del_usuario, *del_token], default=str)
    assert token not in volcado
    assert hash_opaque_token(token) not in volcado


async def test_emite_user_created_con_el_rol_y_quien_crea(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    admin = await usuario_real("admin")
    recibidos = capturar_eventos(UserCreated)
    salida = await _crear(session, admin, f"ev-{etiqueta()}@test.apex")
    assert recibidos == [UserCreated(user_id=salida.user.id, role="coach", by=admin.id)]


async def test_un_correo_tomado_da_email_taken_con_el_id_existente(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    admin = await usuario_real("admin")
    correo = f"tomado-{etiqueta()}@test.apex"
    existente = await usuario_real("coach", email=correo)
    total_antes = await session.scalar(select(func.count()).select_from(User))
    recibidos = capturar_eventos(UserCreated)
    with actor_scope(admin.id), pytest.raises(EmailTaken) as excinfo:
        await service.create_user(
            session, email=correo.upper(), role="coach", by=admin.id, front_base_url=FRONT
        )
    await session.rollback()
    error = excinfo.value
    assert (error.status, error.code, error.field) == (409, "email_taken", "email")
    assert error.existing_id == existente.id
    assert correo not in error.message
    assert await session.scalar(select(func.count()).select_from(User)) == total_antes
    assert await tokens_de(session, existente.id) == []
    assert recibidos == []


async def test_el_correo_de_una_cuenta_borrada_se_puede_reusar(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    correo = f"reuso-{etiqueta()}@test.apex"
    borrado = await usuario_real("coach", email=correo, borrado=True)
    salida = await _crear(session, admin, correo)
    assert salida.user.id != borrado.id
    assert salida.user.email == correo


async def test_dos_altas_simultaneas_con_el_mismo_correo_dan_una_y_un_email_taken(
    dos_sesiones: tuple[AsyncSession, AsyncSession], reloj: FrozenClock
) -> None:
    """Carrera: ambas pasan el pre-chequeo; `uq_users_email_alive` decide y el `IntegrityError`
    del savepoint se traduce a `EmailTaken` (blueprint, `begin_nested()`)."""
    primera, segunda = dos_sesiones
    correo = f"carrera-{etiqueta()}@test.apex"

    async def alta(sesion: AsyncSession) -> Any:
        try:
            with actor_scope(SYSTEM_USER_ID):
                salida = await service.create_user(
                    sesion, email=correo, role="coach", by=SYSTEM_USER_ID, front_base_url=FRONT
                )
                await sesion.commit()
            return salida
        except EmailTaken as error:
            await sesion.rollback()
            return error

    resultados = await asyncio.gather(alta(primera), alta(segunda))
    creadas = [r for r in resultados if isinstance(r, CreateUserOut)]
    tomadas = [r for r in resultados if isinstance(r, EmailTaken)]
    assert len(creadas) == 1 and len(tomadas) == 1, resultados
    assert tomadas[0].existing_id in (None, creadas[0].user.id)


async def test_el_log_no_lleva_el_token_ni_la_url(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await usuario_real("admin")
    caplog.set_level(logging.DEBUG)
    salida = await _crear(session, admin, f"log-{etiqueta()}@test.apex")
    token = _token_de(salida)
    texto = caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    assert token not in texto
    assert salida.activation_url not in texto


# issue_one_time_token --------------------------------------------------------------------


async def _emitir(
    session: AsyncSession, usuario: UsuarioPrueba, purpose: str, *, now: Any
) -> tuple[str, OneTimeToken]:
    with actor_scope(SYSTEM_USER_ID):
        resultado = await tokens.issue_one_time_token(
            session,
            usuario.id,
            purpose,  # type: ignore[arg-type]
            now=now,
        )
        await session.commit()
    return resultado


@pytest.mark.parametrize(
    ("purpose", "ttl"),
    [("activate", timedelta(hours=72)), ("reset", timedelta(hours=1))],
)
async def test_emite_con_el_ttl_del_proposito_y_solo_el_hash(
    purpose: str,
    ttl: timedelta,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach", password=None)
    claro, fila = await _emitir(session, coach, purpose, now=T0)
    assert fila.purpose == purpose
    assert fila.expires_at == T0 + ttl
    assert fila.used_at is None
    assert fila.token_hash == hash_opaque_token(claro) != claro
    assert [t.id for t in await tokens_de(session, coach.id)] == [fila.id]


async def test_cierra_los_abiertos_del_mismo_proposito_y_no_los_del_otro(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    _, viejo = await make_one_time_token(session, coach, "reset", expires_in=timedelta(hours=1))
    _, otro_proposito = await make_one_time_token(
        session, coach, "activate", expires_in=timedelta(hours=72)
    )
    ahora = T0 + timedelta(minutes=10)
    _, nuevo = await _emitir(session, coach, "reset", now=ahora)
    por_id = {t.id: t for t in await tokens_de(session, coach.id)}
    assert por_id[viejo.id].used_at == ahora
    assert por_id[otro_proposito.id].used_at is None
    assert por_id[nuevo.id].used_at is None
    abiertos = [t for t in por_id.values() if t.used_at is None and t.purpose == "reset"]
    assert [t.id for t in abiertos] == [nuevo.id]


async def test_el_cierre_del_anterior_queda_auditado_como_update(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    claro_viejo, viejo = await make_one_time_token(
        session, coach, "reset", expires_in=timedelta(hours=1)
    )
    await _emitir(session, coach, "reset", now=T0)
    filas = await filas_auditoria(session, "auth.one_time_tokens", viejo.id)
    updates = [f for f in filas if f["action"] == "update"]
    assert len(updates) == 1
    assert updates[0]["before"]["used_at"] is None
    assert updates[0]["after"]["used_at"] is not None
    assert claro_viejo not in json.dumps(filas, default=str)
