"""Secretos de operación que no pueden estar en el entorno del api (M2, S4B-D56).

Extraído de `config.py` (S7-W0-3) para no pasar de 800 líneas; `config.py` lo reexporta.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

# H-1 / M2 (S4B-D56): con ENV=production el entorno de un servicio que lee Settings no puede traer
# secretos de operación (`.env.ops` mezclado en `.env`). Nombres exactos y prefijos; nunca valores.
OPS_SECRET_NAMES: Final[frozenset[str]] = frozenset({"POSTGRES_PASSWORD"})
OPS_SECRET_PREFIXES: Final[tuple[str, ...]] = ("RCLONE_", "BACKUP_SIGN_", "BACKUP_VERIFY_")
# S5-W0-3: la llave PÚBLICA de minisign no es secreta y pasa a `Settings` (S5-D44, D72); la privada
# (`BACKUP_SIGN_KEY_FILE`) sigue siendo secreto de operación.
OPS_SECRET_EXEMPT: Final[frozenset[str]] = frozenset({"BACKUP_SIGN_PUBKEY"})


def ops_secret_names(environ: Mapping[str, str]) -> list[str]:
    """Nombres (jamás valores) de las variables de operación secretas presentes en `environ`."""
    return sorted(
        nombre
        for nombre in environ
        if nombre not in OPS_SECRET_EXEMPT
        and (
            nombre in OPS_SECRET_NAMES
            or nombre.startswith(OPS_SECRET_PREFIXES)
            or (nombre.startswith("APEX_") and nombre.endswith("_DB_PASSWORD"))
        )
    )
