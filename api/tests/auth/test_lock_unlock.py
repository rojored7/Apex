"""`auth.service.lock` y `auth.service.unlock` con PostgreSQL real (S2-B5; US-050; S2-D10,
H-4.5, H-3, S2-D37, S2-D49; revisión S2-B4 MEDIUM-1).

`lock(session, user_id, *, by)`:
- `get_alive_or_404` (borrada, técnico e inexistente: `UserNotFound`), `lock_active_admins`,
  `lock_precondition` (`CannotLockSelf`, `AlreadyLocked`, `LastAdmin`, en ese orden);
- `locked_at = ahora` por el ORM (queda el `update` auditado por el admin), `revoke_all`
  (refresh revocados y `tokens_valid_after` = ahora truncado);
- eventos en este orden: `UserLocked(user_id, by, reason="admin")` y
  `SessionsRevoked(user_id, by, revoked=n, reason="lock")`, también con `n = 0`;
- todo en una transacción: si un handler de `UserLocked` lanza, no queda `locked_at` ni
  sesiones revocadas.
`unlock(session, user_id, *, by)`:
- `NotLocked` si la cuenta no está bloqueada; borrada, técnico e inexistente `UserNotFound`;
- `locked_at = None` y `failed_login_count = 0`; olvida los contadores en memoria del límite
  por cuenta de ese correo (`ratelimit.forget` de `login-account`, con todas sus redes, y de
  `login-account-global`), sin tocar los de otra cuenta;
- cierra los enlaces de un solo uso abiertos (decisión S2-B4: el bloqueo no los cierra);
- las sesiones siguen revocadas y `tokens_valid_after` no cambia; no emite eventos de dominio.
Reloj congelado en `T0`; el bloqueo ocurre en `T0 + 1 s`.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events, ratelimit
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.core.errors import TooManyRequestsError
from app.modules.auth import service
from app.modules.auth.exceptions import (
    AlreadyLocked,
    CannotLockSelf,
    LastAdmin,
    NotLocked,
    UserNotFound,
)
from app.modules.auth.models import User
from app.modules.auth.service import (
    ACCOUNT_BUCKET,
    ACCOUNT_GLOBAL_BUCKET,
    SessionsRevoked,
    UserLocked,
)
from tests.auth._ciclo import EVENTOS_DE_CUENTA, como, entrar, sesiones_vivas
from tests.auth._cuentas import (
    avanzar,
    es_update_del_hook,
    fila_usuario,
    filas_auditoria,
    filas_refresh,
    tokens_de,
)
from tests.auth._sesion import IP_A, IP_B
from tests.conftest import T0, CapturarEventos, CrearUsuario, UsuarioPrueba
from tests.factories.users import make_one_time_token

T1 = T0 + timedelta(seconds=1)


class HandlerRoto(Exception):
    """El doble de un handler que falla (no `RuntimeError`: `NotImplementedError` lo es)."""


async def _bloquear(session: AsyncSession, admin: UsuarioPrueba | UUID, objetivo: UUID) -> User:
    quien = admin if isinstance(admin, UUID) else admin.id
    with como(quien):
        usuario = await service.lock(session, objetivo, by=quien)
        await session.commit()
    return usuario


async def _desbloquear(session: AsyncSession, admin: UsuarioPrueba, objetivo: UUID) -> User:
    with como(admin):
        usuario = await service.unlock(session, objetivo, by=admin.id)
        await session.commit()
    return usuario


async def _rechazo(
    session: AsyncSession, metodo: str, por: UUID, objetivo: UUID, tipo: type[Exception]
) -> Exception:
    funcion = service.lock if metodo == "lock" else service.unlock
    with como(por), pytest.raises(tipo) as excinfo:
        await funcion(session, objetivo, by=por)
    await session.rollback()
    return excinfo.value


# lock ------------------------------------------------------------------------------------


async def test_lock_fija_locked_at_y_lo_audita_por_el_admin(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    avanzar(reloj, 1)
    usuario = await _bloquear(session, admin, coach.id)
    assert usuario.id == coach.id and usuario.locked_at == T1
    fila = await fila_usuario(session, coach.id)
    assert fila["locked_at"] == T1
    updates = [
        f for f in await filas_auditoria(session, "auth.users", coach.id) if es_update_del_hook(f)
    ]
    assert len(updates) == 1
    assert updates[0]["user_id"] == admin.id
    assert updates[0]["before"]["locked_at"] is None
    assert updates[0]["after"]["locked_at"] is not None


async def test_lock_revoca_las_sesiones_y_fija_el_corte(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await entrar(session, coach)
    await entrar(session, coach)
    avanzar(reloj, 1)
    await _bloquear(session, admin, coach.id)
    assert await sesiones_vivas(session, coach.id, T1) == 0
    assert all(f.revoked_at == T1 for f in await filas_refresh(session, coach.id))
    assert (await fila_usuario(session, coach.id))["tokens_valid_after"] == T1


async def test_lock_emite_user_locked_y_sessions_revoked_en_orden(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await entrar(session, coach)
    recibidos = capturar_eventos(UserLocked, SessionsRevoked)
    avanzar(reloj, 1)
    await _bloquear(session, admin, coach.id)
    assert recibidos == [
        UserLocked(user_id=coach.id, by=admin.id, reason="admin"),
        SessionsRevoked(user_id=coach.id, by=admin.id, revoked=1, reason="lock"),
    ]


async def test_lock_sin_sesiones_emite_sessions_revoked_con_cero(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    recibidos = capturar_eventos(SessionsRevoked)
    avanzar(reloj, 1)
    await _bloquear(session, admin, coach.id)
    assert recibidos == [SessionsRevoked(user_id=coach.id, by=admin.id, revoked=0, reason="lock")]


async def test_si_un_handler_de_user_locked_falla_no_queda_nada(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await entrar(session, coach)

    async def falla(evento: UserLocked, sesion: AsyncSession) -> None:
        raise HandlerRoto("handler roto")

    events.subscribe(UserLocked, falla)
    avanzar(reloj, 1)
    with como(admin), pytest.raises(HandlerRoto):
        await service.lock(session, coach.id, by=admin.id)
    await session.rollback()
    fila = await fila_usuario(session, coach.id)
    assert fila["locked_at"] is None
    assert fila["tokens_valid_after"] is None
    assert await sesiones_vivas(session, coach.id, T1) == 1


async def test_un_admin_no_se_bloquea_a_si_mismo(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    await usuario_real("admin")
    await _rechazo(session, "lock", admin.id, admin.id, CannotLockSelf)
    assert (await fila_usuario(session, admin.id))["locked_at"] is None


async def test_bloquear_una_cuenta_bloqueada_da_already_locked(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    admin = await usuario_real("admin")
    bloqueado = await usuario_real("coach", bloqueado=True)
    recibidos = capturar_eventos(*EVENTOS_DE_CUENTA)
    avanzar(reloj, 1)
    await _rechazo(session, "lock", admin.id, bloqueado.id, AlreadyLocked)
    assert (await fila_usuario(session, bloqueado.id))["locked_at"] == T0
    assert recibidos == []


async def test_bloquear_al_ultimo_admin_activo_da_last_admin(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """Por HTTP no se llega (quien bloquea ya es otro admin activo); el service lo cubre igual
    con un `by` que no es admin activo (el técnico o un coach)."""
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await usuario_real("admin", password=None)  # pendiente: no releva
    for por in (SYSTEM_USER_ID, coach.id):
        await _rechazo(session, "lock", por, admin.id, LastAdmin)
    assert (await fila_usuario(session, admin.id))["locked_at"] is None


async def test_con_dos_admins_uno_bloquea_al_otro(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    avanzar(reloj, 1)
    usuario = await _bloquear(session, admin, otro.id)
    assert usuario.locked_at == T1


@pytest.mark.parametrize("metodo", ["lock", "unlock"])
async def test_borrada_tecnico_o_inexistente_dan_404(
    metodo: str, session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    borrado = await usuario_real("coach", borrado=True, bloqueado=(metodo == "unlock"))
    for objetivo in (borrado.id, SYSTEM_USER_ID, uuid4()):
        await _rechazo(session, metodo, admin.id, objetivo, UserNotFound)


async def test_el_bloqueado_ya_no_autentica(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await _bloquear(session, admin, coach.id)
    assert await service.load_active_principal(session, coach.id) is None


# unlock ----------------------------------------------------------------------------------


async def test_unlock_limpia_locked_at_y_el_contador_y_lo_audita(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    bloqueado = await usuario_real("coach", bloqueado=True)
    await session.execute(
        User.__table__.update()
        .where(User.__table__.c.id == bloqueado.id)
        .values(failed_login_count=20)
    )
    await session.commit()
    usuario = await _desbloquear(session, admin, bloqueado.id)
    assert usuario.locked_at is None
    fila = await fila_usuario(session, bloqueado.id)
    assert (fila["locked_at"], fila["failed_login_count"]) == (None, 0)
    updates = [
        f
        for f in await filas_auditoria(session, "auth.users", bloqueado.id)
        if f["action"] == "update"
    ]
    assert len(updates) == 1
    assert updates[0]["user_id"] == admin.id
    assert updates[0]["before"]["locked_at"] is not None
    assert updates[0]["after"]["locked_at"] is None
    assert "failed_login_count" not in updates[0]["after"]  # fuera de la auditoría (L-10)
    assert await service.load_active_principal(session, bloqueado.id) is not None


async def _agotado(bucket: str, clave: str, *, kind: ratelimit.KeyKind = "account") -> bool:
    """¿La clave tiene al menos una marca? (`enforce` con tope 1 y sin sumar)."""
    try:
        await ratelimit.enforce(bucket, clave, limit=1, window_s=3600, kind=kind, count=False)
    except TooManyRequestsError:
        return True
    return False


async def test_unlock_olvida_los_contadores_en_memoria_de_esa_cuenta(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    bloqueado = await usuario_real("coach", bloqueado=True)
    ajeno = "ajeno@test.apex"
    claves = [
        (ACCOUNT_BUCKET, f"{bloqueado.email}|{ratelimit.ip_bucket_key(IP_A)}", "account"),
        (ACCOUNT_BUCKET, f"{bloqueado.email}|{ratelimit.ip_bucket_key(IP_B)}", "account"),
        (ACCOUNT_GLOBAL_BUCKET, bloqueado.email, "account-global"),
    ]
    ajenas = [
        (ACCOUNT_BUCKET, f"{ajeno}|{ratelimit.ip_bucket_key(IP_A)}", "account"),
        (ACCOUNT_GLOBAL_BUCKET, ajeno, "account-global"),
    ]
    for bucket, clave, kind in [*claves, *ajenas]:
        await ratelimit.record(bucket, clave, window_s=900, kind=kind)  # type: ignore[arg-type]
    for bucket, clave, kind in [*claves, *ajenas]:
        assert await _agotado(bucket, clave, kind=kind)  # type: ignore[arg-type]

    await _desbloquear(session, admin, bloqueado.id)

    for bucket, clave, kind in claves:
        assert not await _agotado(bucket, clave, kind=kind), clave  # type: ignore[arg-type]
    for bucket, clave, kind in ajenas:
        assert await _agotado(bucket, clave, kind=kind), clave  # type: ignore[arg-type]


async def test_unlock_deja_las_sesiones_revocadas_y_el_corte(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await entrar(session, coach)
    avanzar(reloj, 1)
    await _bloquear(session, admin, coach.id)
    avanzar(reloj, 5)
    await _desbloquear(session, admin, coach.id)
    assert await sesiones_vivas(session, coach.id, T1) == 0
    assert all(f.revoked_at == T1 for f in await filas_refresh(session, coach.id))
    assert (await fila_usuario(session, coach.id))["tokens_valid_after"] == T1


async def test_unlock_no_emite_eventos_de_dominio(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    admin = await usuario_real("admin")
    bloqueado = await usuario_real("coach", bloqueado=True)
    recibidos = capturar_eventos(*EVENTOS_DE_CUENTA)
    await _desbloquear(session, admin, bloqueado.id)
    assert recibidos == []


async def test_unlock_cierra_los_enlaces_abiertos(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """Decisión de S2-B4 (MEDIUM-1): el bloqueo no cierra los enlaces (un bloqueado no puede
    usarlos); el desbloqueo sí, para que uno emitido antes no reviva."""
    admin = await usuario_real("admin")
    bloqueado = await usuario_real("coach", bloqueado=True)
    await make_one_time_token(session, bloqueado, "reset", expires_in=timedelta(hours=1))
    avanzar(reloj, 1)
    await _desbloquear(session, admin, bloqueado.id)
    (enlace,) = await tokens_de(session, bloqueado.id)
    assert enlace.used_at == T1
    cierres = [
        f
        for f in await filas_auditoria(session, "auth.one_time_tokens", enlace.id)
        if f["action"] == "update"
    ]
    assert [f["user_id"] for f in cierres] == [admin.id]


async def test_unlock_de_una_cuenta_no_bloqueada_da_not_locked(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    error = await _rechazo(session, "unlock", admin.id, coach.id, NotLocked)
    assert (getattr(error, "status", None), getattr(error, "code", None)) == (409, "not_locked")
    updates = [
        f for f in await filas_auditoria(session, "auth.users", coach.id) if f["action"] == "update"
    ]
    assert updates == []


async def test_bloquear_y_desbloquear_vuelve_a_dejar_entrar(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    avanzar(reloj, 1)
    await _bloquear(session, admin, coach.id)
    avanzar(reloj, 1)
    await _desbloquear(session, admin, coach.id)
    refresh = await entrar(session, coach)
    assert refresh
    assert await sesiones_vivas(session, coach.id, T1 + timedelta(seconds=1)) == 1
