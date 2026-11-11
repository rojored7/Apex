"""Cambio de proveedor de la llave de firma (S6-A2; S6-D69, D81, D100).

`switch_provider(session, settings, data_class, target, reason, actor)`: la firma no se rota
en sitio (D69): se crea una llave NUEVA en el proveedor destino y la anterior queda `decrypt_only`
(sigue verificando por su clave pública guardada). No recifra nada ni toca `audit.signatures`.
Dentro de la transacción de quien llama (no confirma):
1. bloquea la fila `sign` activa de la clase; sin ella, o con el mismo proveedor, rechaza;
2. pide al destino su referencia y su clave pública (la reversa a `local` exige el archivo);
3. pasa la anterior a `decrypt_only` y, ya liberado el índice único, inserta la versión siguiente;
4. `crypto_ops(wrap)` y UNA fila de auditoría `update` sin material.
Todo rechazo es `ValueError` con un texto fijo (`purpose_not_rotatable`, ...); nunca rutas, URL ni
texto del proveedor.
"""

from __future__ import annotations

import re
from typing import Final
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.clock import current_clock
from app.core.config import Settings
from app.core.crypto import oplog
from app.core.crypto import provider as provider_mod
from app.core.crypto.errors import CryptoError
from app.core.crypto.models import CryptoKey
from app.core.crypto.registry import REGISTRY
from app.core.crypto.service import lock_class_in_transaction, next_key_state

AUDIT_TABLE: Final = "crypto.crypto_keys"
_VARIABLE: Final = re.compile(r"^[A-Z][A-Z_]+ no está definida$")


class SignRotationError(ValueError):
    """Rechazo del cambio de proveedor de la firma; el texto es fijo (sin proveedor ni rutas)."""


def not_rotatable(data_class: str, *, with_provider: bool) -> str | None:
    """Rechazo por argumentos (puro): `--provider` solo vale para una clase de firma y una clase
    de firma solo rota cambiando de proveedor (D69)."""
    spec = REGISTRY.get(data_class)
    if spec is not None and spec.sign and not with_provider:
        return "purpose_not_rotatable: la llave de firma no se rota en sitio; use --provider"
    if with_provider and (spec is None or not spec.sign):
        return "--provider solo se admite con una clase de firma"
    return None


def _destination(settings: Settings, name: str) -> provider_mod.KeyProvider:
    try:
        return provider_mod.get_provider_named(settings, name)
    except CryptoError as error:
        detalle = error.message if _VARIABLE.fullmatch(error.message) else error.code
        raise SignRotationError(f"el proveedor {name} no está disponible: {detalle}") from None


async def _active(session: AsyncSession, data_class: str) -> CryptoKey:
    actual = await session.scalar(
        select(CryptoKey)
        .where(CryptoKey.purpose == "sign", CryptoKey.data_class == data_class)
        .where(CryptoKey.state == "active")
    )
    if actual is None:
        raise SignRotationError(
            "no hay llave de firma activa; cree la fila con init-keys --data-class"
        )
    return actual


async def switch_provider(
    session: AsyncSession,
    settings: Settings,
    data_class: str,
    target: str,
    reason: str,
    actor: UUID,
) -> CryptoKey:
    """Crea la versión siguiente en `target` y deja la activa en `decrypt_only` (1 transacción)."""
    async with session.begin():
        return await _rotate(session, settings, data_class, target, reason, actor)


async def _insert_next(
    session: AsyncSession,
    anterior: CryptoKey,
    target: str,
    referencia: str,
    publica: str,
    actor: UUID,
) -> CryptoKey:
    """Pasa la anterior a `decrypt_only` y, liberado el índice único, inserta la siguiente."""
    ultima = await session.scalar(
        select(func.max(CryptoKey.version)).where(
            CryptoKey.purpose == "sign", CryptoKey.data_class == anterior.data_class
        )
    )
    anterior.state = next_key_state(anterior.state, "rotate", "sign")  # type: ignore[arg-type]
    anterior.rotated_at, anterior.rotated_by = current_clock().now_utc(), actor
    await session.flush()  # libera `uq_crypto_keys_active` antes de insertar la nueva
    nueva = CryptoKey(
        purpose="sign",
        data_class=anterior.data_class,
        algorithm=anterior.algorithm,
        provider=target,
        version=int(ultima or anterior.version) + 1,
        state="active",
        wrapped_material=referencia.encode("ascii"),
        public_key=publica,
        created_by=actor,
    )
    session.add(nueva)
    await session.flush()
    return nueva


async def _rotate(
    session: AsyncSession,
    settings: Settings,
    data_class: str,
    target: str,
    reason: str,
    actor: UUID,
) -> CryptoKey:
    await lock_class_in_transaction(session, data_class)
    anterior = await _active(session, data_class)
    if anterior.provider == target:
        raise SignRotationError(f"purpose_not_rotatable: la firma ya usa el proveedor {target}")
    destino = _destination(settings, target)
    try:
        referencia, publica = destino.sign_key_ref(), await destino.sign_public_key()
    except CryptoError as error:
        raise SignRotationError(
            f"la llave de firma de {target} no está disponible: {error.code}"
        ) from None
    origen = anterior.provider
    nueva = await _insert_next(session, anterior, target, referencia, publica, actor)
    oplog.record("wrap", data_class=data_class, key_id=nueva.id, key_version=nueva.version)
    detalle = {
        "op": "rotate_sign_provider",
        "data_class": data_class,
        "from": origen,
        "to": target,
        "version": nueva.version,
        "reason": reason,
    }
    await audit.record(
        session,
        action="update",
        table_name=AUDIT_TABLE,
        record_id=nueva.id,
        before=None,
        after=detalle,
        user_id=actor,
    )
    return nueva
