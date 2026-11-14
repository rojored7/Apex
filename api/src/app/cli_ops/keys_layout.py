"""`init-keys --migrate-layout` (S6-D58, S5-D201, S7-D4): mueve el volumen `keys` al layout nuevo.

Layout viejo (plano, v0.2): `kek.bin`, `sign-ed25519.key`, `jwt_ed25519.pem`, `jwt_ed25519.pub` en
la raíz del volumen. Layout de v0.3: `custody/` (`kek.bin`, `sign-ed25519.key`) y `jwt/`. Layout
nuevo (v0.4): `custody/` (`kek.bin`), `sign/` (`sign-ed25519.key`, que el api no monta) y `jwt/`.
`--reverse` devuelve la llave de firma de `sign/` a `custody/` (rollback a v0.3, RUNBOOK §12).

Cada archivo se mueve con `os.link` + `os.unlink` dentro del mismo volumen (un `rename` que NO
pisa: `os.link` falla con `FileExistsError` si el destino existe, también si otro `tools` lo creó
después de comprobar el conflicto, S7-W0-3b L-1): sin copias en claro ni temporales, y el modo y
el dueño viajan con el inodo. Nunca sobrescribe: si un nombre existe en los dos layouts es un
conflicto y no se mueve NADA (todo o nada). `custody/`, `sign/` y `jwt/` no pueden ser enlaces
simbólicos (conflicto) y se reponen en 700. Es idempotente. Cualquier otro
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
    "sign-ed25519.key": "sign",
    "jwt_ed25519.pem": "jwt",
    "jwt_ed25519.pub": "jwt",
}
SUBCARPETA_MODO: Final = 0o700
# archivos que el layout de v0.3 guardaba en otra subcarpeta: nombre -> subcarpeta anterior
LAYOUT_V03: Final[dict[str, str]] = {"sign-ed25519.key": "custody"}


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


def _origenes(directory: Path, nombre: str) -> list[Path]:
    """Dónde está hoy el archivo fuera de su carpeta nueva: la raíz (plano) y, si lo hubo, la
    subcarpeta de v0.3."""
    candidatos = [directory / nombre]
    if nombre in LAYOUT_V03:
        candidatos.append(directory / LAYOUT_V03[nombre] / nombre)
    return [c for c in candidatos if os.path.lexists(c)]


def _es_conflicto(directory: Path, nombre: str, origenes: list[Path]) -> bool:
    """Un enlace simbólico de origen, dos orígenes o un destino ya ocupado: no se mueve nada
    (todo o nada)."""
    destino = directory / LAYOUT_NUEVO[nombre] / nombre
    return len(origenes) > 1 or any(o.is_symlink() for o in origenes) or os.path.lexists(destino)


def _subcarpeta_enlace(directory: Path) -> bool:
    """Alguna de las subcarpetas del layout (incluida `custody/`) es un enlace simbólico."""
    return any((directory / sub).is_symlink() for sub in set(LAYOUT_NUEVO.values()) | {"custody"})


def ensure_subdirs(directory: Path) -> None:
    """Crea `custody/`, `sign/` y `jwt/` (700) aunque no haya nada que migrar (S6-W0-2, S7-D4) y
    repone el modo 700 de las que ya existían (`mkdir(exist_ok=True)` no lo cambia)."""
    for sub in sorted(set(LAYOUT_NUEVO.values())):
        carpeta = directory / sub
        carpeta.mkdir(mode=SUBCARPETA_MODO, parents=True, exist_ok=True)
        os.chmod(carpeta, SUBCARPETA_MODO)


def _mover_sin_pisar(origen: Path, destino: Path) -> None:
    """Un `rename` que falla con `FileExistsError` en vez de pisar (atómico, mismo volumen)."""
    os.link(origen, destino)
    os.unlink(origen)


def migrate_layout(directory: Path) -> LayoutReport:
    """Mueve los archivos de `directory` (raíz del volumen) a `custody/`, `sign/` y `jwt/`: los
    planos de la raíz y la llave de firma de `custody/` (layout de v0.3). Un `rename` atómico
    dentro del mismo volumen: sin copia (S7-D34), idempotente y sin pisar."""
    origenes = {n: _origenes(directory, n) for n in LAYOUT_NUEVO}
    pendientes = [n for n, o in origenes.items() if o]
    conflictos = tuple(n for n in pendientes if _es_conflicto(directory, n, origenes[n]))
    if conflictos:
        return LayoutReport(conflicts=conflictos)
    if pendientes and _subcarpeta_enlace(directory):
        return LayoutReport(conflicts=tuple(pendientes))
    ensure_subdirs(directory)
    movidos: list[str] = []
    for nombre in pendientes:
        try:
            _mover_sin_pisar(origenes[nombre][0], directory / LAYOUT_NUEVO[nombre] / nombre)
        except FileExistsError:  # carrera: el destino apareció tras comprobar el conflicto
            return LayoutReport(moved=tuple(movidos), conflicts=(nombre,))
        movidos.append(nombre)
    return LayoutReport(moved=tuple(movidos))


def reverse_layout(directory: Path) -> LayoutReport:
    """Rollback a v0.3: devuelve `sign/sign-ed25519.key` a `custody/` (`os.link` + `os.unlink`).

    Reabre el residual de ADR-006 mientras dure: el api de v0.3 monta el volumen entero. Un destino
    ocupado o un enlace simbólico es conflicto y no se mueve nada."""
    nombre = "sign-ed25519.key"
    origen = directory / LAYOUT_NUEVO[nombre] / nombre
    destino = directory / LAYOUT_V03[nombre] / nombre
    if not os.path.lexists(origen):
        return LayoutReport()
    if origen.is_symlink() or os.path.lexists(destino) or _subcarpeta_enlace(directory):
        return LayoutReport(conflicts=(nombre,))
    destino.parent.mkdir(mode=SUBCARPETA_MODO, parents=True, exist_ok=True)
    os.chmod(destino.parent, SUBCARPETA_MODO)
    try:
        _mover_sin_pisar(origen, destino)
    except FileExistsError:
        return LayoutReport(conflicts=(nombre,))
    return LayoutReport(moved=(nombre,))
