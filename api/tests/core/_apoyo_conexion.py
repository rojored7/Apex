"""Errores de conexión REALES para las pruebas (S9-W0-4c, S9-D46): nada se fabrica con
`OperationalError(...)`; cada error sale de intentar conectar de verdad.

- `error_de_puerto_cerrado()`: el `ConnectionRefusedError` (un `OSError` pelado) que asyncpg deja
  salir sin envolver cuando nadie escucha en el puerto.
- `rol_con_un_solo_cupo(engine)`: un rol con `CONNECTION LIMIT 1` que hereda los permisos del rol
  de la prueba; con una conexión abierta la segunda da `TooManyConnectionsError` (53300) envuelta
  en un `DBAPIError`. Nombre con sufijo aleatorio por corrida, contraseña aleatoria que nunca se
  imprime y `VALID UNTIL` de pocos minutos (S9-D47, LOW 7).
- `barrer_roles_huerfanos(engine)`: borra los roles de un cupo que una corrida muerta dejó (sin
  caducidad o ya caducados); `tests/conftest.py` lo llama al arrancar la sesión de pruebas.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

PUERTO_CERRADO = "postgresql+asyncpg://nadie:nada@127.0.0.1:1/ninguna"
PREFIJO_ROL_DE_UN_CUPO = "apex_prueba_un_cupo"
CREAR_ROL = text(
    "SELECT format('CREATE ROLE %I LOGIN PASSWORD %L CONNECTION LIMIT 1 VALID UNTIL %L IN ROLE %I',"
    " CAST(:rol AS text), CAST(:clave AS text),"
    " CAST(now() + interval '5 minutes' AS text), current_user)"
)
BORRAR_ROL = text("SELECT format('DROP ROLE IF EXISTS %I', CAST(:rol AS text))")
ROLES_HUERFANOS = text(
    "SELECT rolname FROM pg_roles WHERE rolname LIKE :patron"
    " AND (rolvaliduntil IS NULL OR rolvaliduntil < now())"
)


async def error_de_puerto_cerrado() -> BaseException:
    """Intenta conectar a un puerto cerrado y devuelve lo que SALE (no lo que se espera)."""
    motor = create_async_engine(PUERTO_CERRADO)
    try:
        async with motor.connect():
            pass
    except Exception as error:
        return error
    finally:
        await motor.dispose()
    raise AssertionError("el puerto 1 aceptó una conexión")


async def conectar_a_puerto_cerrado() -> None:
    """Lanza el error real de un puerto cerrado (para parchear una función que abre conexión)."""
    raise await error_de_puerto_cerrado()


async def _ejecutar_generada(admin: AsyncConnection, consulta: TextClause, **params: str) -> None:
    """Corre el DDL que arma `format(...)` en el servidor (nombre y clave escapados)."""
    await admin.execute(text(str(await admin.scalar(consulta, params))))


async def barrer_roles_huerfanos(engine: AsyncEngine) -> int:
    """Borra los roles de un cupo sin caducidad o ya caducados (restos de una corrida muerta);
    nunca toca los vigentes de otra corrida. Devuelve cuántos borró."""
    patron = PREFIJO_ROL_DE_UN_CUPO.replace("_", "\\_") + "%"
    async with engine.connect() as admin:
        await admin.execution_options(isolation_level="AUTOCOMMIT")
        nombres = [fila[0] for fila in await admin.execute(ROLES_HUERFANOS, {"patron": patron})]
        for nombre in nombres:
            await _ejecutar_generada(admin, BORRAR_ROL, rol=nombre)
    return len(nombres)


@asynccontextmanager
async def rol_con_un_solo_cupo(engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    """Motor del rol de un cupo; al salir lo suelta y borra el rol."""
    rol = f"{PREFIJO_ROL_DE_UN_CUPO}_{secrets.token_hex(6)}"
    clave = secrets.token_urlsafe(24)  # jamás se imprime ni se registra
    async with engine.connect() as admin:
        await admin.execution_options(isolation_level="AUTOCOMMIT")
        await _ejecutar_generada(admin, CREAR_ROL, rol=rol, clave=clave)
    limitado = create_async_engine(
        engine.url.set(username=rol, password=clave), hide_parameters=True
    )
    try:
        yield limitado
    finally:
        await limitado.dispose()
        async with engine.connect() as admin:
            await admin.execution_options(isolation_level="AUTOCOMMIT")
            await _ejecutar_generada(admin, BORRAR_ROL, rol=rol)
