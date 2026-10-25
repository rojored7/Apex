"""Infraestructura de pruebas del api (US-012, T8; kit HTTP de S2-B1).

- `test_database_url`: `TEST_DATABASE_URL` (servicio `db_test`). Falla, no se salta,
  si no está definida (CRITICA-2 N-1).
- `migrated_database`: corre `alembic upgrade head` una vez por corrida.
- `engine`: engine async por prueba.
- `session`: una conexión en transacción externa y un savepoint por prueba; todo se
  revierte al terminar, así dos pruebas nunca ven las filas de la otra.

Kit de S2-B1 (plan del Sprint 2, sección 2; S2-D19 y E6):
- `proveedor_local`, `sin_llaves`, `bus_listo`: el bus listo dentro del savepoint (antes en
  `tests/crypto/conftest.py`).
- `reloj`: `FrozenClock` en `2026-10-21T15:00:00Z` vía `set_clock`; se restaura al salir.
- `argon2_rapido` y `seguridad`: argon2 con parámetros mínimos y llaves JWT de la sesión.
- `cargador_real`: registra `auth.service.load_active_principal` y al salir vuelve a
  `principal_double`.
- `app_http`: `httpx.AsyncClient` sobre `create_app(...)` sin lifespan; `get_session` cede la
  `session` de la prueba y hace commit (libera el savepoint) o rollback al salir. Una sola
  petición a la vez: todas comparten la misma sesión.
- `usuario_real` (fábrica) y `cabeceras(usuario)`: usuario real en `auth.users` con
  `hash_password` y access token real; cabeceras con `Bearer` y `Origin` del front.
- `dos_sesiones`: dos `AsyncSession` con commit real (concurrencia); al salir borra lo que
  dejaron en `settings.settings_sections`, `memberships.memberships` (S3-B1), `members.members`
  (S2-B7) y `plans.plans` (S2-B9), los usuarios `@test.apex` con sus refresh y tokens de un
  solo uso, y la cola que agregaron a `audit.audit_log` (`limpiar_tras_dos_sesiones`).

Kit de S2-B2 (plan del Sprint 2, sección 2, bloque B2; E7 y E9):
- Al importarse corre `load_module_services()` ANTES de importar y registrar
  `principal_double`: los services se suscriben al bus y el doble queda registrado al final.
- `restaurar_bus` (autouse): foto `{tipo: list(handlers)}` del bus y restauración al salir; la
  prueba que necesita un bus vacío lo vacía ella misma.
- `reset_rate_limit` (autouse): `ratelimit.reset_store()` antes y después de cada prueba.
- `capturar_eventos(*tipos)`: suscribe un capturador y al salir quita solo el suyo.
- `sleeper_nulo`: espía que reemplaza la espera del piso de login (S2-D39) sin dormir.
- `api_prueba` (la app de `app_http`) y `cliente_desde(ip)`: un cliente con otra IP de socket.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.cli import init_keys_files, key_paths_in
from app.core import db, events, ratelimit
from app.core.audit import AuditEntry, install_audit_listeners
from app.core.clock import FrozenClock, reset_clock, set_clock
from app.core.config import Settings, load_settings
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.oplog import install_oplog_listeners
from app.core.crypto.provider import configure_provider
from app.core.crypto.types import install_crypto_type_listeners
from app.core.events import DomainEvent
from app.core.security import (
    PrincipalLoader,
    configure_password_hasher,
    configure_security,
    create_access_token,
    register_principal_loader,
)
from app.main import load_module_services

# E7/E9: los services se importan (y suscriben sus handlers) antes de cualquier foto del bus y
# antes de registrar el doble; así `register_principal_loader(principal_double)` queda último.
load_module_services()

from tests.core._principal_double import principal_double  # noqa: E402

API_ROOT = Path(__file__).resolve().parents[1]

# US-016: los listeners de auditoría viven en la clase Session; en el api los instala
# create_app y aquí se instalan una vez para toda la suite.
install_audit_listeners()
install_oplog_listeners()  # US-029: igual que create_app
install_crypto_type_listeners()  # US-028: igual que create_app
# US-034 (M-2): el arranque exige un PrincipalLoader; hasta que auth registre el real
# (US-041), las pruebas usan este doble, que cada prueba puebla con `principal_double`.
register_principal_loader(principal_double)

# Instante fijo de las pruebas (plan del Sprint 2, sección 2).
T0 = datetime(2026, 10, 21, 15, 0, 0, tzinfo=UTC)
# Contraseña de los usuarios de prueba: cumple la política (12+ y no común).
CLAVE_PRUEBA = "Zanahoria-Lunar-42x"
# Parámetros de argon2 por defecto de `Settings`: los restaura `argon2_rapido`.
ARGON2_PRODUCCION = (3, 65536, 4)


def alembic_config_for(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.fail(
            "TEST_DATABASE_URL no está definida: las pruebas exigen el PostgreSQL 16 de prueba "
            "(db_test de infra/compose.dev.yml); no se saltan."
        )
    assert url.startswith("postgresql+asyncpg://"), url
    if not es_base_de_prueba(url):
        # LOW L9 de la revisión Python: `LIMPIEZA_DE_SESION` y `dos_sesiones` borran tablas
        # enteras; nunca contra una base que no sea la de prueba.
        pytest.fail("TEST_DATABASE_URL debe apuntar a una base cuyo nombre contenga 'test'.")
    return url


def es_base_de_prueba(url: str) -> bool:
    """Pura: el nombre de la base (el camino del DSN) contiene `test`."""
    return "test" in urlsplit(url).path.lstrip("/").lower()


@pytest.fixture(scope="session")
def claves_prueba(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Directorio con KEK, llave de firma y par JWT creados por `init-keys` (US-023)."""
    directorio = tmp_path_factory.mktemp("keys")
    init_keys_files(key_paths_in(directorio))
    return directorio


