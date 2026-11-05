"""Kit de las pruebas de sellado y recuperación (S5-B3; Rojo B3).

- `proveedor_ctl`: `ProveedorControlable` sobre el proveedor local de las pruebas.
- `base_con_llaves` / `base_sin_llaves`: `crypto_keys` con commit real (con las llaves del bus
  creadas por `ensure_keys`, o vacía), para los lifespans, `try_load` y el worker, que abren sus
  propias conexiones. Entregan un `async_sessionmaker` sobre el `engine` de la prueba. Al salir
  borran las llaves y las filas de `crypto_ops` escritas desde que empezó y sueltan el keyring y el
  proveedor del proceso.
- `alertas`: sustituye los sinks de `core/alerts.py` por uno que anota los códigos.
- `estado_de_recovery_limpio`: `recovery.reset()` antes y después (tolera el stub del Rojo).
- `GrabadoraDeAlertas`, `contar_llaves`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass, field

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import alerts
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import oplog, recovery
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.keyring import configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoKey
from app.core.crypto.provider import configure_provider
from tests.conftest import LIMPIAR_LLAVES
from tests.factories.fake_provider import ProveedorControlable
from tests.factories.triggers import disable_user_sql, rearm_always_sql


@dataclass
class GrabadoraDeAlertas:
    """Un `AlertSink` que solo anota (código, contexto)."""

    enviadas: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def send(self, code: str, context: Mapping[str, object]) -> None:
        self.enviadas.append((code, dict(context)))

    @property
    def codigos(self) -> list[str]:
        return [codigo for codigo, _ in self.enviadas]


@pytest.fixture
def alertas(monkeypatch: pytest.MonkeyPatch) -> GrabadoraDeAlertas:
    grabadora = GrabadoraDeAlertas()
    monkeypatch.setattr(alerts, "_sinks", [grabadora])
    return grabadora


def _olvidar_estado() -> None:
    try:
        recovery.reset()
    except NotImplementedError:  # Rojo B3: el stub aún no existe; la prueba falla por su cuenta
        pass


@pytest.fixture
def estado_de_recovery_limpio() -> Iterator[None]:
    _olvidar_estado()
    try:
        yield
    finally:
        _olvidar_estado()


@pytest.fixture
def proveedor_ctl(proveedor_local: LocalFileProvider) -> ProveedorControlable:
    return ProveedorControlable(proveedor_local)


async def _limpiar(engine: AsyncEngine, desde: object) -> None:
    async with engine.begin() as conexion:
        for sql in LIMPIAR_LLAVES:
            await conexion.execute(text(sql))
        await conexion.execute(text(disable_user_sql("crypto.crypto_ops")))
        await conexion.execute(text("DELETE FROM crypto.crypto_ops WHERE at >= :t"), {"t": desde})
        await conexion.execute(text(rearm_always_sql("crypto.crypto_ops")))


async def _base(
    engine: AsyncEngine, proveedor: LocalFileProvider, *, con_llaves: bool
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with engine.connect() as conexion:
        desde = await conexion.scalar(text("SELECT clock_timestamp()"))
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    configure_keyring(None)
    configure_provider(None)
    async with fabrica() as sesion:
        for sql in LIMPIAR_LLAVES:
            await sesion.execute(text(sql))
        if con_llaves:
            with actor_scope(SYSTEM_USER_ID):
                await ensure_keys(sesion, proveedor, lambda _n: proveedor)
        await sesion.commit()
    oplog.reset_buffer()
    configure_keyring(None)
    try:
        yield fabrica
    finally:
        configure_keyring(None)
        configure_provider(None)
        await _limpiar(engine, desde)


@pytest.fixture
async def base_con_llaves(
    engine: AsyncEngine, proveedor_local: LocalFileProvider
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async for fabrica in _base(engine, proveedor_local, con_llaves=True):
        yield fabrica


@pytest.fixture
async def base_sin_llaves(
    engine: AsyncEngine, proveedor_local: LocalFileProvider
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async for fabrica in _base(engine, proveedor_local, con_llaves=False):
        yield fabrica


async def contar_llaves(fabrica: async_sessionmaker[AsyncSession]) -> int:
    async with fabrica() as sesion:
        return int(await sesion.scalar(select(func.count()).select_from(CryptoKey)) or 0)
