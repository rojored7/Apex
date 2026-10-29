"""Fixtures de la auditoría (plan del Sprint 4A, sección 2, bloque B3; S4A-D44, S4A-D69).

- `audit_service` se importa al nivel del módulo: sus suscriptores quedan en el bus antes de la
  foto de `restaurar_bus` (como `dashboard_service` en B8).
- `audit_chain_factory`: `CadenaDePrueba` sobre la `session` de la prueba, con `audit.audit_log` y
  `audit.verifications` vaciadas DENTRO de la transacción de la prueba (se revierte al terminar):
  `make`, `tamper`, `drop_rows`, `drop_tail`, `digest`, `hash_of`, `last_seq`. Apagar triggers
  toma un candado exclusivo sobre `audit.audit_log` hasta el final de la prueba: otra conexión que
  lea la tabla espera (las pruebas con conexiones aparte usan `fabrica_confirmada`).
- `fabrica_confirmada`: `async_sessionmaker` del `engine` de la prueba con commit real; vacía
  `audit.verifications` al entrar y al salir borra la cola de `audit.audit_log` y lo demás
  (`limpiar_tras_dos_sesiones`).
- `motor_del_api`: el engine global del api (`db.configure_engine`) sobre `db_test` con
  `DB_IDLE_IN_TX_TIMEOUT_MS = 2000` en `server_settings` (E10: el `engine` de la prueba se crea
  sin `server_settings`; este sale de `create_engine_from`, con su pool de colas, como el api). Al
  salir cancela las verificaciones 202 en curso y libera el engine.
- `candado_tomado`: otra conexión (del `engine` de la prueba) con `pg_try_advisory_lock(4_270_003)`
  durante la prueba; lo suelta al salir.
- `umbral_bajo` (`SYNC_VERIFY_MAX_ROWS = 10`) y `plazo_corto` (`VERIFY_MAX_SECONDS = 2`), por
  `monkeypatch` en el módulo que los define y, si lo importa, en `audit/verify.py`.
- `espia_de_conexiones`: `EspiaDeConexiones` instalado (H-2).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

import app.modules.audit.service as audit_service
from app.core import audit_verify, db
from app.core.audit import AuditEntry
from app.core.config import Settings
from app.modules.audit import verify as verify_mod
from tests.audit._apoyo import EspiaDeConexiones
from tests.conftest import LIMPIAR_VERIFICATIONS, limpiar_tras_dos_sesiones
from tests.factories import audit_chain

__all__ = ["audit_service"]

IDLE_IN_TX_DE_PRUEBA_MS = 2000
TRY_LOCK = text("SELECT pg_try_advisory_lock(:key)")
UNLOCK = text("SELECT pg_advisory_unlock(:key)")


@dataclass(frozen=True)
class CadenaDePrueba:
    """Las funciones de `tests/factories/audit_chain.py` atadas a una sesión."""

    session: AsyncSession

    async def make(self, n: int, **opciones: Any) -> int:
        return await audit_chain.make_audit_chain(self.session, n, **opciones)

    async def tamper(self, seq: int, column: str, value: Any, *, rehash: bool = False) -> None:
        await audit_chain.tamper_row(self.session, seq, column, value, rehash=rehash)

    async def drop_rows(self, seqs: Iterable[int]) -> None:
        await audit_chain.drop_rows(self.session, seqs)

    async def drop_tail(self, n: int) -> list[int]:
        return await audit_chain.drop_tail(self.session, n)

    async def digest(self, *, hasta: int | None = None) -> str:
        return await audit_chain.table_digest(self.session, hasta=hasta)

    async def hash_of(self, seq: int) -> str | None:
        return await audit_chain.hash_of(self.session, seq)

    async def last_seq(self) -> int:
        return await audit_chain.last_seq(self.session)


@pytest.fixture
async def audit_chain_factory(session: AsyncSession) -> CadenaDePrueba:
    await audit_chain.empty_audit(session)
    return CadenaDePrueba(session)


@pytest.fixture
async def fabrica_confirmada(
    engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with engine.begin() as conexion:
        await conexion.execute(text(LIMPIAR_VERIFICATIONS))
    async with engine.connect() as conexion:
        ultima = await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0)))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await limpiar_tras_dos_sesiones(engine, int(ultima or 0))


@pytest.fixture
async def motor_del_api(settings_prueba: Settings) -> AsyncIterator[AsyncEngine]:
    ajustes = settings_prueba.model_copy(
        update={"DB_IDLE_IN_TX_TIMEOUT_MS": IDLE_IN_TX_DE_PRUEBA_MS}
    )
    motor = db.create_engine_from(ajustes)
    db.configure_engine(motor)
    try:
        yield motor
    finally:
        await audit_service.cancel_background_verifications()
        await db.dispose_engine()


@pytest.fixture
async def candado_tomado(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as conexion:
        conexion = await conexion.execution_options(isolation_level="AUTOCOMMIT")
        tomado = await conexion.scalar(TRY_LOCK, {"key": audit_verify.AUDIT_VERIFY_LOCK_KEY})
        assert tomado is True, "otra conexión ya tenía el candado 4_270_003 antes de la prueba"
        try:
            yield conexion
        finally:
            await conexion.scalar(UNLOCK, {"key": audit_verify.AUDIT_VERIFY_LOCK_KEY})


@pytest.fixture
def umbral_bajo(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(verify_mod, "SYNC_VERIFY_MAX_ROWS", 10)
    return 10


@pytest.fixture
def plazo_corto(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(audit_verify, "VERIFY_MAX_SECONDS", 2)
    monkeypatch.setattr(verify_mod, "VERIFY_MAX_SECONDS", 2, raising=False)
    return 2


@pytest.fixture
def espia_de_conexiones(monkeypatch: pytest.MonkeyPatch) -> EspiaDeConexiones:
    return EspiaDeConexiones().instalar(monkeypatch)
