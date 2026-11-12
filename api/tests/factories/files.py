"""Archivos de prueba para los adjuntos (S6-C1; S6-D22, S6-D59, S6-D84).

Cabeceras con bytes mágicos válidos y relleno determinista; ningún dato personal. Los generadores
devuelven exactamente `size` bytes (los tamaños de borde del tope de 5 MiB: 5.242.880 y 5.242.881).

- `jpeg(size)`, `png(size)`, `pdf(size)`: el tipo lo deciden los primeros bytes.
- `elf(size)` y `pe(size)`: ejecutables que NO se admiten, aunque se llamen `.jpg`.
- `MARCA_PDF`: texto reconocible dentro del PDF; las pruebas de cifrado en reposo exigen que no
  aparezca en el objeto guardado.
- `en_trozos(data, size)`: iterador asíncrono de trozos; `Contado` anota cuántos bytes entregó (la
  prueba de que la lectura se detiene); `infinito()` nunca termina; `lento(...)` entrega un trozo
  y luego espera más de lo permitido.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Final

TOPE: Final = 5_242_880
TOPE_MAS_UNO: Final = TOPE + 1
MARCA_PDF: Final = b"APEX-PRUEBA-AUTORIZACION-SENSIBLE-0123456789"

_JPEG: Final = bytes.fromhex("ffd8ffe000104a46494600010100000100010000")
_PNG: Final = bytes.fromhex("89504e470d0a1a0a0000000d49484452")
_PDF: Final = b"%PDF-1.4\n%" + MARCA_PDF + b"\n"
_ELF: Final = bytes.fromhex("7f454c46020101000000000000000000")
_PE: Final = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"


def _con_relleno(cabecera: bytes, size: int, relleno: bytes = b"\x00") -> bytes:
    if size < len(cabecera):
        raise ValueError("size menor que la cabecera")
    return cabecera + relleno * (size - len(cabecera))


def jpeg(size: int = 2048) -> bytes:
    return _con_relleno(_JPEG, size, b"\xa5")


def png(size: int = 2048) -> bytes:
    return _con_relleno(_PNG, size, b"\x5a")


def pdf(size: int = 4096) -> bytes:
    return _con_relleno(_PDF, size, b"0")


def elf(size: int = 2048) -> bytes:
    return _con_relleno(_ELF, size)


def pe(size: int = 2048) -> bytes:
    return _con_relleno(_PE, size)


async def en_trozos(data: bytes, tam: int = 65536) -> AsyncIterator[bytes]:
    """Los bytes de `data` en trozos de a lo sumo `tam`."""
    for inicio in range(0, len(data), tam):
        yield data[inicio : inicio + tam]


class Contado:
    """Iterador asíncrono que cuenta cuánto entregó (`bytes_entregados`, `trozos`)."""

    def __init__(self, data: bytes, tam: int = 65536) -> None:
        self._data = data
        self._tam = tam
        self._pos = 0
        self.bytes_entregados = 0
        self.trozos = 0

    def __aiter__(self) -> Contado:
        return self

    async def __anext__(self) -> bytes:
        if self._pos >= len(self._data):
            raise StopAsyncIteration
        trozo = self._data[self._pos : self._pos + self._tam]
        self._pos += len(trozo)
        self.bytes_entregados += len(trozo)
        self.trozos += 1
        return trozo


class Infinito:
    """Un cliente que no deja de mandar: `cabecera` primero y luego ceros para siempre."""

    def __init__(self, cabecera: bytes, tam: int = 65536) -> None:
        self._cabecera = cabecera
        self._tam = tam
        self._primero = True
        self.bytes_entregados = 0

    def __aiter__(self) -> Infinito:
        return self

    async def __anext__(self) -> bytes:
        if self._primero:
            self._primero = False
            trozo = self._cabecera
        else:
            trozo = b"\x00" * self._tam
        self.bytes_entregados += len(trozo)
        await asyncio.sleep(0)  # cede el control: el lector debe poder cortar o expirar
        return trozo


class Lento:
    """Entrega `primero` y luego espera `espera_s` antes del segundo trozo (D84: cliente que no
    cierra y no manda). Si la espera termina, entrega `resto` y acaba."""

    def __init__(self, primero: bytes, espera_s: float, resto: bytes = b"") -> None:
        self._trozos = [primero]
        self._espera_s = espera_s
        self._resto = resto
        self._entregado = 0
        self.espero_de_mas = False

    def __aiter__(self) -> Lento:
        return self

    async def __anext__(self) -> bytes:
        if self._entregado == 0:
            self._entregado = 1
            return self._trozos[0]
        if self._entregado == 1:
            self._entregado = 2
            await asyncio.sleep(self._espera_s)
            self.espero_de_mas = True
            return self._resto
        raise StopAsyncIteration
