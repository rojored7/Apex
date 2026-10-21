"""Restricciones y triggers de `crypto_keys`, `crypto_ops` y `crypto_jobs` (US-024 T6)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.models import CryptoJob, CryptoKey, CryptoOp

ENVUELTA = b"apxw1" + b"\x00" * 60


@pytest.fixture
async def db(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    with actor_scope(SYSTEM_USER_ID):
        yield session


def _llave(**cambios: Any) -> CryptoKey:
    valores: dict[str, Any] = {
        "purpose": "encrypt",
        "data_class": "member.document",
        "algorithm": "A256GCM",
        "provider": "local",
        "version": 1,
        "state": "active",
        "wrapped_material": ENVUELTA,
    }
    valores.update(cambios)
    return CryptoKey(**valores)


async def _falla(db: AsyncSession, *objetos: object, sql: str | None = None, **params: Any) -> str:
    with pytest.raises((IntegrityError, DBAPIError)) as excinfo:
        async with db.begin_nested():
            if objetos:
                db.add_all(objetos)
                await db.flush()
            if sql:
                await db.execute(text(sql), params)
    return str(excinfo.value)


async def test_una_sola_llave_activa_por_par(db: AsyncSession) -> None:
    db.add(_llave())
    await db.flush()
    mensaje = await _falla(db, _llave(version=2))
    assert "uq_crypto_keys_active" in mensaje
    db.add(_llave(version=2, state="decrypt_only"))
    await db.flush()


async def test_algoritmo_y_coherencia_proposito(db: AsyncSession) -> None:
    assert "algorithm" in await _falla(db, _llave(algorithm="DES"))
    assert "purpose_algorithm" in await _falla(db, _llave(algorithm="Ed25519"))
    assert "data_class" in await _falla(db, _llave(data_class="Member Document"))
    db.add(_llave(purpose="sign", data_class="audit.chain", algorithm="Ed25519"))
    await db.flush()


async def test_crypto_ops_es_append_only(db: AsyncSession) -> None:
    db.add(
        CryptoOp(user_id=SYSTEM_USER_ID, verb="encrypt", data_class="member.document", result="ok")
    )
    await db.flush()
    assert "append-only" in await _falla(db, sql="UPDATE crypto.crypto_ops SET result = 'error'")
    assert "append-only" in await _falla(db, sql="DELETE FROM crypto.crypto_ops")
    assert "append-only" in await _falla(db, sql="TRUNCATE crypto.crypto_ops")
    assert "count" in await _falla(
        db, CryptoOp(user_id=SYSTEM_USER_ID, verb="encrypt", result="ok", count=0)
    )
    assert "verb" in await _falla(db, CryptoOp(user_id=SYSTEM_USER_ID, verb="hash", result="ok"))


async def test_crypto_keys_no_se_borra_ni_cambia_material(db: AsyncSession) -> None:
    llave = _llave()
    db.add(llave)
    await db.flush()
    assert "nunca se borran" in await _falla(db, sql="DELETE FROM crypto.crypto_keys")
    assert "nunca se borran" in await _falla(db, sql="TRUNCATE crypto.crypto_keys")
    mensaje = await _falla(
        db,
        sql="UPDATE crypto.crypto_keys SET wrapped_material = '\\x00' WHERE id = :id",
        id=llave.id,
    )
    assert "solo cambia" in mensaje
    assert "solo cambia" in await _falla(
        db,
        sql="UPDATE crypto.crypto_keys SET data_class = 'member.phone' WHERE id = :id",
        id=llave.id,
    )


async def test_transiciones_de_estado(db: AsyncSession) -> None:
    llave = _llave()
    db.add(llave)
    await db.flush()
    llave.state = "decrypt_only"
    llave.rotated_at = datetime(2026, 10, 21, tzinfo=UTC)
    llave.rotated_by = uuid4()
    await db.flush()
    assert "transición" in await _falla(
        db, sql="UPDATE crypto.crypto_keys SET state = 'active' WHERE id = :id", id=llave.id
    )
    llave.state = "retired"
    await db.flush()
    assert "transición" in await _falla(
        db, sql="UPDATE crypto.crypto_keys SET state = 'decrypt_only' WHERE id = :id", id=llave.id
    )
    otra = _llave(data_class="member.phone")
    db.add(otra)
    await db.flush()
    otra.state = "retired"  # active → retired (rotación de índice, US-030)
    await db.flush()


async def test_crypto_jobs_un_job_en_curso_por_clase(db: AsyncSession) -> None:
    job = CryptoJob(kind="rotate", data_class="member.document", status="running", total=10)
    db.add(job)
    await db.flush()
    assert "uq_crypto_jobs_in_progress" in await _falla(
        db, CryptoJob(kind="reencrypt", data_class="member.document", status="pending")
    )
    db.add(CryptoJob(kind="rotate", data_class="member.phone", status="pending"))
    await db.flush()
    db.add(CryptoJob(kind="migrate_provider", data_class=None, status="pending"))
    await db.flush()
    assert "uq_crypto_jobs_in_progress" in await _falla(
        db, CryptoJob(kind="rewrap", data_class=None, status="running")
    )


async def test_crypto_jobs_no_se_borra_y_solo_avanza(db: AsyncSession) -> None:
    job = CryptoJob(kind="rotate", data_class="member.document", status="running", total=10)
    db.add(job)
    await db.flush()
    job.done = 5
    await db.flush()
    assert "done" in await _falla(
        db, sql="UPDATE crypto.crypto_jobs SET done = 11 WHERE id = :id", id=job.id
    )
    assert "nunca se borran" in await _falla(db, sql="DELETE FROM crypto.crypto_jobs")
    assert "solo cambia" in await _falla(
        db, sql="UPDATE crypto.crypto_jobs SET kind = 'rewrap' WHERE id = :id", id=job.id
    )
    job.status = "done"
    job.done = 10
    job.finished_at = datetime(2026, 10, 21, tzinfo=UTC)
    await db.flush()
