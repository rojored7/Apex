"""Creación idempotente de las DEK y las llaves de índice al arrancar (US-025 T5, US-026 T4).

Por cada clase con `encrypt=True` sin llave `active` genera 32 bytes de `os.urandom`, los
envuelve con el proveedor y ejecuta `INSERT ... ON CONFLICT (purpose, data_class) WHERE
state = 'active' DO NOTHING`, con `version = 1`, `provider = <nombre del proveedor de creación>` y
`created_by = SYSTEM_USER_ID` (N-15). Lo mismo con `purpose = index` (HMAC-SHA256) para las
clases con `index_kind`. Luego vuelve a leer, así dos procesos arrancando a la vez (api y
worker) terminan con una sola llave por clase. Lo llaman el lifespan de `main.py`, el
worker y los comandos del CLI que usan el bus; deja el keyring del proceso cargado.
"""

from __future__ import annotations

import os
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID
from app.core.crypto import oplog
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.crypto.local_provider import SIGNING_KEY_REF
from app.core.crypto.models import CryptoKey
from app.core.crypto.provider import KeyProvider, ProviderResolver
from app.core.crypto.registry import encrypting_specs, indexing_specs, signing_specs

DEK_LEN = 32
_ALGORITHM = {"encrypt": "A256GCM", "index": "HMAC-SHA256", "sign": "Ed25519"}


async def _active_pairs(session: AsyncSession) -> set[tuple[str, str]]:
    filas = await session.execute(
        select(CryptoKey.purpose, CryptoKey.data_class).where(CryptoKey.state == "active")
    )
    return {(p, d) for p, d in filas.all()}


async def _create_missing(session: AsyncSession, provider: KeyProvider) -> int:
    """Intenta crear las llaves que faltan y devuelve cuántas faltaban (otro proceso puede haberse
    adelantado: el `ON CONFLICT` ya las dejó, y quien llama debe recargar de todos modos)."""
    deseadas = (
        [("encrypt", s.name) for s in encrypting_specs()]
        + [("index", s.name) for s in indexing_specs()]
        + [("sign", s.name) for s in signing_specs()]
    )
    activas = await _active_pairs(session)
    faltaban = 0
    for purpose, data_class in deseadas:
        if (purpose, data_class) in activas:
            continue
        if purpose == "sign":
            # La privada de firma vive en el proveedor: se guarda la referencia (US-027).
            envuelta = SIGNING_KEY_REF.encode("ascii")
        else:
            envuelta = await provider.wrap(os.urandom(DEK_LEN))
        key_id = uuid4()
        stmt = (
            insert(CryptoKey)
            .values(
                id=key_id,
                purpose=purpose,
                data_class=data_class,
                algorithm=_ALGORITHM[purpose],
                provider=provider.name,
                version=1,
                state="active",
                wrapped_material=envuelta,
                created_by=SYSTEM_USER_ID,
            )
            .on_conflict_do_nothing(
                # El predicado del índice parcial debe ir literal: con un parámetro ligado
                # PostgreSQL no reconoce el índice.
                index_elements=["purpose", "data_class"],
                index_where=text("state = 'active'"),
            )
        )
        resultado = await session.execute(stmt)
        faltaban += 1
        if getattr(resultado, "rowcount", 0) == 1 and purpose != "sign":
            oplog.record("wrap", data_class=data_class, key_id=key_id, key_version=1)
    return faltaban


async def ensure_keys(
    session: AsyncSession, provider: KeyProvider, resolver: ProviderResolver
) -> Keyring:
    """Abre lo que ya existe, crea lo que falta, carga el keyring del proceso y lo devuelve.

    S5-D14 (M-4): se abre primero lo existente. Si el proveedor no puede abrir las DEK que ya hay
    (`unwrap_failed`, `forbidden`, custodio caído), el error sube ANTES de envolver una DEK nueva:
    una KEK ajena nunca llega a guardar llaves que nadie más podría abrir."""
    keyring = Keyring()
    await keyring.load_all(session, resolver)
    hay_filas = await session.scalar(select(func.count()).select_from(CryptoKey))
    if hay_filas and not any(k.purpose == "encrypt" for k in keyring.keys()):
        # L5 (S5-D200): hay llaves guardadas y ninguna DEK de cifrado abrió; crear otras sería
        # envolver con una KEK que no es la de los datos.
        raise CryptoError("unwrap_failed", "ninguna DEK de cifrado existente se pudo abrir")
    if await _create_missing(session, provider):
        await keyring.load_all(session, resolver)
    configure_keyring(keyring)
    return keyring
