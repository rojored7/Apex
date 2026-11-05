"""Puerto `KeyProvider` y fábrica por `CRYPTO_PROVIDER` (US-023 T2, T6, T9).

`KeyProvider` es la única interfaz del bus con algo que intercambiar (regla de módulos 5):
`LocalFileProvider` en v0.1 y `OpenBaoProvider` (Transit, US-134) en v0.2. Los métodos
son `async` porque OpenBao se habla con `httpx.AsyncClient`.

El proveedor del proceso lo fija el `lifespan` de `create_app` (y el worker y el CLI) con
`configure_provider`; el keyring (US-025) y el bus lo toman con `current_provider()`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.core.config import Settings
from app.core.crypto.errors import CryptoError


@dataclass(frozen=True)
class KeyInfo:
    key_ref: str
    algorithm: str
    provider: str
    version: int
    created_at: datetime


ProviderStatus = Literal["ok", "sealed", "unreachable"]


class KeyProvider(Protocol):
    name: str

    async def wrap(self, dek: bytes) -> bytes: ...

    async def unwrap(self, wrapped: bytes) -> bytes: ...

    async def sign(self, key_ref: str, data: bytes) -> bytes: ...

    async def verify(self, key_ref: str, data: bytes, signature: bytes) -> bool: ...

    async def rotate(self, key_ref: str) -> KeyInfo: ...

    async def key_info(self, key_ref: str) -> KeyInfo: ...

    async def status(self) -> ProviderStatus: ...

    async def rewrap(self, wrapped: bytes) -> bytes: ...


def get_key_provider(settings: Settings) -> KeyProvider:
    """Instancia el proveedor de `CRYPTO_PROVIDER`, comprobando los archivos de llave."""
    if settings.CRYPTO_PROVIDER == "local":
        from app.core.crypto.local_provider import LocalFileProvider  # evita el ciclo al importar

        if settings.CRYPTO_LOCAL_KEK_PATH is None:
            raise CryptoError("kek_missing", "CRYPTO_LOCAL_KEK_PATH no está definida")
        return LocalFileProvider(
            settings.CRYPTO_LOCAL_KEK_PATH, settings.CRYPTO_LOCAL_SIGNING_KEY_PATH
        )
    raise CryptoError(
        "unknown_provider",
        f"proveedor de llaves no disponible en esta versión: {settings.CRYPTO_PROVIDER}",
    )


_provider: KeyProvider | None = None


def configure_provider(provider: KeyProvider | None) -> None:
    """Fija el proveedor del proceso (`None` lo retira)."""
    global _provider
    _provider = provider


def current_provider() -> KeyProvider:
    if _provider is None:
        raise CryptoError("kek_missing", "el proveedor de llaves no está configurado")
    return _provider


ProviderResolver = Callable[[str], KeyProvider]
"""Nombre de proveedor (`crypto_keys.provider`) -> proveedor que abre esa fila (S5-D3)."""


def get_provider_named(settings: Settings, name: str) -> KeyProvider:
    """Proveedor de una fila (`crypto_keys.provider`); se construye al pedirlo (S5-D3, D131).

    `get_key_provider` sigue siendo la fábrica solo de `local`; `openbao` valida su token al primer
    uso, así que construirlo no toca la red ni el archivo.
    """
    if name == "local":
        return get_key_provider(settings)
    if name == "openbao":
        from app.core.crypto.openbao_provider import OpenBaoProvider  # confinado a core/crypto

        if settings.OPENBAO_TOKEN_FILE is None:
            raise CryptoError("kek_missing", "OPENBAO_TOKEN_FILE no está definida")
        return OpenBaoProvider(
            settings.OPENBAO_ADDR,
            settings.OPENBAO_TOKEN_FILE,
            timeout_s=float(settings.OPENBAO_TIMEOUT_S),
        )
    raise CryptoError("unknown_provider", f"proveedor de llaves desconocido: {name}")


def make_resolver(settings: Settings, *, creation: KeyProvider | None = None) -> ProviderResolver:
    """Resolver con caché por nombre: un solo proveedor por proceso y nombre."""
    cache: dict[str, KeyProvider] = {}
    if creation is not None:
        cache[creation.name] = creation

    def resolver(name: str) -> KeyProvider:
        if name not in cache:
            cache[name] = get_provider_named(settings, name)
        return cache[name]

    return resolver
