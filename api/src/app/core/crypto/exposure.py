"""Comprobación de exposición de la llave de firma en el api (S7-D23 (2), H-1).

El api monta solo `custody/` y `jwt/` del volumen `keys`; si bajo `/run/apex/keys` aparece un
`sign-ed25519.key` (un `.env` o un montaje viejos que reabren el residual de ADR-006), el arranque
falla. Solo nombra el hecho: nunca la ruta ni el contenido. No abre ningún archivo.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

KEYS_ROOT: Path = Path("/run/apex/keys")
SIGNING_KEY_FILENAME: Final = "sign-ed25519.key"


def signing_key_exposed(root: Path | None = None) -> bool:
    """Hay un `sign-ed25519.key` (archivo o enlace) bajo `root` (por omisión `KEYS_ROOT`).

    Recorre sin seguir enlaces; un volumen inexistente (desarrollo fuera de Docker) no expone nada.
    """
    raiz = KEYS_ROOT if root is None else root
    for _carpeta, _subcarpetas, archivos in os.walk(raiz, followlinks=False):
        if SIGNING_KEY_FILENAME in archivos:
            return True
    return False
