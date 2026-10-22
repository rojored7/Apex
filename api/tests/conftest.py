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
  dejaron en `settings.settings_sections` y la cola que agregaron a `audit.audit_log`.
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
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.cli import init_keys_files, key_paths_in
from app.core import db
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
from app.core.security import (
    PrincipalLoader,
    configure_password_hasher,
    configure_security,
    create_access_token,
    register_principal_loader,
)
from tests.core._principal_double import principal_double

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
    return url


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
async def app_http(
    seguridad: Settings,
    session: AsyncSession,
    bus_listo: Keyring,
    proveedor_local: LocalFileProvider,
    cargador_real: PrincipalLoader,
    reloj: FrozenClock,
) -> AsyncIterator[AsyncClient]:
    """Cliente del api real (sin lifespan) sobre la sesión de la prueba (S2-D19).

    El lifespan no corre: su `ensure_keys` confirmaría en otra conexión mientras el savepoint
    de la prueba tiene un `DELETE` abierto sobre `crypto_keys`. Seguridad, proveedor y
    keyring (`bus_listo`) se configuran aquí a mano.
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
        async with AsyncClient(
            transport=ASGITransport(app=aplicacion), base_url="http://t"
        ) as cliente:
            yield cliente
    finally:
        aplicacion.dependency_overrides.clear()
        configure_provider(None)
        await db.dispose_engine()


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
        password: str = CLAVE_PRUEBA,
        member_id: UUID | None = None,
        activo: bool = True,
        bloqueado: bool = False,
    ) -> UsuarioPrueba: ...


@pytest.fixture
def usuario_real(session: AsyncSession, seguridad: Settings, reloj: FrozenClock) -> CrearUsuario:
    """Fábrica: `await usuario_real("admin")` crea el usuario (commit del savepoint) y su token.

    `must_change_password` llega con `0005b_auth_security` (S2-B2) y se agrega entonces.
    """
    from tests.factories.users import make_user

    async def crear(
        role: str = "coach",
        *,
        email: str | None = None,
        password: str = CLAVE_PRUEBA,
        member_id: UUID | None = None,
        activo: bool = True,
        bloqueado: bool = False,
    ) -> UsuarioPrueba:
        usuario = await make_user(
            session,
            role=role,
            email=email,
            password=password,
            member_id=member_id,
            is_active=activo,
            locked_at=reloj.now_utc() if bloqueado else None,
        )
        token = create_access_token(usuario.id, role, usuario.member_id, reloj)  # type: ignore[arg-type]
        return UsuarioPrueba(usuario, usuario.id, usuario.email, role, password, token)

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
    cadena de auditoría. Al salir borra las filas de `settings.settings_sections` y las filas de
    auditoría agregadas desde el inicio (la cola de la cadena; el prefijo sigue válido).
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
        async with engine.begin() as conexion:
            await conexion.execute(text(LIMPIAR_SETTINGS))
            await conexion.execute(text("ALTER TABLE audit.audit_log DISABLE TRIGGER USER"))
            await conexion.execute(
                text("DELETE FROM audit.audit_log WHERE seq > :seq"), {"seq": ultima_seq or 0}
            )
            await conexion.execute(text("ALTER TABLE audit.audit_log ENABLE TRIGGER USER"))
