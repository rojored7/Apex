"""Comprobación de exposición de la llave de firma en el api (S7-D23 (2), H-1; M-1 de S7-W0-3b).

El api monta solo `custody/` y `jwt/` del volumen `keys`; si bajo `/run/apex/keys` aparece un
`sign-ed25519.key` (un `.env` o un montaje viejos que reabren el residual de ADR-006), el arranque
falla. Solo nombra el hecho: nunca la ruta ni el contenido. No abre ningún archivo.

Falla CERRADO: un error al recorrer una subcarpeta (permisos) se relanza como `OSError` en vez de
saltarse en silencio, y un enlace simbólico llamado `sign` o una carpeta con el nombre de la llave
cuentan como exposición (el recorrido no sigue enlaces, así que no se mira dentro).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final, NoReturn

KEYS_ROOT: Path = Path("/run/apex/keys")
SIGNING_KEY_FILENAME: Final = "sign-ed25519.key"
SIGN_DIRNAME: Final = "sign"


def _relanzar(error: OSError) -> NoReturn:
    raise error


def signing_key_exposed(root: Path | None = None) -> bool:
    """Hay un `sign-ed25519.key` (archivo, carpeta o enlace) o un enlace `sign` bajo `root`.

    Recorre sin seguir enlaces; un volumen inexistente (desarrollo fuera de Docker) no expone nada.
    Lanza `OSError` si no puede leer una carpeta: quien llama debe tratarlo como no verificable.
    """
    raiz = KEYS_ROOT if root is None else root
    if not raiz.is_dir():
        return False
    for carpeta, subcarpetas, archivos in os.walk(raiz, followlinks=False, onerror=_relanzar):
        if SIGNING_KEY_FILENAME in archivos or SIGNING_KEY_FILENAME in subcarpetas:
            return True
        if SIGN_DIRNAME in subcarpetas and os.path.islink(os.path.join(carpeta, SIGN_DIRNAME)):
            return True
        if SIGN_DIRNAME in archivos:  # un enlace roto o a archivo con ese nombre
            return True
    return False
