"""`auth.service.login` con PostgreSQL real (S2-B2; US-042; blueprint 7.1 corregido por H-4,
M-6, L-4, L-8 y L-10).

Reloj congelado en `T0 = 2026-10-21T15:00:00Z` (fixture `reloj`), argon2 en mínimos y el piso de
duración anulado (`sleeper_nulo`, autouse en `tests/auth`). Las columnas nuevas de
`0005b_auth_security` se leen con SQL de texto. Un fallo confirma antes de lanzar (S2-D8): la
prueba hace `session.rollback()` (lo que haría `get_session`) y el efecto sigue ahí.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.errors import TooManyRequestsError
from app.core.security import (
    configure_password_hasher,
    decode_access_token,
    hash_opaque_token,
    needs_rehash,
)
from app.modules.auth import service
from app.modules.auth.exceptions import InvalidCredentials
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.service import LoginAttempted, SessionsRevoked, UserLocked
from tests.auth._sesion import IP_A, IP_A2, IP_B, EspiaArgon2, politica
from tests.conftest import CLAVE_PRUEBA, T0, CapturarEventos, CrearUsuario, SleeperEspia

ERRADA = "Otra-Clave-Distinta-77"
RAFAGA = 30


async def _login(
    session: AsyncSession,
    email: str,
    password: str = CLAVE_PRUEBA,
    *,
    ip: str = IP_A,
    ua: str | None = "pytest",
    **cambios: Any,
) -> service.LoginResult:
    """Un login y, si tiene éxito, el commit de `get_session` (una petición, una transacción)."""
    resultado = await service.login(
        session, email, password, ip=ip, user_agent=ua, policy=politica(**cambios)
    )
    await session.commit()
    return resultado


async def _falla(session: AsyncSession, email: str, password: str = ERRADA, **kw: Any) -> None:
    with pytest.raises(InvalidCredentials):
        await _login(session, email, password, **kw)
    await session.rollback()  # lo que hace `get_session` ante la excepción


async def _cuenta(session: AsyncSession, user_id: UUID) -> dict[str, Any]:
    fila = (
        await session.execute(
            text(
                "SELECT failed_login_count, locked_at, last_login_at, tokens_valid_after, "
                "password_hash FROM auth.users WHERE id = :id"
            ),
            {"id": user_id},
        )
    ).one()
    return dict(fila._mapping)


async def _refresh_de(session: AsyncSession, user_id: UUID) -> list[RefreshToken]:
    filas = await session.scalars(
        select(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .order_by(RefreshToken.created_at)
    )
    return list(filas.all())


# Camino feliz ------------------------------------------------------------------------------


async def test_login_correcto_deja_un_refresh_hasheado_a_7_dias_y_un_evento_ok(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    capturar_eventos: CapturarEventos,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    eventos = capturar_eventos(LoginAttempted)
    resultado = await _login(session, coach.email)

    assert resultado.expires_in == 900 and resultado.must_change_password is False
    assert resultado.user.id == coach.id and resultado.user.role == "coach"
    claims = decode_access_token(resultado.access_token, reloj)
    assert claims.sub == coach.id and claims.iat == int(T0.timestamp())
    [fila] = await _refresh_de(session, coach.id)
    assert fila.token_hash != resultado.refresh_token
    assert fila.token_hash == hash_opaque_token(resultado.refresh_token)
    assert len(fila.token_hash) == 64
    assert fila.expires_at == T0 + timedelta(days=7)
    assert fila.revoked_at is None and fila.replaced_by_id is None
    assert fila.user_agent == "pytest"
    familia = await session.scalar(
        text("SELECT family_started_at FROM auth.refresh_tokens WHERE id = :id"), {"id": fila.id}
    )
    assert familia == T0  # sale del reloj de la app, no de now() de SQL (E8)
    cuenta = await _cuenta(session, coach.id)
    assert cuenta["last_login_at"] == T0 and cuenta["failed_login_count"] == 0
    assert [(e.user_id, e.result, e.reason, e.ip, e.user_agent) for e in eventos] == [
        (coach.id, "ok", None, IP_A, "pytest")
    ]


async def test_el_correo_se_normaliza_antes_de_buscar(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach", email="coach.norma@test.apex")
    resultado = await _login(session, "  Coach.Norma@Test.Apex ")
    assert resultado.user.id == coach.id


async def test_user_agent_largo_se_trunca_a_120_en_el_evento_y_a_255_en_la_fila(
    session: AsyncSession, usuario_real: CrearUsuario, capturar_eventos: CapturarEventos
) -> None:
    """L-8: el evento lleva `ip` y el agente hasta 120 caracteres; nunca el correo."""
    coach = await usuario_real("coach")
    eventos = capturar_eventos(LoginAttempted)
    largo = "Mozilla/5.0 " + "x" * 300
    await _login(session, coach.email, ua=largo)
    [fila] = await _refresh_de(session, coach.id)
    assert fila.user_agent == largo[:255]
    [evento] = eventos
    assert evento.user_agent == largo[:120] and evento.ip == IP_A
    assert coach.email not in repr(evento)


# Fallos ------------------------------------------------------------------------------------


async def test_contrasena_errada_suma_un_fallo_que_sobrevive_al_401(
    session: AsyncSession, usuario_real: CrearUsuario, capturar_eventos: CapturarEventos
) -> None:
    coach = await usuario_real("coach")
    eventos = capturar_eventos(LoginAttempted)
    await _falla(session, coach.email)
    cuenta = await _cuenta(session, coach.id)
    assert cuenta["failed_login_count"] == 1
    assert cuenta["last_login_at"] is None
    assert await _refresh_de(session, coach.id) == []
    assert [(e.user_id, e.result, e.reason, e.ip) for e in eventos] == [
        (coach.id, "failed", "bad_password", IP_A)
    ]


@pytest.mark.parametrize("caso", ["inexistente", "tecnico", "borrado"])
async def test_inexistente_tecnico_y_borrado_no_emiten_eventos_y_usan_dummy_verify(
    caso: str,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    capturar_eventos: CapturarEventos,
    espia_argon2: EspiaArgon2,
) -> None:
    """N-31 y M-6: sin evento ni escritura; exactamente una verificación, contra el ficticio."""
    if caso == "inexistente":
        correo = "nadie@test.apex"
    elif caso == "tecnico":
        correo = "system@apex.local"
    else:
        correo = (await usuario_real("coach", borrado=True)).email
    espia_argon2.reiniciar()
    eventos = capturar_eventos(LoginAttempted, UserLocked, SessionsRevoked)
    await _falla(session, correo, CLAVE_PRUEBA)
    assert eventos == []
    assert (espia_argon2.ficticias, espia_argon2.reales) == (1, 0)


async def test_bloqueado_inactivo_y_pendiente_dan_el_mismo_invalid_credentials(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    capturar_eventos: CapturarEventos,
    espia_argon2: EspiaArgon2,
) -> None:
    bloqueado = await usuario_real("coach", bloqueado=True)
    inactivo = await usuario_real("coach", activo=False)
    pendiente = await usuario_real("coach", password=None)
    eventos = capturar_eventos(LoginAttempted)
    errores: list[tuple[str, str, int]] = []
    verificaciones: list[tuple[int, int]] = []
    for usuario in (bloqueado, inactivo, pendiente):
        espia_argon2.reiniciar()
        with pytest.raises(InvalidCredentials) as excinfo:
            await _login(session, usuario.email, CLAVE_PRUEBA)
        await session.rollback()
        errores.append((excinfo.value.code, excinfo.value.message, excinfo.value.status))
        verificaciones.append((espia_argon2.reales, espia_argon2.ficticias))
    assert len(set(errores)) == 1
    assert errores[0] == ("invalid_credentials", "Correo o contraseña incorrectos.", 401)
    # M-6: con la contraseña correcta, bloqueado e inactivo verifican contra su hash real; el
    # pendiente (sin hash) nunca llama a verify_password(None, ...): usa dummy_verify.
    assert verificaciones == [(1, 0), (1, 0), (0, 1)]
    assert [(e.user_id, e.result, e.reason) for e in eventos] == [
        (bloqueado.id, "failed", "locked"),
        (inactivo.id, "failed", "inactive"),
        (pendiente.id, "failed", "pending"),
    ]
    # La contraseña era correcta: ninguno suma fallos.
    for usuario in (bloqueado, inactivo):
        assert (await _cuenta(session, usuario.id))["failed_login_count"] == 0


async def test_una_sola_verificacion_real_en_el_exito_y_en_la_contrasena_errada(
    session: AsyncSession, usuario_real: CrearUsuario, espia_argon2: EspiaArgon2
) -> None:
    coach = await usuario_real("coach")
    espia_argon2.reiniciar()
    await _falla(session, coach.email)
    assert (espia_argon2.reales, espia_argon2.ficticias) == (1, 0)
    espia_argon2.reiniciar()
    await _login(session, coach.email)
    assert (espia_argon2.reales, espia_argon2.ficticias) == (1, 0)


async def test_un_hash_con_parametros_viejos_se_rehace_al_entrar(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")  # hash con memory_cost=8 (argon2_rapido)
    antes = (await _cuenta(session, coach.id))["password_hash"]
    configure_password_hasher(time_cost=1, memory_cost_kib=16, parallelism=1)
    assert needs_rehash(antes) is True
    await _login(session, coach.email)
    despues = (await _cuenta(session, coach.id))["password_hash"]
    assert despues != antes and needs_rehash(despues) is False


# Piso de duración (M-6, S2-D39) -------------------------------------------------------------


async def test_el_piso_se_aplica_a_los_401_y_no_al_exito(
    session: AsyncSession, usuario_real: CrearUsuario, sleeper_nulo: SleeperEspia
) -> None:
    coach = await usuario_real("coach")
    sleeper_nulo.llamadas.clear()
    await _falla(session, coach.email, min_duration_ms=400)
    await _falla(session, "nadie@test.apex", min_duration_ms=400)
    assert len(sleeper_nulo.llamadas) == 2
    assert all(0 < espera <= 0.4 for espera in sleeper_nulo.llamadas), sleeper_nulo.llamadas
    sleeper_nulo.llamadas.clear()
    await _login(session, coach.email, min_duration_ms=400)
    assert sleeper_nulo.llamadas == []


# Límite por cuenta (H-4, S2-D10) --------------------------------------------------------------


async def test_solo_cuentan_los_fallos(session: AsyncSession, usuario_real: CrearUsuario) -> None:
    coach = await usuario_real("coach")
    for _ in range(12):  # más que LOGIN_ACCOUNT_LIMIT=10: los éxitos no consumen el cupo
        await _login(session, coach.email)
    assert len(await _refresh_de(session, coach.id)) == 12


async def test_diez_fallos_desde_una_ip_no_impiden_entrar_desde_otra(
    session: AsyncSession, usuario_real: CrearUsuario, espia_argon2: EspiaArgon2
) -> None:
    """Revisión de seguridad V10 (N-3): la clave por cuenta es (correo, IPv4 exacta); antes de
    la revisión era la red /24 y esta prueba fijaba el 429 desde `IP_A2`. Actualizada por
    decisión del orquestador (docs/scratch/sprint-02-revision-backend.md)."""
    coach = await usuario_real("coach")
    for _ in range(10):
        await _falla(session, coach.email, ip=IP_A)
    espia_argon2.reiniciar()
    with pytest.raises(TooManyRequestsError):  # la misma IP, aun con la contraseña correcta
        await _login(session, coach.email, ip=IP_A)
    assert espia_argon2.total == 0, "el 429 por cuenta llega antes de argon2"
    resultado = await _login(session, coach.email, ip=IP_B)
    assert resultado.user.id == coach.id
    assert (await _cuenta(session, coach.id))["failed_login_count"] == 0


async def test_dos_ips_del_mismo_24_no_comparten_el_cupo_por_cuenta(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """N-3: en la LAN del gimnasio (un solo /24) un dispositivo con diez fallos no niega el
    login de la cuenta a los demás; el tope global por correo y el bloqueo a 20 siguen."""
    coach = await usuario_real("coach")
    for _ in range(10):
        await _falla(session, coach.email, ip=IP_A)
    resultado = await _login(session, coach.email, ip=IP_A2)  # mismo /24 que IP_A
    assert resultado.user.id == coach.id


async def test_el_limite_por_cuenta_vale_igual_para_un_correo_inexistente(
    session: AsyncSession, espia_argon2: EspiaArgon2, seguridad: object
) -> None:
    """Misma respuesta que para un correo existente: el 429 no enumera cuentas."""
    for _ in range(10):
        await _falla(session, "nadie@test.apex", CLAVE_PRUEBA, ip=IP_A)
    espia_argon2.reiniciar()
    with pytest.raises(TooManyRequestsError):
        await _login(session, "nadie@test.apex", ip=IP_A)
    assert espia_argon2.total == 0


async def test_tope_global_por_cuenta_entre_redes_distintas(
    session: AsyncSession, usuario_real: CrearUsuario, espia_argon2: EspiaArgon2
) -> None:
    coach = await usuario_real("coach")
    for i in range(5):
        await _falla(
            session, coach.email, ip=f"192.0.{i}.10", account_limit=3, account_global_limit=5
        )
    espia_argon2.reiniciar()
    with pytest.raises(TooManyRequestsError):
        await _login(session, coach.email, ip="192.0.9.10", account_limit=3, account_global_limit=5)
    assert espia_argon2.total == 0


async def test_el_ultimo_admin_activo_solo_tiene_el_limite_por_ip_y_argon2(
    session: AsyncSession, usuario_real: CrearUsuario, capturar_eventos: CapturarEventos
) -> None:
    """H-4.3 y S2-D10.5: ni límite por cuenta, ni tope global, ni bloqueo persistente."""
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
    assert activos == 1, "la prueba exige un único admin activo"
    bloqueos = capturar_eventos(UserLocked)
    for _ in range(8):
        await _falla(
            session,
            admin.email,
            ip=IP_A,
            account_limit=3,
            account_global_limit=5,
            lock_after=6,
        )
    cuenta = await _cuenta(session, admin.id)
    assert cuenta["failed_login_count"] == 8 and cuenta["locked_at"] is None
    assert bloqueos == []
    resultado = await _login(session, admin.email, ip=IP_A, account_limit=3, lock_after=6)
    assert resultado.user.id == admin.id


# Bloqueo persistente (S2-D10.4) -----------------------------------------------------------------


async def test_veinte_fallos_consecutivos_bloquean_y_cierran_las_sesiones(
    session: AsyncSession, usuario_real: CrearUsuario, capturar_eventos: CapturarEventos
) -> None:
    coach = await usuario_real("coach")
    await _login(session, coach.email)  # una sesión viva antes de los fallos
    eventos = capturar_eventos(UserLocked, SessionsRevoked, LoginAttempted)
    sin_limite = {"account_limit": 1000, "account_global_limit": 1000}
    for _ in range(19):
        await _falla(session, coach.email, **sin_limite)
    assert (await _cuenta(session, coach.id))["locked_at"] is None
    await _falla(session, coach.email, **sin_limite)
    cuenta = await _cuenta(session, coach.id)
    assert cuenta["failed_login_count"] == 20
    assert cuenta["locked_at"] == T0
    assert cuenta["tokens_valid_after"] == T0  # H-3: revoke_all corta los access ya emitidos
    [bloqueo] = [e for e in eventos if isinstance(e, UserLocked)]
    assert (bloqueo.user_id, bloqueo.by, bloqueo.reason) == (
        coach.id,
        SYSTEM_USER_ID,
        "too_many_failures",
    )
    [revocadas] = [e for e in eventos if isinstance(e, SessionsRevoked)]
    assert (revocadas.user_id, revocadas.by, revocadas.reason, revocadas.revoked) == (
        coach.id,
        SYSTEM_USER_ID,
        "lock",
        1,
    )
    assert all(f.revoked_at is not None for f in await _refresh_de(session, coach.id))
    eventos.clear()
    await _falla(session, coach.email, CLAVE_PRUEBA, **sin_limite)  # correcta, pero bloqueado
    assert [(e.result, e.reason) for e in eventos if isinstance(e, LoginAttempted)] == [
        ("failed", "locked")
    ]


async def test_un_exito_reinicia_el_contador_consecutivo(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    sin_limite = {"account_limit": 1000, "account_global_limit": 1000}
    for _ in range(15):
        await _falla(session, coach.email, **sin_limite)
    await _login(session, coach.email, **sin_limite)
    assert (await _cuenta(session, coach.id))["failed_login_count"] == 0
    for _ in range(19):
        await _falla(session, coach.email, **sin_limite)
    cuenta = await _cuenta(session, coach.id)
    assert cuenta["failed_login_count"] == 19 and cuenta["locked_at"] is None


# Purga oportunista (L-4) -----------------------------------------------------------------------


async def test_el_login_purga_solo_los_refresh_vencidos_hace_mas_de_30_dias(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    viejos = {
        "hace-31": T0 - timedelta(days=31),
        "hace-29": T0 - timedelta(days=29),
        "vigente": T0 + timedelta(days=1),
    }
    ids: dict[str, UUID] = {}
    with actor_scope(SYSTEM_USER_ID):
        for nombre, vence in viejos.items():
            fila = RefreshToken(
                user_id=coach.id,
                token_hash=hash_opaque_token(f"token-{nombre}"),
                expires_at=vence,
                created_by=SYSTEM_USER_ID,
            )
            session.add(fila)
            await session.flush()
            ids[nombre] = fila.id
        await session.commit()
    await _login(session, coach.email)
    quedan = {f.id for f in await _refresh_de(session, coach.id)}
    assert ids["hace-31"] not in quedan
    assert {ids["hace-29"], ids["vigente"]} <= quedan
    assert len(quedan) == 3  # los dos que quedan y el nuevo


# Concurrencia (L-10; Python M2) -------------------------------------------------------------------


async def test_una_rafaga_paralela_no_supera_el_tope_por_cuenta(
    migrated_database: str, seguridad: object, reloj: FrozenClock, espia_argon2: EspiaArgon2
) -> None:
    """Revisión Python M2: el cupo por cuenta se reserva (`hit`) antes de argon2 y se devuelve
    si el login sale bien. Antes era `peek` + `record` al fallar: 30 peticiones simultáneas
    pasaban todas el `peek` y cada una pagaba un argon2."""
    motor = create_async_engine(migrated_database, pool_size=RAFAGA, max_overflow=0)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    sesiones = [fabrica() for _ in range(RAFAGA)]
    try:
        resultados = await asyncio.gather(
            *(
                service.login(
                    s, "rafaga@test.apex", ERRADA, ip=IP_A, user_agent=None, policy=politica()
                )
                for s in sesiones
            ),
            return_exceptions=True,
        )
    finally:
        for s in sesiones:
            await s.close()
        await motor.dispose()
    rechazos = [r for r in resultados if isinstance(r, TooManyRequestsError)]
    fallos = [r for r in resultados if isinstance(r, InvalidCredentials)]
    assert len(fallos) + len(rechazos) == RAFAGA, resultados
    assert espia_argon2.total <= politica().account_limit
    assert len(fallos) == espia_argon2.total


async def test_un_login_correcto_devuelve_el_cupo_reservado(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """M2: el éxito no consume el cupo (como antes, cuando solo se sumaban los fallos)."""
    coach = await usuario_real("coach")
    for _ in range(9):
        await _falla(session, coach.email, ip=IP_A)
    for _ in range(3):  # cada éxito reserva y devuelve: el décimo cupo sigue libre
        await _login(session, coach.email, ip=IP_A)
    await _falla(session, coach.email, ip=IP_A)
    with pytest.raises(TooManyRequestsError):
        await _login(session, coach.email, ip=IP_A)


async def test_dos_fallos_concurrentes_suman_dos(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    seguridad: object,
    reloj: FrozenClock,
) -> None:
    """`UPDATE ... RETURNING` atómico: dos fallos simultáneos nunca pierden un conteo."""
    from tests.factories.users import make_user

    primera, segunda = dos_sesiones
    usuario = await make_user(primera, role="coach", password=CLAVE_PRUEBA)
    usuario_id, correo = usuario.id, usuario.email
    resultados = await asyncio.gather(
        _login(primera, correo, ERRADA, ip=IP_A),
        _login(segunda, correo, ERRADA, ip=IP_B),
        return_exceptions=True,
    )
    assert all(isinstance(r, InvalidCredentials) for r in resultados), resultados
    await primera.rollback()
    total = await primera.scalar(
        text("SELECT failed_login_count FROM auth.users WHERE id = :id"), {"id": usuario_id}
    )
    assert total == 2
