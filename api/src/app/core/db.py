"""Base de datos async, columnas comunes y sesión por petición (US-012).

- Un esquema por módulo (`APP_SCHEMAS`); las tablas nacen solo por migraciones.
- `Base` con convención de nombres y `TIMESTAMPTZ` para todo `datetime`
  (CLAUDE.md, datos 2).
- `CommonColumnsMixin`: `id` UUID asignado al construir el objeto (US-028 cifra con
  `aad = id` antes del flush), `created_at`, `updated_at`, `created_by` NOT NULL
  (siempre hay actor: una persona o `SYSTEM_USER_ID`; lo llena US-016).
- `SoftDeleteMixin`: solo socios, planes y usuarios (RN-14).
- `get_session`: una transacción por petición; se usa SIEMPRE como `SessionDep`
  (`Depends(get_session, scope="function")`, revisión de seguridad V10, N-1 y N-9). Con ese
  alcance FastAPI cierra la dependencia al terminar la función de la ruta y la serialización
  de su respuesta, ANTES de enviarla; así un error de commit (trigger, restricción, el
  `crypto_ops` de `before_commit`, una conexión caída) llega al cliente como envelope de error
  (US-017) y nunca sale un 200/201 de una escritura revertida. Con el alcance por defecto
  (`request`) FastAPI 0.157 confirma después de enviar el cuerpo. Todas las rutas y
  `current_user` usan el mismo alias: FastAPI cachea la dependencia por (función, alcance) y
  mezclar las dos formas abriría dos sesiones en una petición
  (`tests/architecture/test_session_scope.py`).

Este módulo no importa ningún módulo de negocio ni `core/audit.py`; los listeners
de auditoría los registra `core/audit.py` sobre la clase de sesión (US-016).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, ClassVar, Final
from uuid import UUID, uuid4

from fastapi import Depends
from sqlalchemy import TIMESTAMP, MetaData, event, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import Settings, get_settings
from app.core.errors import DomainError

logger = logging.getLogger("app.db")

APP_SCHEMAS: tuple[str, ...] = (
    "audit",
    "crypto",
    "auth",
    "settings",
    "members",
    "plans",
    "memberships",
    "payments",
    "worker",
)

# Lock asesor de las migraciones (bigint fijo; distinto del de la cadena de auditoría, US-015).
MIGRATION_LOCK_KEY: int = 4_270_001
# Tiempo máximo para abrir una conexión; /health usa además su propio límite de 2 s.
CONNECT_TIMEOUT_S = 5

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: TIMESTAMP(timezone=True),
        UUID: postgresql.UUID(as_uuid=True),
    }


class CommonColumnsMixin:
    """`id`, `created_at`, `updated_at`, `created_by` (CLAUDE.md, datos 3).

    `eager_defaults=True` (revisión Python M4): `created_at` y `updated_at` los fija el servidor;
    el `INSERT`/`UPDATE ... RETURNING` los trae en el mismo viaje, así leerlos tras un flush no
    lanza `MissingGreenlet` en una sesión async y los services no necesitan `session.refresh`.
    """

    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # Sin FK a auth.users: el núcleo no se acopla a auth (0004_auth llega después).
    created_by: Mapped[UUID] = mapped_column(nullable=False)


@event.listens_for(CommonColumnsMixin, "init", propagate=True)
def _asignar_id_al_construir(target: Any, args: Any, kwargs: dict[str, Any]) -> None:
    """El UUID existe antes del flush: el AAD del cifrado es el id del registro."""
    if kwargs.get("id") is None:
        kwargs["id"] = uuid4()


class SoftDeleteMixin:
    """Borrado lógico (RN-14): solo socios, planes y usuarios."""

    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)


def create_engine_from(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.DATABASE_URL.get_secret_value(),
        pool_pre_ping=True,
        hide_parameters=True,
        echo=False,
        connect_args={
            "timeout": CONNECT_TIMEOUT_S,
            "server_settings": server_settings_from(settings),
        },
    )


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def configure_engine(engine: AsyncEngine | None) -> None:
    """Fija el engine del proceso (`create_app`, pruebas). `None` vuelve a `Settings`."""
    global _engine, _sessionmaker
    _engine = engine
    _sessionmaker = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_engine_from(get_settings())
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


def configure_sessionmaker(factory: async_sessionmaker[AsyncSession] | None) -> None:
    """Inyección para pruebas y arranque: `None` vuelve al engine de `Settings`."""
    global _sessionmaker
    _sessionmaker = factory


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


def violated_constraint(error: IntegrityError) -> str | None:
    """Nombre de la restricción o índice único que violó el `INSERT`/`UPDATE` (revisión Python
    H3): asyncpg lo expone en `constraint_name` de la causa del error del adaptador. `None` si
    el error no lo trae. Reemplaza el frágil "nombre in str(error.orig)" de cada service."""
    causa = getattr(error.orig, "__cause__", None)
    nombre = getattr(causa, "constraint_name", None)
    return nombre if isinstance(nombre, str) else None


BUSY_SQLSTATES: Final[frozenset[str]] = frozenset({"55P03", "57014", "40P01"})
"""`lock_not_available`, `query_canceled` (statement_timeout) y `deadlock_detected` (S3-D67)."""
BUSY_MESSAGE: Final = "La base de datos está ocupada; intenta de nuevo en un momento."
BUSY_RETRY_AFTER_S: Final = 1


class DatabaseBusy(DomainError):
    """503 `busy` (S3-D67): la base no dio el candado o cortó la sentencia a tiempo.

    Lleva `Cache-Control: no-store` en sus propias cabeceras: la respuesta la arma
    `_handler_dominio` y las cabeceras de la dependencia `no_store` no llegan a un error.
    """

    status = 503
    code = "busy"
    default_message = BUSY_MESSAGE

    def __init__(self) -> None:
        super().__init__()
        self.headers = {"Retry-After": str(BUSY_RETRY_AFTER_S), "Cache-Control": "no-store"}


def _milisegundos(valor: int) -> str:
    return "0" if valor == 0 else f"{valor}ms"


def server_settings_from(settings: Settings) -> dict[str, str]:
    """`server_settings` de asyncpg con los tres tiempos de espera (S3-D43); `"0"` desactiva."""
    return {
        "lock_timeout": _milisegundos(settings.DB_LOCK_TIMEOUT_MS),
        "statement_timeout": _milisegundos(settings.DB_STATEMENT_TIMEOUT_MS),
        "idle_in_transaction_session_timeout": _milisegundos(settings.DB_IDLE_IN_TX_TIMEOUT_MS),
    }


def sqlstate_of(error: BaseException) -> str | None:
    """SQLSTATE del error de asyncpg que envuelve un `DBAPIError` (`error.orig.sqlstate`)."""
    sqlstate = getattr(getattr(error, "orig", None), "sqlstate", None)
    return sqlstate if isinstance(sqlstate, str) else None


def translate_busy(error: BaseException) -> DatabaseBusy | None:
    """`DatabaseBusy` si el SQLSTATE está en `BUSY_SQLSTATES`; `None` en otro caso."""
    return DatabaseBusy() if sqlstate_of(error) in BUSY_SQLSTATES else None


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependencia de sesión; las rutas la piden con `SessionDep`, nunca con `Depends` suelto.

    Abre una transacción, cede la sesión y hace commit al salir; cualquier excepción revierte.
    Con `scope="function"` (el de `SessionDep`) el commit corre antes de enviar la respuesta.

    El `try` abarca todo el `async with`, también el commit del `__aexit__` de `session.begin()`
    (E7): un candado no obtenido (55P03), una sentencia cortada (57014) o un deadlock (40P01),
    en el cuerpo o al confirmar, salen como `DatabaseBusy` (503 `busy`, S3-D67) encadenado con
    `from`; cualquier otro error sale intacto (la misma instancia). El 503 deja un `WARNING`
    `db busy` con solo el SQLSTATE (nunca la sentencia ni sus parámetros) y ninguna traza.
    """
    try:
        async with get_sessionmaker()() as session, session.begin():
            yield session
    except DBAPIError as error:
        busy = translate_busy(error)
        if busy is None:
            raise
        logger.warning("db busy", extra={"sqlstate": sqlstate_of(error)})
        raise busy from error


SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]
"""La sesión de una ruta: commit antes de enviar la respuesta (N-1). Alias único del api."""
