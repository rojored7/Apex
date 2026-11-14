"""Regla de la ruta de la llave de firma (S7-D23 (1), H-1).

La semilla de firma solo la ven el worker y las herramientas: su ruta no puede quedar bajo la
carpeta de la KEK (`custody/`, que monta el api) ni bajo la del JWT (`jwt/`), ni estar vacía
(`CRYPTO_LOCAL_SIGNING_KEY_PATH=` vale `Path(".")` porque `Settings` no ignora los vacíos). Puro:
recibe rutas, no lee el disco ni el entorno; `config.py` lo llama desde un validador del modelo.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

DEFAULT_SIGNING_KEY_PATH: Final = Path("/run/apex/keys/sign/sign-ed25519.key")


def _bajo(ruta: Path, carpeta: Path) -> bool:
    """`ruta` está dentro de `carpeta` (comparación léxica, sin tocar el disco)."""
    r = Path(os.path.normcase(os.path.normpath(ruta)))
    c = Path(os.path.normcase(os.path.normpath(carpeta)))
    return c in r.parents


def signing_path_problems(signing: Path, kek: Path | None, jwt_private: Path) -> list[str]:
    """Nombres de variable inválidos (jamás valores): `[]` si la ruta de firma es aceptable."""
    if os.path.normpath(signing) == ".":
        return ["CRYPTO_LOCAL_SIGNING_KEY_PATH"]
    expuesta = _bajo(signing, jwt_private.parent) or (
        kek is not None and _bajo(signing, kek.parent)
    )
    return ["CRYPTO_LOCAL_SIGNING_KEY_PATH"] if expuesta else []
