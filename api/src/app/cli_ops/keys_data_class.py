"""`init-keys --data-class <clase> [--as]` (S6-A2, S6-C1; S6-D72, D80, D81, D99).

Crea o completa la fila `sign` de una clase de firma (`audit.signature`) con su referencia y la
`public_key` del proveedor (con `public_key` ya puesta: «ya existe», 0; sin ella, S6-D99, se
completa una vez). Con una clase cifrada sin columnas (`attachment.sensitive`) crea la fila
`encrypt` con una DEK nueva, sin persistir antes lo que `ensure_keys` crearía, para que la cree y
la audite este comando (`crypto.crypto_keys`, sin material). Otra clase: 2 `unknown_data_class`.
Con `ENV=production` exige `--as`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli_base import (
    RuntimeOptions,
    crypto_runtime,
    reject,
    resolve_admin_actor,
    unit_of_work,
)
from app.core import audit
from app.core.config import Settings
from app.core.crypto import oplog
from app.core.crypto.bootstrap import DEK_LEN
from app.core.crypto.models import CryptoKey
from app.core.crypto.provider import current_provider
from app.core.crypto.registry import REGISTRY
from app.core.crypto.service import lock_class_in_transaction

COMMAND: Final = "init-keys"
AUDIT_TABLE: Final = "crypto.crypto_keys"


@dataclass(frozen=True)
class DataClassReport:
    outcome: str
    provider: str
    algorithm: str
    purpose: str = "sign"


async def _audit(
    session: AsyncSession, action: Literal["insert", "update"], fila: CryptoKey, actor: UUID
) -> None:
    detalle = {"op": "init_data_class", "data_class": fila.data_class, "version": fila.version}
    await audit.record(
        session, action=action, table_name=AUDIT_TABLE, record_id=fila.id, before=None,
        after=detalle, user_id=actor
    )  # fmt: skip


async def _persist(session: AsyncSession, nueva: CryptoKey, actor: UUID) -> DataClassReport:
    session.add(nueva)
    await session.flush()
    await _audit(session, "insert", nueva, actor)
    return DataClassReport("created", nueva.provider, nueva.algorithm, nueva.purpose)


async def _rows(session: AsyncSession, purpose: str, data_class: str) -> list[CryptoKey]:
    where = (CryptoKey.purpose == purpose, CryptoKey.data_class == data_class)
    return list(await session.scalars(select(CryptoKey).where(*where).order_by(CryptoKey.version)))


async def ensure_data_class(
    session: AsyncSession, settings: Settings, data_class: str, actor: UUID
) -> DataClassReport:
    """Dentro de la transacción de quien llama (no confirma). Toma el candado de la clase (la clave
    de la rotación) para serializar con `rotate-key --provider`."""
    if (rechazo := data_class_error(data_class)) is not None:
        reject(rechazo, COMMAND)
    await lock_class_in_transaction(session, data_class)
    proveedor = current_provider()
    if not REGISTRY[data_class].sign:
        return await _ensure_encrypt(session, data_class, actor)
    filas = await _rows(session, "sign", data_class)
    activa = next((f for f in filas if f.state == "active"), None)
    if activa is not None and activa.public_key is not None:
        return DataClassReport("exists", activa.provider, activa.algorithm)
    publica = await proveedor.sign_public_key()
    if activa is not None:
        if activa.provider != proveedor.name:
            reject("la fila de firma es de otro proveedor; use rotate-key --provider", COMMAND)
        activa.public_key = publica
        await session.flush()
        await _audit(session, "update", activa, actor)
        return DataClassReport("completed", activa.provider, activa.algorithm)
    nueva = CryptoKey(
        purpose="sign",
        data_class=data_class,
        algorithm="Ed25519",
        provider=proveedor.name,
        version=max((f.version for f in filas), default=0) + 1,
        state="active",
        wrapped_material=proveedor.sign_key_ref().encode("ascii"),
        public_key=publica,
        created_by=actor,
    )
    return await _persist(session, nueva, actor)


async def _ensure_encrypt(session: AsyncSession, data_class: str, actor: UUID) -> DataClassReport:
    """La DEK `encrypt` de una clase sin columnas (S6-D72); el candado ya está tomado."""
    filas = await _rows(session, "encrypt", data_class)
    activa = next((f for f in filas if f.state == "active"), None)
    if activa is not None:
        return DataClassReport("exists", activa.provider, activa.algorithm, "encrypt")
    proveedor, version = current_provider(), max((f.version for f in filas), default=0) + 1
    nueva = CryptoKey(
        purpose="encrypt",
        data_class=data_class,
        algorithm="A256GCM",
        provider=proveedor.name,
        version=version,
        state="active",
        wrapped_material=await proveedor.wrap(os.urandom(DEK_LEN)),
        created_by=actor,
    )
    oplog.record("wrap", data_class=data_class, key_id=nueva.id, key_version=version)
    return await _persist(session, nueva, actor)


async def run(
    settings: Settings, options: RuntimeOptions, data_class: str, actor_email: str | None
) -> DataClassReport:
    """Arranque con `crypto_runtime` y atribución a un admin activo (o al usuario técnico)."""
    sign = REGISTRY[data_class].sign
    async with crypto_runtime(settings, options, persist_keys=sign) as session:
        async with session.begin():
            actor = await resolve_admin_actor(session, actor_email, required=False)
        with unit_of_work(actor):
            async with session.begin():
                return await ensure_data_class(session, settings, data_class, actor)


def data_class_error(data_class: str) -> str | None:
    """Rechazo previo y puro (sin `.env` ni base): la clase no existe, o ni se firma ni es una
    clase cifrada sin columnas (esas las crea el arranque)."""
    spec = REGISTRY.get(data_class)
    if spec is None or not (spec.sign or (spec.encrypt and not spec.columns)):
        return f"unknown_data_class: {data_class} no es una clase de firma ni de adjuntos"
    return None