@pytest.fixture
def settings_prueba(tmp_path: Path, migrated_database: str, claves_prueba: Path) -> Settings:
    """`Settings` completa apuntando a `db_test` y a llaves reales, sin tocar el `.env` real."""
    rutas = key_paths_in(claves_prueba)
    test_database_url = migrated_database  # garantiza la base migrada y limpia de otras sesiones
    env = tmp_path / ".env"
    env.write_text(
        f"DATABASE_URL={test_database_url}\n"
        f"JWT_PRIVATE_KEY_PATH={rutas.jwt_private}\n"
        "CRYPTO_PROVIDER=local\n"
        f"CRYPTO_LOCAL_KEK_PATH={rutas.kek}\n"
        f"CRYPTO_LOCAL_SIGNING_KEY_PATH={rutas.signing_key}\n"
        "UPLOADS_DIR=/data/uploads\n"
        'CORS_ORIGINS=["http://localhost"]\n'
        "LOG_LEVEL=INFO\n"
        "ENV=dev\n",
        encoding="utf-8",
    )
    return load_settings(env_file=env)


@pytest.fixture(scope="session")
def alembic_config(test_database_url: str) -> Config:
    return alembic_config_for(test_database_url)


LIMPIAR_LLAVES = (
    "ALTER TABLE crypto.crypto_keys DISABLE TRIGGER USER",
    "DELETE FROM crypto.crypto_keys",
    "ALTER TABLE crypto.crypto_keys ENABLE TRIGGER USER",
)

# `settings.settings_sections` nace en `0005_settings` (S2-B1). Mientras no exista (Rojo de
# B1) la limpieza no la toca, para no romper el resto de la suite.
LIMPIAR_SETTINGS = (
    "DO $$ BEGIN IF to_regclass('settings.settings_sections') IS NOT NULL THEN "
    "DELETE FROM settings.settings_sections; END IF; END $$"
)

# S2-B2: lo que una prueba con commit real (`dos_sesiones`, CLI) o una corrida cortada haya
# dejado en `auth`. Nunca toca al usuario técnico ni a cuentas fuera del dominio de prueba.
LIMPIAR_AUTH = (
    "DELETE FROM auth.refresh_tokens",
    "DELETE FROM auth.one_time_tokens",
    "DELETE FROM auth.users WHERE email LIKE '%@test.apex' AND id <> "
    "'00000000-0000-0000-0000-000000000001'",
)

# S2-B7: los socios que una prueba con commit real (`dos_sesiones`) o una corrida cortada hayan
# dejado. `members.members` nace en `0006_members`: mientras no exista (Rojo de B7) no se toca.
LIMPIAR_MEMBERS = (
    "DO $$ BEGIN IF to_regclass('members.members') IS NOT NULL THEN "
    "DELETE FROM members.members; END IF; END $$"
)

