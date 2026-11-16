"""`is_connection_error` con errores REALES de conexión (S9-W0-4c, S9-D46, hallazgo MEDIUM 1).

Antes la toma del candado de aviso solo atrapaba `SQLAlchemyError`: un puerto cerrado sale como
`ConnectionRefusedError` pelado (un `OSError`), sin envolver. El predicado único reconoce lo que
asyncpg deja salir de verdad y NO confunde un error de la sentencia con uno de conexión.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.db import is_connection_error
from tests.core._apoyo_conexion import error_de_puerto_cerrado, rol_con_un_solo_cupo


async def test_un_puerto_cerrado_es_un_error_de_conexion() -> None:
    error = await error_de_puerto_cerrado()
    assert isinstance(error, OSError)  # no está envuelto: por eso `except SQLAlchemyError` no basta
    assert is_connection_error(error)


async def test_demasiadas_conexiones_es_un_error_de_conexion(engine: AsyncEngine) -> None:
    async with rol_con_un_solo_cupo(engine) as limitado, limitado.connect() as primera:
        await primera.execute(text("SELECT 1"))
        with pytest.raises(DBAPIError) as salida:
            async with limitado.connect():
                pass
    assert salida.value.orig.__cause__.__class__.__name__ == "TooManyConnectionsError"  # type: ignore[union-attr]
    assert is_connection_error(salida.value)


async def test_un_error_de_la_sentencia_no_es_un_error_de_conexion(session: AsyncSession) -> None:
    with pytest.raises(DBAPIError) as salida:
        await session.execute(text("SELECT 1 / 0"))
    assert not is_connection_error(salida.value)


@pytest.mark.parametrize("error", [ValueError("x"), RuntimeError("y"), KeyError("z")])
def test_un_error_cualquiera_no_es_un_error_de_conexion(error: BaseException) -> None:
    assert not is_connection_error(error)


def test_una_conexion_invalidada_es_un_error_de_conexion() -> None:
    error = OperationalError("SELECT 1", {}, Exception("caída"), connection_invalidated=True)
    assert is_connection_error(error)
