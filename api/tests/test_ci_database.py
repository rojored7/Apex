"""Las pruebas corren contra un PostgreSQL 16 real (US-003, T1; CRITICA-2 N-1).

Falla, no se salta, si `TEST_DATABASE_URL` no está definida: una suite que se
salta la base de datos en silencio no prueba nada. US-012 agrega la fixture de
sesión de `conftest.py`; esta prueba se queda como centinela de la versión.
"""

from __future__ import annotations

import os

import asyncpg
import pytest

pytestmark = pytest.mark.db


def _url_asyncpg() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    assert url, "TEST_DATABASE_URL no está definida: las pruebas exigen PostgreSQL 16 de prueba"
    assert url.startswith("postgresql+asyncpg://"), url
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def test_database_url_apunta_a_postgres16() -> None:
    conexion = await asyncpg.connect(_url_asyncpg())
    try:
        version = await conexion.fetchval("SHOW server_version")
    finally:
        await conexion.close()
    assert str(version).startswith("16."), version