# S2-B9: los planes que una prueba con commit real (`dos_sesiones`) o una corrida cortada hayan
# dejado. `plans.plans` nace en `0007_plans`: mientras no exista (Rojo de B9) no se toca.
LIMPIAR_PLANS = (
    "DO $$ BEGIN IF to_regclass('plans.plans') IS NOT NULL THEN "
    "DELETE FROM plans.plans; END IF; END $$"
)

# S3-B1 (D30, S3-D48, E1): las membresías que una prueba con commit real (`dos_sesiones`) o una
# corrida cortada hayan dejado. `memberships.memberships` nace en `0008_memberships`: mientras no
# exista (Rojo de B1) no se toca. Sus triggers rechazan `DELETE` (S3-D48): se apagan, se borra y se
# vuelven a encender UNO POR UNO con `ENABLE ALWAYS` (S3-D49). Nunca `ENABLE TRIGGER USER`: dejaría
# `tgenabled = 'O'` y `session_replication_role = replica` los saltaría
# (`tests/migrations/test_triggers_siempre_activos.py`).
# S3-B2 (E1, S3-D48): las congelaciones se borran PRIMERO (FK a la membresía), con la misma regla:
# apagar, borrar y encender por nombre con `ENABLE ALWAYS`. `membership_freezes` nace en
# `0009_membership_freezes`: mientras no exista (Rojo de B2) no se toca.
TRIGGERS_DE_MEMBERSHIPS = (
    "memberships_guard_identity",
    "memberships_forbid_delete",
    "memberships_forbid_truncate",
)
TRIGGERS_DE_CONGELACIONES = (
    "membership_freezes_append_only",
    "membership_freezes_forbid_truncate",
)
LIMPIAR_MEMBERSHIPS = (
    "DO $$ BEGIN IF to_regclass('memberships.membership_freezes') IS NOT NULL THEN "
    "ALTER TABLE memberships.membership_freezes DISABLE TRIGGER USER; "
    "DELETE FROM memberships.membership_freezes; "
    "ALTER TABLE memberships.membership_freezes "
    "ENABLE ALWAYS TRIGGER membership_freezes_append_only; "
    "ALTER TABLE memberships.membership_freezes "
    "ENABLE ALWAYS TRIGGER membership_freezes_forbid_truncate; "
    "END IF; "
    "IF to_regclass('memberships.memberships') IS NOT NULL THEN "
    "ALTER TABLE memberships.memberships DISABLE TRIGGER USER; "
    "DELETE FROM memberships.memberships; "
    "ALTER TABLE memberships.memberships ENABLE ALWAYS TRIGGER memberships_guard_identity; "
    "ALTER TABLE memberships.memberships ENABLE ALWAYS TRIGGER memberships_forbid_delete; "
    "ALTER TABLE memberships.memberships ENABLE ALWAYS TRIGGER memberships_forbid_truncate; "
    "END IF; END $$"
)

LIMPIEZA_DE_SESION = (
    # Las llaves se envuelven con la KEK temporal de esta sesión: las de sesiones previas
    # no se abren. Solo en db_test y con los triggers apagados.
    *LIMPIAR_LLAVES,
    "ALTER TABLE crypto.crypto_ops DISABLE TRIGGER USER",
    "DELETE FROM crypto.crypto_ops",
    "ALTER TABLE crypto.crypto_ops ENABLE TRIGGER USER",
    "ALTER TABLE audit.audit_log DISABLE TRIGGER USER",
    "DELETE FROM audit.audit_log",
    "ALTER TABLE audit.audit_log ENABLE TRIGGER USER",
    LIMPIAR_SETTINGS,  # E6: lo que `dos_sesiones` o una corrida cortada hayan confirmado
    *LIMPIAR_AUTH,
    LIMPIAR_MEMBERSHIPS,  # S3-B1 (sección 0 del plan del Sprint 3): antes que socios y planes
    LIMPIAR_MEMBERS,  # E6 y plan, sección 2 (B7)
    LIMPIAR_PLANS,  # E6 y plan, sección 2 (B9)
)


