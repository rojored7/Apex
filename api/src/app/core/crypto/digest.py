"""SHA-256 sin llave para la cadena de auditoría (US-015 T3, N-06).

Contrato: `sha256_hex` es determinista, no usa llave y nunca escribe en
`crypto_ops`. Si el bus registrara cada digest, el hook de auditoría escribiría
durante un flush y abriría recursión. Este módulo solo importa `hashlib`;
`core/audit.py` lo toma directamente (`tests/architecture/test_core_import_direction.py`).
"""

from __future__ import annotations

import hashlib


def sha256_hex(data: bytes) -> str:
    """SHA-256 de `data`, en 64 caracteres hexadecimales minúsculas."""
    return hashlib.sha256(data).hexdigest()
