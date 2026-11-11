"""`init-keys --data-class <clase> [--as]` (S6-A2; S6-D72, D80, D81, D99).

Crea o completa la fila `sign` de una clase de firma (`audit.signature`) con la referencia
(`local:sign-ed25519` o `apex-sign-audit`) y la `public_key` del proveedor vigente; no toca
archivos. Idempotente: una fila con `public_key` ya puesta no se cambia («ya existe», 0); una fila
sin ella (base de desarrollo anterior al CHECK, S6-D99) se completa una vez. Se audita con
`audit_log` (`insert` o `update` sobre `crypto.crypto_keys`, sin material); no escribe
`crypto_ops` (crear la fila no firma ni cifra). Clase desconocida o que no se firma: 2
`unknown_data_class` (`attachment.sensitive` hasta C1). Con `ENV=production` exige `--as`.
"""

from __future__ import annotations

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
from app.core.crypto.models import CryptoKey
from app.core.crypto.provider import current_provider
from app.core.crypto.registry import REGISTRY
from app.core.crypto.service import lock_class_in_transaction

COMMAND: Final = "init-keys"
AUDIT_TABLE: Final = "crypto.crypto_keys"


@dataclass(frozen=True)
class DataClassReport:
    outcome: str  # "created" | "completed" | "exists"
    provider: str
    algorithm: str


async def _audit(
    session: AsyncSession,
    accion: Literal["insert", "update"],
    fila: CryptoKey,
    data_class: str,
    actor: UUID,
) -> None:
    detalle = {"op": "init_data_class", "data_class": data_class, "version": fila.version}
    await audit.record(
        session,
        action=accion,
        table_name=AUDIT_TABLE,
        record_id=fila.id,
        before=None,
        after=detalle,
        user_id=actor,
    )


async def ensure_data_class(
    session: AsyncSession, settings: Settings, data_class: str, actor: UUID
) -> DataClassReport:
    """Dentro de la transacción de quien llama (no confirma). Toma el candado de la clase (la clave
    de la rotación) para serializar con `rotate-key --provider`."""
    if (rechazo := data_class_error(data_class)) is not None:
        reject(rechazo, COMMAND)
    await lock_class_in_transaction(session, data_class)
    proveedor = current_provider()
    filas = list(
        await session.scalars(
            select(CryptoKey)
            .where(CryptoKey.purpose == "sign", CryptoKey.data_class == data_class)
            .order_by(CryptoKey.version)
        )
    )
    activa = next((f for f in filas if f.state == "active"), None)
    if activa is not None and activa.public_key is not None:
        return DataClassReport("exists", activa.provider, activa.algorithm)
    publica = await proveedor.sign_public_key()
    if activa is not None:
        if activa.provider != proveedor.name:
            reject("la fila de firma es de otro proveedor; use rotate-key --provider", COMMAND)
        activa.public_key = publica
        await session.flush()
        await _audit(session, "update", activa, data_class, actor)
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
    session.add(nueva)
    await session.flush()
    await _audit(session, "insert", nueva, data_class, actor)
    return DataClassReport("created", nueva.provider, nueva.algorithm)


async def run(
    settings: Settings, options: RuntimeOptions, data_class: str, actor_email: str | None
) -> DataClassReport:
    """Arranque con `crypto_runtime` y atribución a un admin activo (o al usuario técnico)."""
    async with crypto_runtime(settings, options) as session:
        async with session.begin():
            actor = await resolve_admin_actor(session, actor_email, required=False)
        with unit_of_work(actor):
            async with session.begin():
                return await ensure_data_class(session, settings, data_class, actor)


def data_class_error(data_class: str) -> str | None:
    """Rechazo previo y puro (sin `.env` ni base): la clase no existe o no se firma."""
    spec = REGISTRY.get(data_class)
    if spec is None or not spec.sign:
        return f"unknown_data_class: {data_class} no es una clase de firma"
    return None
