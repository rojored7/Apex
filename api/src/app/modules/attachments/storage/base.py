"""Puerto `StorageProvider` (S6-C1; S6-D21). La clave es siempre `^[0-9a-f]{32}$`."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Final, Protocol

KEY_PATTERN: Final = r"^[0-9a-f]{32}$"
CHUNK_SIZE: Final = 65536
_KEY_RE: Final = re.compile(r"[0-9a-f]{32}")


def check_key(key: str) -> str:
    """Valida la clave ANTES de tocar disco o red: `fullmatch` rechaza hasta un `\\n` final."""
    if not isinstance(key, str) or _KEY_RE.fullmatch(key) is None:
        raise ValueError("clave de objeto inválida")
    return key


def is_key(name: str) -> bool:
    return _KEY_RE.fullmatch(name) is not None


class StorageProvider(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...

    async def get(self, key: str) -> bytes: ...

    def stream(self, key: str, chunk_size: int = CHUNK_SIZE) -> AsyncIterator[bytes]: ...

    async def exists(self, key: str) -> bool: ...

    async def delete_object(self, key: str) -> None: ...

    def list_keys(self) -> AsyncIterator[str]: ...
