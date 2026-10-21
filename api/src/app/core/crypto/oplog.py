"""Bitácora `crypto_ops` por unidad de trabajo y por lote (US-029; N-01, N-05, N-15).

- Cada operación del bus llama a `record(...)`, que acumula una `OpRow` en el buffer de la
  unidad de trabajo (un `ContextVar`: cada petición, comando o job tiene el suyo). El actor
  se toma de `core/context.py`; si falta, se exige al escribir y el commit falla.
- Dentro de `with batch(verb, data_class):` las operaciones van al lote y, al cerrarlo,
  `aggregate_ops` las agrupa en una fila por (verbo, clase, llave, versión, propósito) con
  `batch_id` y `count`. Anidado en `batch_scope` del comando reutiliza ese `batch_id`.
- `before_commit` de `sqlalchemy.orm.Session` vacía el buffer con un `INSERT` múltiple en la
  misma conexión y transacción: si falla, el commit falla (la operación no queda sin rastro).
- `after_soft_rollback` de la transacción externa escribe en una conexión aparte las filas
  `error` y las `decrypt` (el dato estuvo en claro en memoria) y descarta `encrypt` e `index`.
- Ninguna fila lleva material, blob, valor ni mensaje de error: solo `result`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import event, insert
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import Session, SessionTransaction

from app.core.context import MissingActorError, current_actor, current_batch, get_actor
from app.core.crypto.errors import CryptoError
from app.core.crypto.models import OP_PURPOSES, OP_VERBS, CryptoOp

logger = logging.getLogger("app.crypto.oplog")


@dataclass(frozen=True)
class OpRow:
    verb: str
    data_class: str | None
    key_id: UUID | None
    key_version: int | None
    record_id: UUID | None
    purpose: str | None
    result: str
    user_id: UUID | None
    batch_id: UUID | None
    count: int = 1


@dataclass(frozen=True)
class BatchHandle:
    batch_id: UUID


@dataclass
class _Batch:
    batch_id: UUID
    rows: list[OpRow] = field(default_factory=list)


_buffer: ContextVar[list[OpRow] | None] = ContextVar("apex_oplog", default=None)
_batch: ContextVar[_Batch | None] = ContextVar("apex_oplog_batch", default=None)


def _buffer_list() -> list[OpRow]:
    filas = _buffer.get()
    if filas is None:
        filas = []
        _buffer.set(filas)
    return filas


def record(
    verb: str,
    *,
    data_class: str | None,
    key_id: UUID | None,
    key_version: int | None,
    record_id: UUID | None = None,
    purpose: str | None = None,
    result: str = "ok",
) -> None:
    if verb not in OP_VERBS:
        raise CryptoError("unsupported", f"verbo de bitácora desconocido: {verb}")
    if purpose is not None and purpose not in OP_PURPOSES:
        raise CryptoError("unsupported", f"propósito de bitácora desconocido: {purpose}")
    lote = _batch.get()
    fila = OpRow(
        verb=verb,
        data_class=data_class,
        key_id=key_id,
        key_version=key_version,
        record_id=record_id,
        purpose=purpose,
        result=result,
        user_id=current_actor.get(),
        batch_id=lote.batch_id if lote is not None else current_batch.get(),
    )
    (lote.rows if lote is not None else _buffer_list()).append(fila)


def aggregate_ops(rows: Iterable[OpRow]) -> list[OpRow]:
    """Agrupa las `ok` por (verbo, clase, llave, versión, propósito, actor, lote) con `count`;
    cada `error` queda en fila propia con su `record_id`."""
    salida: list[OpRow] = []
    grupos: dict[tuple[object, ...], int] = {}
    for fila in rows:
        if fila.result != "ok":
            salida.append(fila)
            continue
        clave = (
            fila.verb,
            fila.data_class,
            fila.key_id,
            fila.key_version,
            fila.purpose,
            fila.user_id,
            fila.batch_id,
        )
        if clave in grupos:
            indice = grupos[clave]
            salida[indice] = OpRow(
                **{**salida[indice].__dict__, "count": salida[indice].count + fila.count}
            )
        else:
            grupos[clave] = len(salida)
            salida.append(OpRow(**{**fila.__dict__, "record_id": None}))
    return salida


@contextmanager
def batch(verb: str, data_class: str | None) -> Iterator[BatchHandle]:
    """Lote de operaciones: una fila agregada por grupo al cerrar."""
    heredado = current_batch.get()
    lote = _Batch(heredado if heredado is not None else uuid4())
    token = _batch.set(lote)
    try:
        yield BatchHandle(lote.batch_id)
    finally:
        _batch.reset(token)
        _buffer_list().extend(aggregate_ops(lote.rows))


def pending_rows() -> list[OpRow]:
    return list(_buffer.get() or [])


def reset_buffer() -> None:
    _buffer.set(None)
    _batch.set(None)


def _materialize(rows: Iterable[OpRow], *, strict: bool) -> list[dict[str, Any]]:
    valores: list[dict[str, Any]] = []
    for fila in rows:
        if fila.user_id is not None:
            actor = fila.user_id
        elif strict:
            actor = get_actor()  # lanza MissingActorError: el commit falla
        else:
            try:
                actor = get_actor()
            except MissingActorError:
                logger.warning(
                    "crypto_ops: fila %s descartada tras rollback por falta de actor", fila.verb
                )
                continue
        valores.append(
            {
                "id": uuid4(),
                "user_id": actor,
                "verb": fila.verb,
                "data_class": fila.data_class,
                "key_id": fila.key_id,
                "key_version": fila.key_version,
                "record_id": fila.record_id,
                "purpose": fila.purpose,
                "result": fila.result,
                "batch_id": fila.batch_id,
                "count": fila.count,
                "created_by": actor,
            }
        )
    return valores


def _before_commit(session: Session) -> None:
    filas = _buffer.get()
    if not filas:
        return
    _buffer.set([])
    valores = _materialize(filas, strict=True)
    if valores:
        session.connection().execute(insert(CryptoOp), valores)


def _after_soft_rollback(session: Session, previous_transaction: SessionTransaction) -> None:
    if session.in_transaction():
        return  # savepoint interno: la unidad de trabajo sigue viva
    filas = _buffer.get()
    if not filas:
        return
    _buffer.set([])
    conservar = [f for f in filas if f.result == "error" or f.verb == "decrypt"]
    valores = _materialize(conservar, strict=False)
    if not valores:
        return
    bind = session.get_bind()
    engine = bind.engine if isinstance(bind, Connection) else bind
    with engine.begin() as conn:
        conn.execute(insert(CryptoOp), valores)


async def flush_standalone(engine: AsyncEngine) -> int:
    """Escribe el buffer sin sesión (arranque, CLI). Devuelve cuántas filas escribió."""
    filas = _buffer.get()
    if not filas:
        return 0
    _buffer.set([])
    valores = _materialize(filas, strict=True)
    if valores:
        async with engine.begin() as conn:
            await conn.execute(insert(CryptoOp), valores)
    return len(valores)


def install_oplog_listeners() -> None:
    """Registra los listeners sobre la clase `Session` síncrona (idempotente)."""
    if not event.contains(Session, "before_commit", _before_commit):
        event.listen(Session, "before_commit", _before_commit)
    if not event.contains(Session, "after_soft_rollback", _after_soft_rollback):
        event.listen(Session, "after_soft_rollback", _after_soft_rollback)
