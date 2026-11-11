"""Apoyo de S6-A2 (D81): cambio de proveedor de la llave de firma. Sobre `migracion_lista`.

- `sembrar_firmas(e)`: fila `sign` v1 `local` `active`, cadena de 3 + 2 filas y DOS firmas hechas
  con `sign_latest` (commit real); devuelve `Sembrado(v1, firmas)`; el keyring del proceso queda
  vacío.
- `rotar_a_mano(e, v1)`: el estado POSTERIOR a `rotate-key audit.signature --provider openbao`
  construido a mano (sin pasar por el código bajo prueba): v1 `decrypt_only`, v2 `active` `openbao`
  con la referencia y la pública de `key_info`.
- `cargar_keyring(e)`: keyring del proceso con todas las llaves (resolver del entorno).
- `agregar_y_firmar(e, n)`: agrega `n` filas a la cadena y firma con `sign_latest`.
- `instantanea_firmas(fabrica)`: filas de `audit.signatures` como tuplas comparables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core import audit_sign
from app.core.audit_sign import AuditSignature
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.crypto.models import CryptoKey
from tests.crypto._migracion import Entorno
from tests.crypto.conftest import fila_sign
from tests.factories import audit_chain


@dataclass(frozen=True)
class Sembrado:
    v1: UUID
    firmas: list[tuple[Any, ...]]


async def cargar_keyring(e: Entorno) -> Keyring:
    keyring = Keyring()
    async with e.fabrica() as sesion:
        await keyring.load_all(sesion, e.resolver())
    configure_keyring(keyring)
    return keyring


async def agregar_y_firmar(e: Entorno, n: int) -> audit_sign.SignOutcome:
    async with e.fabrica() as sesion:
        with actor_scope(SYSTEM_USER_ID):
            await audit_chain.make_audit_chain(sesion, n)
            salida = await audit_sign.sign_latest(sesion)
            await sesion.commit()
    return salida


async def instantanea_firmas(fabrica: Any) -> list[tuple[Any, ...]]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(select(AuditSignature).order_by(AuditSignature.through_seq))
        return [
            (f.id, f.through_seq, f.chain_hash, f.signature, f.key_id, f.algorithm, f.signed_at)
            for f in filas
        ]


async def sembrar_firmas(e: Entorno) -> Sembrado:
    async with e.fabrica() as sesion:
        with actor_scope(SYSTEM_USER_ID):
            v1 = await fila_sign(sesion, e.local)
            await sesion.commit()
    await cargar_keyring(e)
    await agregar_y_firmar(e, 3)
    await agregar_y_firmar(e, 2)
    configure_keyring(None)
    return Sembrado(v1.id, await instantanea_firmas(e.fabrica))


async def rotar_a_mano(e: Entorno, v1: UUID) -> UUID:
    async with e.fabrica() as sesion:
        antigua = await sesion.get(CryptoKey, v1)
        assert antigua is not None
        with actor_scope(SYSTEM_USER_ID):
            antigua.state = "decrypt_only"
            await sesion.flush()
            nueva = await fila_sign(sesion, e.openbao, version=2)
            await sesion.commit()
        return nueva.id
