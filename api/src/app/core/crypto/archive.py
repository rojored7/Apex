"""Archivos de respaldo: digest en reposo y (B3a) respaldo de la KEK con `age -p`.

S4B-B2 (S4B-D20, S4B-D59): `digest_file(path, chunk_size)` calcula el SHA-256 de un archivo por
bloques, sin cargarlo entero y sin seguir enlaces simbólicos (`O_NOFOLLOW`). Lo usa el job
`backup_check` del worker para comprobar el `sha256` en reposo del manifiesto; el worker no ejecuta
`age` ni abre ninguna identidad (S4B-D59). `AGE_BINARY` y `AGE_TIMEOUT_S` son las constantes del
binario que usan las funciones de la KEK (llegan en B3a).

"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Final

DIGEST_CHUNK: Final = 1 << 20
"""Tamaño de bloque de lectura de `digest_file` (1 MiB)."""

AGE_BINARY: Final = "/usr/bin/age"
"""Ruta del binario `age` (B3a; el worker nunca lo abre)."""

AGE_TIMEOUT_S: Final = 600
"""Tiempo máximo de una llamada a `age` (B3a)."""


def digest_file(path: Path, chunk_size: int = DIGEST_CHUNK, *, max_bytes: int | None = None) -> str:
    """SHA-256 hexadecimal (minúsculas) de `path`, leído por bloques de `chunk_size` bytes.

    Un archivo inexistente lanza `FileNotFoundError`; un enlace simbólico lanza `OSError`
    (`O_NOFOLLOW`); un FIFO, un dispositivo o un directorio lanzan `OSError` sin bloquear
    (`O_NONBLOCK` evita colgarse en el `open` y `fstat` exige un archivo regular antes de leer).
    Las banderas que no existen en la plataforma quedan en 0 (`getattr`). Un `chunk_size` no
    positivo lanza `ValueError`. Con `max_bytes`, leer más que ese tope (archivo que creció) lanza
    `OSError`; leer exactamente `max_bytes` es válido.
    """
    if chunk_size <= 0:
        raise ValueError("digest_file: chunk_size debe ser positivo")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags | getattr(os, "O_NONBLOCK", 0))
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("digest_file: no es un archivo regular")
    except BaseException:
        os.close(descriptor)
        raise
    resumen = hashlib.sha256()
    leidos = 0
    with os.fdopen(descriptor, "rb", buffering=0) as archivo:
        while bloque := archivo.read(chunk_size):
            leidos += len(bloque)
            if max_bytes is not None and leidos > max_bytes:
                raise OSError("digest_file: el archivo supera el tamaño esperado")
            resumen.update(bloque)
    return resumen.hexdigest()
