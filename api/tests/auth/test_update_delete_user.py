"""`get_user`, `update_user`, `delete_user` y `tokens.lock_active_admins` con PostgreSQL real
(S2-B5; US-049; blueprint S2-B5; H-3, S2-D37, S2-D49; RN-14).

- `get_user` incluye las cuentas borradas; el técnico y un id inexistente dan `UserNotFound`.
- `update_user`: 404 sobre una borrada o el técnico; correo normalizado y único entre no
  borrados (`EmailTaken` con `existing_id`; la carrera con `dos_sesiones` también da
  `EmailTaken`); el propio correo con otra caja no choca; el de una borrada se puede tomar; el
  cambio de rol valida el `member_id` actual (`validate_user_role`) y da `LastAdmin` si degrada
  al último admin activo; `None` no cambia nada; un `update` auditado por el actor; el
  cargador lee el rol nuevo (un token emitido antes ya lleva el rol vigente).
- `delete_user`: baja lógica (`deleted_at = ahora`, sin `session.delete`, sin fila `delete` en la
  auditoría); `LastAdmin` para el último admin activo (un admin pendiente no cuenta);
  `revoke_all` en la misma transacción (refresh revocados y `tokens_valid_after` = ahora
  truncado) y `SessionsRevoked(reason="delete", revoked=n)` siempre, también con 0; si un
  handler falla no queda nada; la segunda baja da 404; el correo queda libre; dos bajas
  concurrentes de los dos únicos admins dejan exactamente uno.
- `lock_active_admins`: solo admins activos con hash, sin bloqueo, baja ni el técnico, con
  `FOR UPDATE` (otra transacción no los puede tomar).
Reloj congelado en `T0`; las bajas ocurren en `T0 + 1 s` para separar el corte de H-3.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.modules.auth import service, tokens
from app.modules.auth.exceptions import AuthError, EmailTaken, LastAdmin, UserNotFound
from app.modules.auth.models import User
from app.modules.auth.service import SessionsRevoked
from tests.auth._ciclo import EVENTOS_DE_CUENTA, como, entrar, sesiones_vivas
from tests.auth._cuentas import (
    avanzar,
    es_update_del_hook,
    etiqueta,
    fila_usuario,
    filas_auditoria,
    filas_refresh,
)
from tests.conftest import CLAVE_PRUEBA, T0, CapturarEventos, CrearUsuario, UsuarioPrueba
from tests.factories.users import make_user

T1 = T0 + timedelta(seconds=1)


class HandlerRoto(Exception):
    """El doble de un handler que falla (no `RuntimeError`: `NotImplementedError` lo es)."""


async def _actualizar(
    session: AsyncSession,
    admin: UsuarioPrueba,
    objetivo: UUID,
    *,
    email: str | None = None,
    role: str | None = None,
) -> User:
    with como(admin):
        usuario = await service.update_user(
            session,
            objetivo,
            email=email,
            role=role,  # type: ignore[arg-type]
            by=admin.id,
        )
        await session.commit()
    return usuario


async def _rechazo_update(
    session: AsyncSession,
    admin: UsuarioPrueba,
    objetivo: UUID,
    tipo: type[Exception],
    **cambios: Any,
) -> Any:
    with como(admin), pytest.raises(tipo) as excinfo:
        await service.update_user(
            session, objetivo, email=cambios.get("email"), role=cambios.get("role"), by=admin.id
        )
    await session.rollback()
    return excinfo.value


async def _borrar(session: AsyncSession, admin: UsuarioPrueba | UUID, objetivo: UUID) -> None:
    quien = admin if isinstance(admin, UUID) else admin.id
    with como(quien):
        await service.delete_user(session, objetivo, by=quien)
        await session.commit()


# get_user ------------------------------------------------------------------------------


async def test_get_user_devuelve_la_cuenta_leida_de_la_base(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    usuario = await service.get_user(session, coach.id)
    assert (usuario.id, usuario.email, usuario.role) == (coach.id, coach.email, "coach")


async def test_get_user_incluye_las_cuentas_borradas(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    borrado = await usuario_real("coach", borrado=True)
    usuario = await service.get_user(session, borrado.id)
    assert usuario.id == borrado.id
    assert usuario.deleted_at == T0


@pytest.mark.parametrize("objetivo", [SYSTEM_USER_ID, uuid4()], ids=["tecnico", "inexistente"])
async def test_get_user_del_tecnico_o_inexistente_da_404(
    objetivo: UUID, session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    await usuario_real("admin")
    with pytest.raises(UserNotFound):
        await service.get_user(session, objetivo)


# update_user -----------------------------------------------------------------------------


async def test_cambia_el_correo_normalizado_y_lo_audita(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    tag = etiqueta()
    usuario = await _actualizar(session, admin, coach.id, email=f"  Nuevo.Correo-{tag}@Test.APEX ")
    assert usuario.email == f"nuevo.correo-{tag}@test.apex"
    assert (await fila_usuario(session, coach.id))["email"] == f"nuevo.correo-{tag}@test.apex"
    updates = [
        f for f in await filas_auditoria(session, "auth.users", coach.id) if f["action"] == "update"
    ]
    assert len(updates) == 1
    assert updates[0]["user_id"] == admin.id
    assert updates[0]["before"]["email"] == coach.email
    assert updates[0]["after"]["email"] == f"nuevo.correo-{tag}@test.apex"


async def test_el_propio_correo_con_otra_caja_no_choca(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    usuario = await _actualizar(session, admin, coach.id, email=coach.email.upper())
    assert usuario.email == coach.email


async def test_un_correo_de_otra_cuenta_viva_da_email_taken_con_su_id(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    otro = await usuario_real("coach")
    error = await _rechazo_update(session, admin, coach.id, EmailTaken, email=otro.email.upper())
    assert (error.status, error.code, error.field) == (409, "email_taken", "email")
    assert error.existing_id == otro.id
    assert otro.email not in error.message
    assert (await fila_usuario(session, coach.id))["email"] == coach.email


async def test_el_correo_de_una_cuenta_borrada_se_puede_tomar(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    borrado = await usuario_real("coach", borrado=True)
    usuario = await _actualizar(session, admin, coach.id, email=borrado.email)
    assert usuario.email == borrado.email


async def test_dos_cambios_simultaneos_al_mismo_correo_dan_uno_y_un_email_taken(
    dos_sesiones: tuple[AsyncSession, AsyncSession], reloj: FrozenClock, argon2_rapido: None
) -> None:
    """Ambos pasan el pre-chequeo; `uq_users_email_alive` decide dentro del `begin_nested()`."""
    primera, segunda = dos_sesiones
    tag = etiqueta()
    uno = await make_user(primera, email=f"uno-{tag}@test.apex", password=CLAVE_PRUEBA)
    dos = await make_user(primera, email=f"dos-{tag}@test.apex", password=CLAVE_PRUEBA)
    uno_id, dos_id = uno.id, dos.id
    correo = f"disputado-{tag}@test.apex"

    async def cambiar(sesion: AsyncSession, objetivo: UUID) -> Any:
        try:
            with como(SYSTEM_USER_ID):
                usuario = await service.update_user(
                    sesion, objetivo, email=correo, role=None, by=SYSTEM_USER_ID
                )
                await sesion.commit()
            return usuario.id
        except EmailTaken as error:
            await sesion.rollback()
            return error

    resultados = await asyncio.gather(
        cambiar(primera, uno_id), cambiar(segunda, dos_id), return_exceptions=True
    )
    ganadores = [r for r in resultados if isinstance(r, UUID)]
    perdedores = [r for r in resultados if isinstance(r, EmailTaken)]
    assert len(ganadores) == 1 and len(perdedores) == 1, resultados
    assert perdedores[0].existing_id in (None, ganadores[0])
    async with primera.begin():
        con_el_correo = await primera.scalar(
            select(func.count()).select_from(User).where(User.email == correo)
        )
    assert con_el_correo == 1


async def test_cambia_el_rol_de_coach_a_admin_y_lo_audita(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    usuario = await _actualizar(session, admin, coach.id, role="admin")
    assert usuario.role == "admin"
    updates = [
        f for f in await filas_auditoria(session, "auth.users", coach.id) if f["action"] == "update"
    ]
    assert [(u["before"]["role"], u["after"]["role"], u["user_id"]) for u in updates] == [
        ("coach", "admin", admin.id)
    ]


async def test_un_coach_no_pasa_a_socio_sin_ficha(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    error = await _rechazo_update(session, admin, coach.id, AuthError, role="member")
    assert (error.code, error.field) == ("member_id_required", "member_id")
    assert (await fila_usuario(session, coach.id))["role"] == "coach"


async def test_un_socio_no_pasa_a_coach_con_su_ficha(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """`validate_user_role` con el `member_id` actual: admin y coach no llevan ficha."""
    admin = await usuario_real("admin")
    socio = await usuario_real("member")
    error = await _rechazo_update(session, admin, socio.id, AuthError, role="coach")
    assert (error.code, error.field) == ("member_id_not_allowed", "member_id")
    assert (await fila_usuario(session, socio.id))["role"] == "member"


async def test_degradar_al_ultimo_admin_activo_da_last_admin(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    await usuario_real("admin", password=None)  # pendiente: no cuenta como activo
    await usuario_real("admin", bloqueado=True)  # bloqueado: tampoco
    error = await _rechazo_update(session, admin, admin.id, LastAdmin, role="coach")
    assert (error.status, error.code) == (409, "last_admin")
    assert (await fila_usuario(session, admin.id))["role"] == "admin"


async def test_con_dos_admins_uno_se_puede_degradar(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    usuario = await _actualizar(session, admin, otro.id, role="coach")
    assert usuario.role == "coach"


async def test_el_cambio_de_rol_lo_ve_el_cargador_de_inmediato(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """El token emitido antes trae `role=admin`, pero `current_user` usa el `Principal` del
    cargador, que lee la base: el rol nuevo manda en la siguiente petición."""
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    await _actualizar(session, admin, otro.id, role="coach")
    principal = await service.load_active_principal(session, otro.id)
    assert principal is not None and principal.role == "coach"


async def test_sin_cambios_no_audita_nada(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    usuario = await _actualizar(session, admin, coach.id)
    assert (usuario.email, usuario.role) == (coach.email, "coach")
    updates = [
        f for f in await filas_auditoria(session, "auth.users", coach.id) if f["action"] == "update"
    ]
    assert updates == []


async def test_update_de_una_borrada_o_del_tecnico_da_404(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    borrado = await usuario_real("coach", borrado=True)
    for objetivo in (borrado.id, SYSTEM_USER_ID, uuid4()):
        await _rechazo_update(session, admin, objetivo, UserNotFound, role="admin")
    assert (await fila_usuario(session, borrado.id))["role"] == "coach"


# delete_user -----------------------------------------------------------------------------


async def test_la_baja_es_logica_y_no_usa_session_delete(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")

    async def prohibido(*args: object, **kwargs: object) -> None:
        raise AssertionError("delete_user no debe borrar físicamente (RN-14)")

    monkeypatch.setattr(session, "delete", prohibido)
    avanzar(reloj, 1)
    await _borrar(session, admin, coach.id)
    fila = await fila_usuario(session, coach.id)
    assert fila["deleted_at"] == T1
    auditoria = await filas_auditoria(session, "auth.users", coach.id)
    assert "delete" not in [f["action"] for f in auditoria]
    (update,) = [f for f in auditoria if es_update_del_hook(f)]
    assert update["user_id"] == admin.id
    assert update["before"]["deleted_at"] is None
    assert update["after"]["deleted_at"] is not None


async def test_la_baja_revoca_las_sesiones_y_fija_el_corte(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await entrar(session, coach)
    await entrar(session, coach)
    recibidos = capturar_eventos(SessionsRevoked)
    avanzar(reloj, 1)
    await _borrar(session, admin, coach.id)
    assert await sesiones_vivas(session, coach.id, T1) == 0
    assert all(f.revoked_at == T1 for f in await filas_refresh(session, coach.id))
    assert (await fila_usuario(session, coach.id))["tokens_valid_after"] == T1
    assert recibidos == [SessionsRevoked(user_id=coach.id, by=admin.id, revoked=2, reason="delete")]


async def test_la_baja_sin_sesiones_emite_sessions_revoked_con_cero(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    recibidos = capturar_eventos(SessionsRevoked)
    avanzar(reloj, 1)
    await _borrar(session, admin, coach.id)
    assert recibidos == [SessionsRevoked(user_id=coach.id, by=admin.id, revoked=0, reason="delete")]


async def test_si_un_handler_falla_la_baja_no_deja_nada(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """La baja y la revocación van en la misma transacción que el evento."""
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await entrar(session, coach)

    async def falla(evento: SessionsRevoked, sesion: AsyncSession) -> None:
        raise HandlerRoto("handler roto")

    events.subscribe(SessionsRevoked, falla)
    avanzar(reloj, 1)
    with como(admin), pytest.raises(HandlerRoto):
        await service.delete_user(session, coach.id, by=admin.id)
    await session.rollback()
    fila = await fila_usuario(session, coach.id)
    assert fila["deleted_at"] is None
    assert fila["tokens_valid_after"] is None
    assert await sesiones_vivas(session, coach.id, T1) == 1


async def test_dar_de_baja_al_ultimo_admin_activo_da_last_admin(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    admin = await usuario_real("admin")
    await usuario_real("admin", password=None)  # un admin pendiente no lo releva
    recibidos = capturar_eventos(*EVENTOS_DE_CUENTA)
    with como(admin), pytest.raises(LastAdmin):
        await service.delete_user(session, admin.id, by=admin.id)
    await session.rollback()
    assert (await fila_usuario(session, admin.id))["deleted_at"] is None
    assert recibidos == []


async def test_el_tecnico_no_cuenta_como_admin_y_da_404(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    with como(admin), pytest.raises(UserNotFound):
        await service.delete_user(session, SYSTEM_USER_ID, by=admin.id)
    await session.rollback()
    await _borrar(session, admin, otro.id)  # el técnico tiene rol admin pero no se cuenta
    with como(admin), pytest.raises(LastAdmin):
        await service.delete_user(session, admin.id, by=admin.id)
    await session.rollback()


async def test_la_segunda_baja_da_404(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await _borrar(session, admin, coach.id)
    with como(admin), pytest.raises(UserNotFound):
        await service.delete_user(session, coach.id, by=admin.id)
    await session.rollback()


async def test_el_correo_de_la_baja_queda_libre(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await _borrar(session, admin, coach.id)
    with como(admin):
        salida = await service.create_user(
            session, email=coach.email, role="coach", by=admin.id, front_base_url="http://x"
        )
        await session.commit()
    assert salida.user.id != coach.id
    assert salida.user.email == coach.email


async def test_la_cuenta_borrada_ya_no_autentica(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await _borrar(session, admin, coach.id)
    assert await service.load_active_principal(session, coach.id) is None


async def test_dos_bajas_concurrentes_de_los_dos_unicos_admins_dejan_uno(
    dos_sesiones: tuple[AsyncSession, AsyncSession], reloj: FrozenClock, argon2_rapido: None
) -> None:
    """`lock_active_admins` (`FOR UPDATE` por id) serializa: la segunda ve un solo admin."""
    primera, segunda = dos_sesiones
    tag = etiqueta()
    a = await make_user(primera, role="admin", email=f"a-{tag}@test.apex", password=CLAVE_PRUEBA)
    b = await make_user(primera, role="admin", email=f"b-{tag}@test.apex", password=CLAVE_PRUEBA)
    a_id, b_id = a.id, b.id

    async def baja(sesion: AsyncSession, objetivo: UUID, por: UUID) -> Any:
        try:
            with como(por):
                await service.delete_user(sesion, objetivo, by=por)
                await sesion.commit()
            return objetivo
        except LastAdmin as error:
            await sesion.rollback()
            return error

    resultados = await asyncio.gather(
        baja(primera, a_id, b_id), baja(segunda, b_id, a_id), return_exceptions=True
    )
    hechas = [r for r in resultados if isinstance(r, UUID)]
    rechazadas = [r for r in resultados if isinstance(r, LastAdmin)]
    assert len(hechas) == 1 and len(rechazadas) == 1, resultados
    async with primera.begin():
        vivos = await primera.scalar(
            select(func.count())
            .select_from(User)
            .where(User.id.in_([a_id, b_id]), User.deleted_at.is_(None))
        )
    assert vivos == 1


# lock_active_admins ------------------------------------------------------------------------


async def test_lock_active_admins_trae_solo_los_admins_activos(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    activo = await usuario_real("admin")
    otro_activo = await usuario_real("admin")
    await usuario_real("admin", password=None)
    await usuario_real("admin", bloqueado=True)
    await usuario_real("admin", borrado=True)
    await usuario_real("admin", activo=False)
    await usuario_real("coach")
    ids = await tokens.lock_active_admins(session)
    assert ids == frozenset({activo.id, otro_activo.id})
    assert SYSTEM_USER_ID not in ids


async def test_lock_active_admins_toma_las_filas_con_for_update(
    dos_sesiones: tuple[AsyncSession, AsyncSession], reloj: FrozenClock, argon2_rapido: None
) -> None:
    primera, segunda = dos_sesiones
    await make_user(
        primera, role="admin", email=f"fu-{etiqueta()}@test.apex", password=CLAVE_PRUEBA
    )
    await tokens.lock_active_admins(primera)  # abre la transacción y retiene los candados
    try:
        await segunda.execute(text("SET LOCAL lock_timeout = '300ms'"))
        with pytest.raises(DBAPIError):
            await tokens.lock_active_admins(segunda)
    finally:
        await segunda.rollback()
        await primera.rollback()
