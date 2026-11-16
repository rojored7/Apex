"""Errores de conexión REALES para las pruebas (S9-W0-4c, S9-D46): nada se fabrica con
`OperationalError(...)`; cada error sale de intentar conectar de verdad.

- `error_de_puerto_cerrado()`: el `ConnectionRefusedError` (un `OSError` pelado) que asyncpg deja
  salir sin envolver cuando nadie escucha en el puerto.
- `rol_con_un_solo_cupo(engine)`: un rol con `CONNECTION LIMIT 1` que hereda los permisos del rol
  de la prueba; con una conexión abierta la segunda da `TooManyConnectionsError` (53300) envuelta
  en un `DBAPIError`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

PUERTO_CERRADO = "postgresql+asyncpg://nadie:nada@127.0.0.1:1/ninguna"
ROL_DE_UN_CUPO = "apex_prueba_un_cupo"
CLAVE_DEL_ROL = "prueba-un-cupo"
CREAR_ROL = (
    "SELECT format('CREATE ROLE " + ROL_DE_UN_CUPO + " LOGIN PASSWORD ''" + CLAVE_DEL_ROL + "'' "
    "CONNECTION LIMIT 1 IN ROLE %I', current_user)"
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


@asynccontextmanager
async def rol_con_un_solo_cupo(engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    """Motor del rol de un cupo; al salir lo suelta y borra el rol."""
    async with engine.connect() as admin:
        await admin.execution_options(isolation_level="AUTOCOMMIT")
        await admin.execute(text("DROP ROLE IF EXISTS " + ROL_DE_UN_CUPO))
        await admin.execute(text(str(await admin.scalar(text(CREAR_ROL)))))
    limitado = create_async_engine(
        engine.url.set(username=ROL_DE_UN_CUPO, password=CLAVE_DEL_ROL), hide_parameters=True
    )
    try:
        yield limitado
    finally:
        await limitado.dispose()
        async with engine.connect() as admin:
            await admin.execution_options(isolation_level="AUTOCOMMIT")
            await admin.execute(text("DROP ROLE IF EXISTS " + ROL_DE_UN_CUPO))
