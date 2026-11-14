"""`S3CompatibleStorage` (S6-C1; S6-D21, S6-D45): `boto3` se importa de forma perezosa.

Apagado por defecto (`STORAGE_PROVIDER=local`). Cliente con credenciales EXPLÍCITAS de `Settings`
(nunca la cadena por defecto de `boto3`: ni `AWS_*` ni `~/.aws`), `verify=True`, sin proxies del
entorno y tres reintentos. La clave del objeto es la del adjunto, sin prefijo.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from app.core.config import Settings
from app.modules.attachments.exceptions import StorageUnavailable
from app.modules.attachments.storage.base import CHUNK_SIZE, check_key, is_key

_AUSENTE = frozenset({"404", "NoSuchKey", "NotFound"})


class S3CompatibleStorage:
    name: ClassVar[str] = "s3"

    def __init__(self, settings: Settings) -> None:
        try:  # `import_module`: sin stubs de tipos y sin romper si el extra `s3` no está instalado
            boto3 = importlib.import_module("boto3")
            Config = importlib.import_module("botocore.config").Config
        except ImportError as error:
            raise ValueError(
                "S3 requiere boto3: instale el extra s3 (uv sync --extra s3)"
            ) from error
        secreto = settings.S3_SECRET_ACCESS_KEY
        if secreto is None or settings.S3_BUCKET is None:
            raise ValueError("faltan S3_BUCKET o S3_SECRET_ACCESS_KEY")
        self._bucket: str = settings.S3_BUCKET
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            region_name=settings.S3_REGION,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=secreto.get_secret_value(),
            verify=True,
            config=Config(
                proxies={},
                retries={"max_attempts": 3},
                connect_timeout=5,
                read_timeout=30,
            ),
        )

    def __repr__(self) -> str:
        return f"S3CompatibleStorage(bucket={self._bucket!r})"

    @staticmethod
    def _code(error: Exception) -> str:
        respuesta = getattr(error, "response", None) or {}
        return str(respuesta.get("Error", {}).get("Code", ""))

    def _traducir(self, error: Exception) -> Exception:
        if self._code(error) in _AUSENTE:
            return FileNotFoundError("objeto ausente")
        return StorageUnavailable()

    def _put(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def _get(self, key: str) -> bytes:
        return bytes(self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read())

    async def put(self, key: str, data: bytes) -> None:
        check_key(key)
        try:
            await asyncio.to_thread(self._put, key, data)
        except Exception as error:
            raise self._traducir(error) from error

    async def get(self, key: str) -> bytes:
        check_key(key)
        try:
            return await asyncio.to_thread(self._get, key)
        except Exception as error:
            raise self._traducir(error) from error

    def stream(self, key: str, chunk_size: int = CHUNK_SIZE) -> AsyncIterator[bytes]:
        check_key(key)
        return self._stream(key, chunk_size)

    async def _stream(self, key: str, chunk_size: int) -> AsyncIterator[bytes]:
        try:
            respuesta = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=key
            )
        except Exception as error:
            raise self._traducir(error) from error
        cuerpo = respuesta["Body"]
        trozos = cuerpo.iter_chunks(chunk_size)
        try:
            while True:
                trozo = await asyncio.to_thread(next, trozos, None)
                if trozo is None:
                    return
                yield trozo
        finally:
            await asyncio.to_thread(cuerpo.close)

    async def exists(self, key: str) -> bool:
        check_key(key)
        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=key)
        except Exception as error:
            if self._code(error) in _AUSENTE:
                return False
            raise StorageUnavailable() from error
        return True

    async def delete_object(self, key: str) -> None:
        check_key(key)
        try:
            await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)
        except Exception as error:
            raise StorageUnavailable() from error

    def _keys(self) -> list[str]:
        claves: list[str] = []
        paginador = self._client.get_paginator("list_objects_v2")
        for pagina in paginador.paginate(Bucket=self._bucket):
            claves.extend(o["Key"] for o in pagina.get("Contents", []) if is_key(o["Key"]))
        return sorted(claves)

    async def list_keys(self) -> AsyncIterator[str]:
        try:
            claves = await asyncio.to_thread(self._keys)
        except Exception as error:
            raise StorageUnavailable() from error
        for clave in claves:
            yield clave
