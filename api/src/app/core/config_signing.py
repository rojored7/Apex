"""Regla de la ruta de la llave de firma (S7-D23 (1), H-1; endurecida en S7-W0-3b, M-2).

La semilla de firma solo la ven el worker y las herramientas: su ruta no puede quedar bajo la
carpeta de la KEK ni bajo las del JWT (`custody/` y `jwt/`, que monta el api), ni bajo esas dos
carpetas FIJAS del volumen aunque no haya KEK local (con OpenBao `CRYPTO_LOCAL_KEK_PATH` es
`None` y `compose.openbao.yml` monta igual `custody/` en el api). Tampoco puede ser vacía
(`CRYPTO_LOCAL_SIGNING_KEY_PATH=` vale `Path(".")` porque `Settings` no ignora los vacíos), relativa
ni llevar `..`. Puro: recibe rutas, no lee el disco ni el entorno; `config.py` lo llama desde un
validador del modelo.

[DECISIÓN DE DISEÑO] Forma mínima y no la estricta («solo absolutas bajo `/run/apex/keys/sign/`»):
las pruebas y el CLI usan rutas temporales (`tmp_path`) para la semilla, que la forma estricta
rompería. La estricta la cubre ya `deploy.sh` para producción (solo `*/sign/*` absoluta).
"""

from __future__ import annotations

import os
from pathlib import Path, PurePath
from typing import Final

DEFAULT_SIGNING_KEY_PATH: Final = Path("/run/apex/keys/sign/sign-ed25519.key")
_KEYS_ROOT: Final = PurePath("/run/apex/keys")
CARPETAS_DEL_API: Final = (_KEYS_ROOT / "custody", _KEYS_ROOT / "jwt")
VARIABLE: Final = "CRYPTO_LOCAL_SIGNING_KEY_PATH"


def _bajo(ruta: PurePath, carpeta: PurePath) -> bool:
    """`ruta` está dentro de `carpeta` (comparación léxica, sin tocar el disco)."""
    r = PurePath(os.path.normcase(os.path.normpath(ruta)))
    c = PurePath(os.path.normcase(os.path.normpath(carpeta)))
    return c in r.parents


def signing_path_problems(
    signing: Path,
    kek: Path | None,
    jwt_private: Path,
    jwt_public: Path | None = None,
) -> list[str]:
    """Nombres de variable inválidos (jamás valores): `[]` si la ruta de firma es aceptable."""
    if not signing.anchor or ".." in signing.parts or os.path.normpath(signing) == ".":
        return [VARIABLE]  # vacía, relativa o con `..`
    prohibidas: list[PurePath] = [*CARPETAS_DEL_API, jwt_private.parent]
    if jwt_public is not None:
        prohibidas.append(jwt_public.parent)
    if kek is not None:
        prohibidas.append(kek.parent)
    return [VARIABLE] if any(_bajo(signing, c) for c in prohibidas) else []
