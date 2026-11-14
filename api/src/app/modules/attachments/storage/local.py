"""`LocalDiskStorage` (S6-C1; S6-D21, S6-D60, M-9).

Escritura atómica: temporal con modo 600 en la MISMA carpeta, `fsync`, `os.replace` y `fsync` de la
carpeta (POSIX). Todo el I/O de disco va en `asyncio.to_thread`. Las claves se validan antes de
tocar el disco, así que ningún nombre llega a construir una ruta fuera de la raíz.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import ClassVar

from app.modules.attachments.storage.base import CHUNK_SIZE, check_key, is_key

_TMP_PREFIX = ".tmp-"


class LocalDiskStorage:
    name: ClassVar[str] = "local"

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / check_key(key)

    def _write(self, path: Path, data: bytes) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = self.root / f"{_TMP_PREFIX}{uuid.uuid4().hex}"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        if sys.platform != "win32":
            dir_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        await asyncio.to_thread(self._write, path, data)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        return await asyncio.to_thread(path.read_bytes)

    def stream(self, key: str, chunk_size: int = CHUNK_SIZE) -> AsyncIterator[bytes]:
        path = self._path(key)
        return self._stream(path, chunk_size)

    @staticmethod
    async def _stream(path: Path, chunk_size: int) -> AsyncIterator[bytes]:
        handle = await asyncio.to_thread(path.open, "rb")
        try:
            while True:
                trozo = await asyncio.to_thread(handle.read, chunk_size)
                if not trozo:
                    return
                yield trozo
        finally:
            await asyncio.to_thread(handle.close)

    async def exists(self, key: str) -> bool:
        path = self._path(key)
        return await asyncio.to_thread(path.is_file)

    async def delete_object(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, True)

    def _names(self) -> list[str]:
        if not self.root.is_dir():  # solo lectura: no se crea la carpeta
            return []
        return sorted(p.name for p in self.root.iterdir() if is_key(p.name) and p.is_file())

    async def list_keys(self) -> AsyncIterator[str]:
        for nombre in await asyncio.to_thread(self._names):
            yield nombre
