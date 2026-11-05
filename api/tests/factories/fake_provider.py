"""Proveedor de llaves controlable para las pruebas de sellado (S5-B3; S5-D13, S5-D14, S5-D16).

`ProveedorControlable` envuelve un proveedor real (el local de las pruebas) y le añade:

- `estado` (`ok | sealed | unreachable`): lo que devuelve `status()`; con `sealed` o `unreachable`
  `wrap`, `unwrap`, `sign`, `verify`, `rotate`, `key_info` y `rewrap` lanzan `CryptoUnavailable`
  con esa razón, como el `OpenBaoProvider` real;
- `error`: una excepción que `unwrap` lanza siempre (por ejemplo `CryptoError("unwrap_failed")` o
  `CryptoUnavailable("forbidden")`);
- contadores `status_calls`, `wrap_calls` y `unwrap_calls` para afirmar qué tocó el código.

Se llama `local` para que las filas de `crypto_keys` que crea o abre sean las del proveedor local.
`inyectar_proveedor(monkeypatch, proveedor)` lo deja como proveedor del proceso y como resultado de
`get_provider_named` en cada sitio donde el código de producción pueda haberlo importado.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.crypto.errors import CryptoUnavailable
from app.core.crypto.provider import KeyInfo, KeyProvider, ProviderStatus, configure_provider

SITIOS_DE_LA_FABRICA = (
    "app.core.crypto.provider.get_provider_named",
    "app.core.crypto.recovery.get_provider_named",
    "app.main.get_provider_named",
    "app.worker.runtime.get_provider_named",
)


class ProveedorControlable:
    name = "local"

    def __init__(self, delegado: KeyProvider, estado: ProviderStatus = "ok") -> None:
        self._delegado = delegado
        self.estado: ProviderStatus = estado
        self.error: Exception | None = None
        self.last_reason: str | None = None  # como OpenBaoProvider (S5-D200)
        self.bloqueo: asyncio.Event | None = None  # unwrap espera aquí (cancelación)
        self.fallos_unicos: list[Exception] = []  # se lanzan de a uno en unwrap
        self.status_calls = 0
        self.wrap_calls = 0
        self.unwrap_calls = 0

    def _exigir(self) -> None:
        if self.estado != "ok":
            raise CryptoUnavailable(self.estado)

    async def status(self) -> ProviderStatus:
        self.status_calls += 1
        return self.estado

    async def wrap(self, dek: bytes | bytearray) -> bytes:
        self.wrap_calls += 1
        self._exigir()
        return await self._delegado.wrap(dek)

    async def unwrap(self, wrapped: bytes) -> bytes:
        self.unwrap_calls += 1
        self._exigir()
        if self.bloqueo is not None:
            await self.bloqueo.wait()
        if self.fallos_unicos:
            raise self.fallos_unicos.pop(0)
        if self.error is not None:
            raise self.error
        return await self._delegado.unwrap(wrapped)

    async def sign(self, key_ref: str, data: bytes) -> bytes:
        self._exigir()
        return await self._delegado.sign(key_ref, data)

    async def verify(self, key_ref: str, data: bytes, signature: bytes) -> bool:
        self._exigir()
        return await self._delegado.verify(key_ref, data, signature)

    async def rotate(self, key_ref: str) -> KeyInfo:
        self._exigir()
        return await self._delegado.rotate(key_ref)

    async def key_info(self, key_ref: str) -> KeyInfo:
        self._exigir()
        return await self._delegado.key_info(key_ref)

    async def rewrap(self, wrapped: bytes) -> bytes:
        self._exigir()
        return await self._delegado.rewrap(wrapped)

    def __repr__(self) -> str:
        return f"ProveedorControlable({self.estado})"


def inyectar_proveedor(monkeypatch: pytest.MonkeyPatch, proveedor: ProveedorControlable) -> None:
    """Proveedor del proceso y resultado de `get_provider_named` (donde exista ese nombre)."""

    def fabrica(settings: object, name: str) -> ProveedorControlable:
        return proveedor

    for sitio in SITIOS_DE_LA_FABRICA:
        monkeypatch.setattr(sitio, fabrica, raising=False)
    configure_provider(proveedor)


__all__ = ["ProveedorControlable", "inyectar_proveedor"]
