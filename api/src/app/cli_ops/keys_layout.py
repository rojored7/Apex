"""`init-keys --migrate-layout` (S6-D58, S5-D201): mueve el volumen `keys` plano al layout nuevo.

Layout viejo (plano): `kek.bin`, `sign-ed25519.key`, `jwt_ed25519.pem`, `jwt_ed25519.pub` en la
raíz del volumen. Layout nuevo: `custody/` (`kek.bin`, `sign-ed25519.key`) y `jwt/` (el par JWT).

Cada archivo se mueve con `os.replace` dentro del mismo volumen: sin copias en claro ni
temporales, y el modo y el dueño viajan con el inodo. Nunca sobrescribe: si un nombre existe en
los dos layouts es un conflicto y no se mueve NADA (todo o nada). Es idempotente. Cualquier otro
archivo de la raíz se deja intacto. Este módulo no importa `keys.py` ni `cli.py` (S4B-D76,
S6-D80).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# nombre del archivo -> subcarpeta del layout nuevo (decisión 1 del orquestador: cuatro archivos)
LAYOUT_NUEVO: Final[dict[str, str]] = {
    "kek.bin": "custody",
    "sign-ed25519.key": "custody",
    "jwt_ed25519.pem": "jwt",
    "jwt_ed25519.pub": "jwt",
}
SUBCARPETA_MODO: Final = 0o700


@dataclass(frozen=True)
class LayoutReport:
    """Resultado de `migrate_layout`.

    `moved`: nombres de archivo movidos (por ejemplo `kek.bin`). `conflicts`: nombres presentes
    en los dos layouts; si hay alguno no se mueve NADA (todo o nada).
    """

    moved: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()

    @property
    def nothing_to_migrate(self) -> bool:
        return not self.moved and not self.conflicts


def _es_conflicto(directory: Path, nombre: str) -> bool:
    """Un enlace simbólico en la raíz o un destino ya ocupado: no se mueve nada (todo o nada)."""
    origen = directory / nombre
    return origen.is_symlink() or os.path.lexists(directory / LAYOUT_NUEVO[nombre] / nombre)


def ensure_subdirs(directory: Path) -> None:
    """Crea `custody/` y `jwt/` (700) aunque no haya nada que migrar (revisión de S6-W0-2)."""
    for sub in sorted(set(LAYOUT_NUEVO.values())):
        (directory / sub).mkdir(mode=SUBCARPETA_MODO, parents=True, exist_ok=True)


def migrate_layout(directory: Path) -> LayoutReport:
    """Mueve los archivos planos de `directory` (raíz del volumen) a `custody/` y `jwt/`."""
    pendientes = [n for n in LAYOUT_NUEVO if os.path.lexists(directory / n)]
    conflictos = tuple(n for n in pendientes if _es_conflicto(directory, n))
    if conflictos:
        return LayoutReport(conflicts=conflictos)
    ensure_subdirs(directory)
    for nombre in pendientes:
        os.replace(directory / nombre, directory / LAYOUT_NUEVO[nombre] / nombre)
    return LayoutReport(moved=tuple(pendientes))
