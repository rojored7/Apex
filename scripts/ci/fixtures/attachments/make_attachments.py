"""Genera los archivos de prueba de la subida de adjuntos (S6-W0-2, paso 13).

Uso: `python make_attachments.py <carpeta>`. Escribe fotos JPEG (bytes mágicos válidos, resto
ceros; sin datos personales) de 100 KB, 5.242.880, 5.242.881 y 6.300.000 bytes. Solo biblioteca
estándar; idempotente.
"""

from __future__ import annotations

import sys
from pathlib import Path

JPEG_HEAD = bytes.fromhex("ffd8ffe000104a46494600010100000100010000")  # SOI + APP0 JFIF
JPEG_TAIL = bytes.fromhex("ffd9")  # EOI
TAMANOS: dict[str, int] = {
    "foto-100kb.jpg": 100 * 1024,
    "foto-5242880.jpg": 5 * 1024 * 1024,
    "foto-5242881.jpg": 5 * 1024 * 1024 + 1,
    "foto-6300000.jpg": 6_300_000,
}


def jpeg_de(tamano: int) -> bytes:
    """JPEG con cabecera y cierre válidos y exactamente `tamano` bytes."""
    relleno = tamano - len(JPEG_HEAD) - len(JPEG_TAIL)
    if relleno < 0:
        raise ValueError("tamaño menor que la cabecera JPEG")
    return JPEG_HEAD + bytes(relleno) + JPEG_TAIL


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("uso: make_attachments.py <carpeta>", file=sys.stderr)
        return 2
    destino = Path(argv[0])
    destino.mkdir(parents=True, exist_ok=True)
    for nombre, tamano in TAMANOS.items():
        (destino / nombre).write_bytes(jpeg_de(tamano))
        print(f"make_attachments: {nombre} {tamano} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