@pytest.fixture(scope="session")
def migrated_database(alembic_config: Config, test_database_url: str) -> str:
    command.upgrade(alembic_config, "head")

    async def limpiar() -> None:
        motor = create_async_engine(test_database_url, hide_parameters=True)
        try:
            async with motor.begin() as conn:
                for sql in LIMPIEZA_DE_SESION:
                    await conn.execute(text(sql))
        finally:
            await motor.dispose()

    asyncio.run(limpiar())
    return test_database_url


@pytest.fixture
async def engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    motor = create_async_engine(migrated_database, hide_parameters=True, echo=False)
    try:
        yield motor
    finally:
        await motor.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conexion:
        transaccion = await conexion.begin()
        fabrica = async_sessionmaker(
            bind=conexion, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with fabrica() as sesion:
            yield sesion
        await transaccion.rollback()


# Bus de criptografía (movidas desde tests/crypto/conftest.py; S2-D19) -----------------


@pytest.fixture
def proveedor_local(claves_prueba: Path) -> LocalFileProvider:
    rutas = key_paths_in(claves_prueba)
    return LocalFileProvider(rutas.kek, rutas.signing_key)


@pytest.fixture
async def sin_llaves(session: AsyncSession) -> AsyncSession:
    """Tabla `crypto_keys` vacía dentro del savepoint de la prueba (se revierte)."""
    for sql in LIMPIAR_LLAVES:
        await session.execute(text(sql))
    configure_keyring(None)
    return session


@pytest.fixture
async def bus_listo(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> AsyncIterator[Keyring]:
    """`ensure_keys` sobre base vacía: DEK y llaves de índice creadas y keyring cargado."""
    with actor_scope(SYSTEM_USER_ID):
        keyring = await ensure_keys(sin_llaves, proveedor_local)
    try:
        yield keyring
    finally:
        configure_keyring(None)


# Bus de eventos y límite de intentos (S2-B2; E7, riesgo 6.6) --------------------------------


@pytest.fixture(autouse=True)
def restaurar_bus() -> Iterator[None]:
    """Foto del bus antes de la prueba y restauración al salir (E7)."""
    foto = {tipo: list(handlers) for tipo, handlers in events._subscribers.items()}
    try:
        yield
    finally:
        events._subscribers.clear()
        events._subscribers.update(foto)


@pytest.fixture(autouse=True)
def reset_rate_limit() -> Iterator[None]:
    """Almacenes del límite vacíos antes y después de cada prueba."""
    ratelimit.reset_store()
    try:
        yield
    finally:
        ratelimit.reset_store()


CapturarEventos = Callable[..., list[Any]]


@pytest.fixture
def capturar_eventos() -> Iterator[CapturarEventos]:
    """`recibidos = capturar_eventos(LoginAttempted, SessionsRevoked)`; quita solo lo suyo."""
    suscritos: list[tuple[type[DomainEvent], Any]] = []

    def capturar(*tipos: type[DomainEvent]) -> list[Any]:
        recibidos: list[Any] = []

        async def capturador(evento: DomainEvent, sesion: AsyncSession) -> None:
            recibidos.append(evento)

        for tipo in tipos:
            events.subscribe(tipo, capturador)
            suscritos.append((tipo, capturador))
        return recibidos

    try:
        yield capturar
    finally:
        for tipo, capturador in suscritos:
            handlers = events._subscribers.get(tipo, [])
            if capturador in handlers:
                handlers.remove(capturador)


@dataclass
class SleeperEspia:
    """Registra cada espera pedida (segundos) sin dormir."""

    llamadas: list[float]

    async def __call__(self, segundos: float) -> None:
        self.llamadas.append(segundos)


@pytest.fixture
def sleeper_nulo() -> Iterator[SleeperEspia]:
    """Anula el piso de duración de login y forgot (S2-D39) y deja ver qué se pidió."""
    from app.modules.auth.service import configure_sleeper

    espia = SleeperEspia(llamadas=[])
    configure_sleeper(espia)
    try:
        yield espia
    finally:
        configure_sleeper(None)


# Reloj, argon2 y seguridad ---------------------------------------------------------------


@pytest.fixture
def reloj() -> Iterator[FrozenClock]:
    """Reloj congelado en `T0`; la prueba lo puede mover con `reloj.advance(...)`."""
    clock = FrozenClock(T0)
    token = set_clock(clock)
    try:
        yield clock
    finally:
        reset_clock(token)


def _argon2_minimo() -> None:
    configure_password_hasher(time_cost=1, memory_cost_kib=8, parallelism=1)


@pytest.fixture
def argon2_rapido() -> Iterator[None]:
    """argon2 con parámetros mínimos (solo pruebas); restaura los de `Settings` al salir."""
    _argon2_minimo()
    try:
        yield
    finally:
        configure_password_hasher(*ARGON2_PRODUCCION)


@pytest.fixture
def seguridad(settings_prueba: Settings, argon2_rapido: None) -> Settings:
    """Llaves JWT y política de `settings_prueba`; argon2 sigue en mínimos."""
    configure_security(settings_prueba)  # fija argon2 de `Settings`: se vuelve a bajar
    _argon2_minimo()
    return settings_prueba


@pytest.fixture
def cargador_real() -> Iterator[PrincipalLoader]:
    """El `PrincipalLoader` real de auth (lee `auth.users`); al salir vuelve el doble."""
    from app.modules.auth.service import load_active_principal

    register_principal_loader(load_active_principal)
    try:
        yield load_active_principal
    finally:
        register_principal_loader(principal_double)


# Cliente HTTP ------------------------------------------------------------------------------


@pytest.fixture
async def api_prueba(
    seguridad: Settings,
    session: AsyncSession,
    bus_listo: Keyring,
    proveedor_local: LocalFileProvider,
    cargador_real: PrincipalLoader,
    reloj: FrozenClock,
) -> AsyncIterator[FastAPI]:
    """La app real (sin lifespan) sobre la sesión de la prueba (S2-D19).

    El lifespan no corre: su `ensure_keys` confirmaría en otra conexión mientras el savepoint
    de la prueba tiene un `DELETE` abierto sobre `crypto_keys`. Seguridad, proveedor y
    keyring (`bus_listo`) se configuran aquí a mano. `app.state.settings` es la `Settings`
    que leen las rutas; una prueba puede reemplazarla con `model_copy(update=...)`.
    """
    from app.main import create_app

    aplicacion = create_app(seguridad, run_migrations_on_startup=False)
    register_principal_loader(cargador_real)  # create_app importa auth; manda el real
    configure_provider(proveedor_local)

    async def sesion_de_la_prueba() -> AsyncIterator[AsyncSession]:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
        else:
            await session.commit()  # libera el savepoint, como el commit de get_session

    aplicacion.dependency_overrides[db.get_session] = sesion_de_la_prueba
    try:
        yield aplicacion
    finally:
        aplicacion.dependency_overrides.clear()
        configure_provider(None)
        await db.dispose_engine()


@pytest.fixture
async def app_http(api_prueba: FastAPI) -> AsyncIterator[AsyncClient]:
    """Cliente HTTP de `api_prueba` (socket `127.0.0.1`)."""
    async with AsyncClient(transport=ASGITransport(app=api_prueba), base_url="http://t") as c:
        yield c


ClienteDesde = Callable[[str], AsyncClient]


@pytest.fixture
async def cliente_desde(api_prueba: FastAPI) -> AsyncIterator[ClienteDesde]:
    """`cliente_desde("2001:db8::1")`: cliente de `api_prueba` con esa IP de socket."""
    abiertos: list[AsyncClient] = []

    def crear(ip: str) -> AsyncClient:
        cliente = AsyncClient(
            transport=ASGITransport(app=api_prueba, client=(ip, 40000)), base_url="http://t"
        )
        abiertos.append(cliente)
        return cliente

    try:
        yield crear
    finally:
        for cliente in abiertos:
            await cliente.aclose()


# Usuarios reales y cabeceras ------------------------------------------------------------


@dataclass(frozen=True)
class UsuarioPrueba:
    """Usuario real en `auth.users`. `id`, `email` y `role` van aparte: tras un rollback de la
    sesión el `User` queda expirado y leer sus atributos dispararía una carga perezosa."""

    user: Any
    id: UUID
    email: str
    role: str
    password: str
    token: str


class CrearUsuario(Protocol):
    async def __call__(
        self,
        role: str = "coach",
        *,
        email: str | None = None,
        password: str | None = CLAVE_PRUEBA,
        member_id: UUID | None = None,
        activo: bool = True,
        bloqueado: bool = False,
        borrado: bool = False,
        debe_cambiar: bool = False,
    ) -> UsuarioPrueba: ...


@pytest.fixture
def usuario_real(session: AsyncSession, seguridad: Settings, reloj: FrozenClock) -> CrearUsuario:
    """Fábrica: `await usuario_real("admin")` crea el usuario (commit del savepoint) y su token.

    `password=None` deja la cuenta pendiente de activación (sin hash). `debe_cambiar` fija
    `must_change_password`, columna de `0005b_auth_security` (S2-B2): solo se envía cuando es
    verdadera, para que las pruebas que no la usan no dependan de la migración.
    """
    from tests.factories.users import make_user

    async def crear(
        role: str = "coach",
        *,
        email: str | None = None,
        password: str | None = CLAVE_PRUEBA,
        member_id: UUID | None = None,
        activo: bool = True,
        bloqueado: bool = False,
        borrado: bool = False,
        debe_cambiar: bool = False,
    ) -> UsuarioPrueba:
        extra: dict[str, Any] = {"must_change_password": True} if debe_cambiar else {}
        if borrado:
            extra["deleted_at"] = reloj.now_utc()
        usuario = await make_user(
            session,
            role=role,
            email=email,
            password=password,
            member_id=member_id,
            is_active=activo,
            locked_at=reloj.now_utc() if bloqueado else None,
            **extra,
        )
        token = create_access_token(usuario.id, role, usuario.member_id, reloj)  # type: ignore[arg-type]
        return UsuarioPrueba(usuario, usuario.id, usuario.email, role, password or "", token)

    return crear


Cabeceras = Callable[[UsuarioPrueba], dict[str, str]]


@pytest.fixture
def cabeceras(settings_prueba: Settings) -> Cabeceras:
    """`cabeceras(usuario)`: `Authorization: Bearer <token>` y el `Origin` del front (S2-D38)."""
    partes = urlsplit(settings_prueba.FRONT_BASE_URL)
    origen = f"{partes.scheme}://{partes.netloc}"

    def armar(usuario: UsuarioPrueba) -> dict[str, str]:
        return {"Authorization": f"Bearer {usuario.token}", "Origin": origen}

    return armar


# Concurrencia con commit real (E6) -----------------------------------------------------------


@pytest.fixture
async def dos_sesiones(engine: AsyncEngine) -> AsyncIterator[tuple[AsyncSession, AsyncSession]]:
    """Dos sesiones independientes (dos conexiones) con commit real, para `asyncio.gather`.

    No se combina con `session`: la transacción externa de esa fixture retiene el candado de la
    cadena de auditoría. Al salir borra las filas de `settings.settings_sections`, los socios
    (S2-B7), los planes (S2-B9), los usuarios `@test.apex` (con sus refresh y tokens de un solo
    uso) y las filas de auditoría agregadas desde el inicio (la cola de la cadena; el prefijo sigue
    válido).
    """
    async with engine.connect() as conexion:
        ultima_seq = await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0)))
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    primera, segunda = fabrica(), fabrica()
    try:
        yield primera, segunda
    finally:
        await primera.close()
        await segunda.close()
        await limpiar_tras_dos_sesiones(engine, ultima_seq or 0)


async def limpiar_tras_dos_sesiones(engine: AsyncEngine, ultima_seq: int) -> None:
    """Lo que borra el `finally` de `dos_sesiones` (en una función para que
    `tests/migrations/test_triggers_siempre_activos.py` pruebe exactamente esta limpieza).

    Orden (sección 0 del plan del Sprint 3): membresías antes que socios y planes.
    """
    async with engine.begin() as conexion:
        await conexion.execute(text(LIMPIAR_SETTINGS))
        await conexion.execute(text(LIMPIAR_MEMBERSHIPS))
        await conexion.execute(text(LIMPIAR_MEMBERS))
        await conexion.execute(text(LIMPIAR_PLANS))
        for sql in LIMPIAR_AUTH:
            await conexion.execute(text(sql))
        await conexion.execute(text("ALTER TABLE audit.audit_log DISABLE TRIGGER USER"))
        await conexion.execute(
            text("DELETE FROM audit.audit_log WHERE seq > :seq"), {"seq": ultima_seq}
        )
        await conexion.execute(text("ALTER TABLE audit.audit_log ENABLE TRIGGER USER"))
