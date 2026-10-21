"""Keyring en memoria (US-025 T4): las DEK y llaves de índice abiertas del proceso.

- `load_all` desenvuelve con el `KeyProvider` las llaves `active` y `decrypt_only`.
- `refresh_if_stale` compara una marca de `crypto_keys` (conteo, último `updated_at` y la
  firma `id:state` de todas las filas; la tabla tiene decenas de filas como mucho) con lo
  cargado y recarga solo si cambió (rotación de US-030 desde otro proceso). US-029 lo
  cablea al inicio de cada unidad de trabajo.
- El material vive en `bytearray` sin `__repr__`; el keyring no tiene getters que devuelvan
  una DEK y su `repr` solo muestra conteos.
- `current_keyring()` es el keyring del proceso, fijado por `bootstrap.ensure_keys`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import String, cast, func, literal_column, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import oplog
from app.core.crypto.errors import CryptoError
from app.core.crypto.models import CryptoKey
from app.core.crypto.provider import KeyProvider

LOADABLE_STATES: frozenset[str] = frozenset({"active", "decrypt_only"})


@dataclass(eq=False)
class LoadedKey:
    key_id: UUID
    purpose: str
    data_class: str
    version: int
    state: str
    material: bytearray = field(repr=False)

    def __repr__(self) -> str:
        return f"LoadedKey({self.purpose}:{self.data_class} v{self.version} {self.state})"


class Keyring:
    def __init__(self) -> None:
        self._keys: dict[UUID, LoadedKey] = {}
        self._active: dict[tuple[str, str], LoadedKey] = {}
        self._marca_cargada: tuple[int, datetime | None, str | None] = (0, None, None)
        self.provider: KeyProvider | None = None

    def __repr__(self) -> str:
        return f"Keyring(llaves={len(self._keys)}, activas={len(self._active)})"

    def keys(self) -> list[LoadedKey]:
        return list(self._keys.values())

    def get(self, key_id: UUID) -> LoadedKey | None:
        return self._keys.get(key_id)

    def active_for(self, purpose: str, data_class: str) -> LoadedKey:
        try:
            return self._active[(purpose, data_class)]
        except KeyError:
            raise CryptoError(
                "key_missing", f"no hay llave {purpose} activa para {data_class}"
            ) from None

    async def _load_rows(
        self, session: AsyncSession, provider: KeyProvider, rows: list[CryptoKey]
    ) -> None:
        for fila in rows:
            existente = self._keys.get(fila.id)
            if existente is not None:
                existente.state = fila.state
            else:
                if fila.purpose == "sign":
                    # La privada vive en el proveedor: la fila guarda su referencia y se
                    # conserva en todos los estados porque la pública sigue verificando (Q27).
                    material = bytearray(fila.wrapped_material)
                elif fila.state in LOADABLE_STATES:
                    material = bytearray(await provider.unwrap(fila.wrapped_material))
                    oplog.record(
                        "unwrap",
                        data_class=fila.data_class,
                        key_id=fila.id,
                        key_version=fila.version,
                    )
                else:
                    continue
                existente = LoadedKey(
                    key_id=fila.id,
                    purpose=fila.purpose,
                    data_class=fila.data_class,
                    version=fila.version,
                    state=fila.state,
                    material=material,
                )
                self._keys[fila.id] = existente
            par = (fila.purpose, fila.data_class)
            if fila.state == "active":
                self._active[par] = existente
            elif self._active.get(par) is existente:
                del self._active[par]

    async def _marca(self, session: AsyncSession) -> tuple[int, datetime | None, str | None]:
        firma = func.string_agg(
            func.concat(cast(CryptoKey.id, String), ":", CryptoKey.state),
            aggregate_order_by(literal_column("','"), CryptoKey.id),
        )
        fila = (
            await session.execute(
                select(func.count(), func.max(CryptoKey.updated_at), firma).select_from(CryptoKey)
            )
        ).one()
        return int(fila[0]), fila[1], fila[2]

    async def load_all(self, session: AsyncSession, provider: KeyProvider) -> None:
        self.provider = provider
        filas = list((await session.scalars(select(CryptoKey).order_by(CryptoKey.version))).all())
        await self._load_rows(session, provider, filas)
        self._marca_cargada = await self._marca(session)

    async def refresh_if_stale(self, session: AsyncSession, provider: KeyProvider) -> bool:
        """Recarga si cambió el conteo o el último `updated_at`. Devuelve si recargó."""
        if await self._marca(session) == self._marca_cargada:
            return False
        await self.load_all(session, provider)
        return True

    async def ensure_loaded(
        self, session: AsyncSession, provider: KeyProvider, key_id: UUID
    ) -> LoadedKey | None:
        """Carga bajo demanda una llave creada por otro proceso (un blob con `key_id` nuevo)."""
        if key_id in self._keys:
            return self._keys[key_id]
        fila = await session.get(CryptoKey, key_id)
        if fila is None:
            return None
        await self._load_rows(session, provider, [fila])
        return self._keys.get(key_id)


_current: Keyring | None = None


def configure_keyring(keyring: Keyring | None) -> None:
    global _current
    _current = keyring


def current_keyring() -> Keyring:
    if _current is None:
        raise CryptoError("crypto_unavailable", "el keyring no está cargado (ensure_keys)")
    return _current
