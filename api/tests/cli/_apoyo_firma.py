"""Apoyo de las pruebas CLI de la firma de la cadena (S6-A2; S6-D8, D80, D81, D99).

`tests/cli/conftest.py` no las reexporta: cada archivo importa lo que usa.
- `firma_lista`: base vacía de llaves (`limpiar_demo`), DEK del bus y fila `sign` `local` con su
  clave pública, commit real, keyring del proceso vacío (el comando lo carga con `crypto_runtime`).
- `sin_fila_sign`: lo mismo pero sin la fila `sign` (`init-keys --data-class` la crea).
- `admin`: un admin activo para `--as`.
- `con_proveedor(monkeypatch, proveedor)`: el proveedor que el comando recibe de la fábrica.
- `llave_sign(fabrica)`: filas `sign` de `crypto.crypto_keys` por versión.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.crypto import provider as provider_mod
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoKey
from tests.conftest import CLAVE_PRUEBA
from tests.factories.firma_real import llaves_de_firma
from tests.factories.users import make_user

Fabrica = async_sessionmaker[AsyncSession]


@pytest.fixture
async def firma_lista(
    limpiar_demo: Fabrica, engine: AsyncEngine, proveedor_local: LocalFileProvider
) -> AsyncIterator[Fabrica]:
    async with llaves_de_firma(engine, proveedor_local) as fabrica:
        yield fabrica


@pytest.fixture
async def sin_fila_sign(
    limpiar_demo: Fabrica, engine: AsyncEngine, proveedor_local: LocalFileProvider
) -> AsyncIterator[Fabrica]:
    async with llaves_de_firma(engine, proveedor_local, con_fila_sign=False) as fabrica:
        yield fabrica


@pytest.fixture
async def admin(limpiar_demo: Fabrica, argon2_rapido: None) -> Any:
    async with limpiar_demo() as sesion:
        return await make_user(sesion, role="admin", password=CLAVE_PRUEBA)


def con_proveedor(monkeypatch: pytest.MonkeyPatch, proveedor: Any) -> None:
    """`get_provider_named` (de `crypto_runtime`) devuelve `proveedor` con cualquier nombre."""
    monkeypatch.setattr(provider_mod, "get_provider_named", lambda settings, nombre: proveedor)


async def llaves_sign(fabrica: Fabrica) -> list[CryptoKey]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(
            select(CryptoKey).where(CryptoKey.purpose == "sign").order_by(CryptoKey.version)
        )
        return list(filas)
