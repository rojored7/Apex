"""MEDIUM-2 de W0-2 del Sprint 3 (S4B-D12): `_after_soft_rollback` no enmascara el error original.

Si el `INSERT` de `crypto_ops` que rescata las filas `error`/`decrypt` falla durante el rollback
(por ejemplo una base caída), el error se registra con `logger.error` (solo el tipo y el SQLSTATE,
nunca la sentencia ni los valores) y NO se relanza: al llamador le llega el error de negocio que
causó el rollback, intacto.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import bus, oplog
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoOp
from app.core.crypto.oplog import install_oplog_listeners, pending_rows, reset_buffer
from tests.crypto.conftest import limpiar_llaves_con_commit
from tests.factories.triggers import disable_user_sql, rearm_always_sql

ACTOR = UUID(int=42)
CHECK_VIOLATION = "23514"


class ErrorDeNegocio(Exception):
    """El error que debe llegar intacto al llamador."""


async def _limpiar_ops(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(disable_user_sql("crypto.crypto_ops")))
        await conn.execute(text("DELETE FROM crypto.crypto_ops"))
        await conn.execute(text(rearm_always_sql("crypto.crypto_ops")))


@pytest.fixture
async def uow(
    engine: AsyncEngine, proveedor_local: LocalFileProvider
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    install_oplog_listeners()
    await limpiar_llaves_con_commit(engine)
    await _limpiar_ops(engine)
    reset_buffer()
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with fabrica() as session, session.begin():
        with actor_scope(SYSTEM_USER_ID):
            await ensure_keys(session, proveedor_local, lambda _n: proveedor_local)
    await _limpiar_ops(engine)
    try:
        yield fabrica
    finally:
        reset_buffer()
        configure_keyring(None)
        await _limpiar_ops(engine)
        await limpiar_llaves_con_commit(engine)


@asynccontextmanager
async def tx(fabrica: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    with actor_scope(ACTOR):
        async with fabrica() as session, session.begin():
            yield session


async def _filas(fabrica: async_sessionmaker[AsyncSession]) -> list[CryptoOp]:
    async with fabrica() as session:
        return list((await session.scalars(select(CryptoOp))).all())


def _romper_el_insert_del_rollback(parche: pytest.MonkeyPatch) -> None:
    """Las filas rescatadas llevan un `verb` fuera del CHECK: el INSERT falla con 23514."""
    real = oplog._materialize

    def rotas(rows: Any, *, strict: bool) -> list[dict[str, Any]]:
        return [{**valores, "verb": "verbo_inexistente"} for valores in real(rows, strict=strict)]

    parche.setattr(oplog, "_materialize", rotas)


async def _cifrar(fabrica: async_sessionmaker[AsyncSession], record_id: UUID) -> str:
    async with tx(fabrica):
        return bus.encrypt("member.document", b"1020304", bus.aad_for(record_id))


async def _descifrar_mal_y_fallar(
    fabrica: async_sessionmaker[AsyncSession], blob: str, record_id: UUID, error: Exception
) -> None:
    async with tx(fabrica):
        with pytest.raises(CryptoError):
            bus.decrypt(blob, bus.aad_for(uuid4()), purpose="reveal", record_id=record_id)
        raise error


async def test_control_sin_fallo_el_error_de_descifrado_se_conserva_tras_el_rollback(
    uow: async_sessionmaker[AsyncSession],
) -> None:
    record_id = uuid4()
    blob = await _cifrar(uow, record_id)
    original = ErrorDeNegocio("negocio")
    with pytest.raises(ErrorDeNegocio) as capturado:
        await _descifrar_mal_y_fallar(uow, blob, record_id, original)
    assert capturado.value is original
    errores = [f for f in await _filas(uow) if f.result == "error"]
    assert len(errores) == 1 and errores[0].verb == "decrypt"


async def test_si_el_insert_del_rollback_falla_llega_el_error_original_intacto(
    uow: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    record_id = uuid4()
    blob = await _cifrar(uow, record_id)
    original = ErrorDeNegocio("el error de negocio")
    _romper_el_insert_del_rollback(monkeypatch)
    with pytest.raises(ErrorDeNegocio) as capturado:
        await _descifrar_mal_y_fallar(uow, blob, record_id, original)
    assert capturado.value is original, "el rollback no puede enmascarar el error de negocio"


async def test_el_fallo_del_insert_se_registra_con_tipo_y_sqlstate_sin_datos(
    uow: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    record_id = uuid4()
    blob = await _cifrar(uow, record_id)
    _romper_el_insert_del_rollback(monkeypatch)
    with caplog.at_level(logging.INFO):
        with pytest.raises(ErrorDeNegocio):
            await _descifrar_mal_y_fallar(uow, blob, record_id, ErrorDeNegocio("x"))
    # El sink de alertas (app.alerts) también escribe un ERROR: aquí se mira solo el de oplog.
    errores = [
        r for r in caplog.records if r.levelno >= logging.ERROR and r.name == "app.crypto.oplog"
    ]
    assert len(errores) == 1
    registro = errores[0]
    assert registro.name == "app.crypto.oplog"
    texto = registro.getMessage()
    assert CHECK_VIOLATION in texto, "el SQLSTATE"
    assert any(tipo in texto for tipo in ("IntegrityError", "CheckViolationError")), "el tipo"
    assert registro.exc_info is None, "sin traza: lleva la sentencia y los valores"
    for secreto in ("verbo_inexistente", "Failing row", "INSERT INTO", str(record_id)):
        assert secreto not in caplog.text


async def test_tras_el_fallo_el_buffer_queda_vacio_y_la_siguiente_unidad_de_trabajo_escribe(
    uow: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    record_id = uuid4()
    blob = await _cifrar(uow, record_id)
    async with uow() as session, session.begin():
        await session.execute(text(disable_user_sql("crypto.crypto_ops")))
        await session.execute(text("DELETE FROM crypto.crypto_ops"))
        await session.execute(text(rearm_always_sql("crypto.crypto_ops")))
    with monkeypatch.context() as parche:
        _romper_el_insert_del_rollback(parche)
        with pytest.raises(ErrorDeNegocio):
            await _descifrar_mal_y_fallar(uow, blob, record_id, ErrorDeNegocio("x"))
    assert pending_rows() == []
    assert await _filas(uow) == [], "nada quedó escrito por el INSERT roto"
    async with tx(uow):
        bus.encrypt("member.phone", b"3001234567", bus.aad_for(uuid4()))
    async with uow() as session:
        assert await session.scalar(select(func.count()).select_from(CryptoOp)) == 1


async def test_el_fallo_del_insert_dispara_la_alerta_crypto_ops_lost_solo_con_tipo_y_sqlstate(
    uow: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revisión de W0-3 (DB-5, L4): además del log, una alerta; nunca sentencia ni datos."""
    llamadas: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        oplog, "alert", lambda codigo, **contexto: llamadas.append((codigo, contexto))
    )
    record_id = uuid4()
    blob = await _cifrar(uow, record_id)
    _romper_el_insert_del_rollback(monkeypatch)
    with pytest.raises(ErrorDeNegocio):
        await _descifrar_mal_y_fallar(uow, blob, record_id, ErrorDeNegocio("x"))
    assert len(llamadas) == 1
    codigo, contexto = llamadas[0]
    assert codigo == "crypto_ops_lost"
    assert set(contexto) == {"error_type", "sqlstate"}
    assert contexto["sqlstate"] == CHECK_VIOLATION
    assert str(record_id) not in str(contexto)


def test_la_alerta_acepta_las_claves_que_usa_oplog() -> None:
    from app.core.alerts import ALERT_CONTEXT_KEYS, alert

    assert {"error_type", "sqlstate"} <= ALERT_CONTEXT_KEYS
    alert("crypto_ops_lost", error_type="IntegrityError", sqlstate="23514")
