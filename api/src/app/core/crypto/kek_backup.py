"""Prueba de una KEK exportada contra las DEK envueltas de la base (S4B-B3a; S4B-D58, S4B-D62).

`verify_wrapped` abre cada DEK `active` y `decrypt_only` con `AESGCM` y `parse_wrapped` (nunca las
`retired`: su KEK pudo ser otra) y pone en ceros el `bytearray` de la KEK al terminar, haya o no
fallos. `load_wrapped` es una consulta de solo lectura propia de `core/crypto`: una sola sentencia
`SELECT` sobre `crypto.crypto_keys`. Ninguna función imprime, registra ni conserva la KEK, y el
módulo no expone un lector de ella.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto.archive import VerifyKekResult
from app.core.crypto.errors import CryptoError
from app.core.crypto.local_provider import WRAP_AAD, parse_wrapped
from app.core.crypto.models import CryptoKey

VERIFIED_STATES: Final = frozenset({"active", "decrypt_only"})
"""Estados cuyas DEK deben abrirse con la KEK exportada; las `retired` no cuentan."""


@dataclass(frozen=True)
class WrappedDek:
    """Una fila de `crypto.crypto_keys` con su material envuelto (nunca la DEK en claro)."""

    key_id: str
    version: int
    state: str
    wrapped_material: bytes

    def __repr__(self) -> str:  # sin el material envuelto
        return f"WrappedDek(key_id={self.key_id!r}, version={self.version}, state={self.state!r})"


def _opens(aead: AESGCM, wrapped: bytes) -> bool:
    try:
        nonce, cifrado = parse_wrapped(wrapped)
        aead.decrypt(nonce, cifrado, WRAP_AAD)
    except (CryptoError, InvalidTag):
        return False
    return True


def verify_wrapped(kek: bytearray, wrapped: Sequence[WrappedDek]) -> VerifyKekResult:
    """Prueba `unwrap` de cada DEK `active`/`decrypt_only` con `kek`; deja `kek` en ceros."""
    try:
        aead = AESGCM(bytes(kek))
        contadas = [d for d in wrapped if d.state in VERIFIED_STATES]
        fallidas = tuple(d.key_id for d in contadas if not _opens(aead, d.wrapped_material))
        return VerifyKekResult(total=len(contadas), failed_key_ids=fallidas)
    finally:
        kek[:] = bytes(len(kek))


async def load_wrapped(session: AsyncSession) -> list[WrappedDek]:
    """Lee `crypto_keys` (solo lectura, una consulta `SELECT`)."""
    filas = await session.execute(
        select(
            CryptoKey.id, CryptoKey.version, CryptoKey.state, CryptoKey.wrapped_material
        ).order_by(CryptoKey.purpose, CryptoKey.data_class, CryptoKey.version)
    )
    return [WrappedDek(str(i), int(v), str(s), bytes(m)) for i, v, s, m in filas.all()]
