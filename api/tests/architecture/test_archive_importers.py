"""Importadores de `app.core.crypto.archive` (S4B-B2; C6, S4B-D20, S4B-D59).

`archive.py` guarda `digest_file` y (B3a) las funciones de respaldo de la KEK con `age -p` por
`subprocess`. Fuera de `core/` solo lo importa el job de verificación del worker:
`worker/jobs/backup_check.py` (por `digest_file`). B3a suma `cli_ops/kek.py` (S4B-D85) y esta lista
se amplía en ese slice. Ni `main.py`, ni `core/health.py`, ni `core/backup_status.py`, ni los
services, ni `cli.py` lo importan.

Por AST sobre `src/app` (también imports perezosos y relativos). Controles con fuentes falsas.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

SRC: Final = Path(__file__).resolve().parents[2] / "src" / "app"
ARCHIVE: Final = "app.core.crypto.archive"
PERMITIDOS_FUERA_DE_CORE: Final = frozenset({"worker/jobs/backup_check.py"})


def _paquete(path: Path) -> list[str]:
    rel = path.relative_to(SRC).with_suffix("")
    partes = ["app", *rel.parts]
    return partes if path.name == "__init__.py" else partes[:-1]


def importa_archive(fuente: str, path: Path) -> list[int]:
    """Líneas de `fuente` (archivo `path` bajo `src/app`) que importan `app.core.crypto.archive`."""
    arbol = ast.parse(fuente, filename=str(path))
    paquete = _paquete(path)
    lineas: list[int] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            if any(a.name == ARCHIVE or a.name.startswith(ARCHIVE + ".") for a in nodo.names):
                lineas.append(nodo.lineno)
        elif isinstance(nodo, ast.ImportFrom):
            base = nodo.module or ""
            if nodo.level:
                raiz = paquete[: len(paquete) - (nodo.level - 1)]
                base = ".".join([*raiz, base] if base else raiz)
            if base == ARCHIVE or base.startswith(ARCHIVE + "."):
                lineas.append(nodo.lineno)
            elif base == "app.core.crypto" and any(a.name == "archive" for a in nodo.names):
                lineas.append(nodo.lineno)
    return lineas


def importadores_fuera_de_core() -> set[str]:
    salida: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith("core/"):
            continue
        if importa_archive(path.read_text(encoding="utf-8"), path):
            salida.add(rel)
    return salida


# Reglas sobre el árbol real -------------------------------------------------------------------


def test_archive_existe_y_expone_digest_file() -> None:
    fuente = (SRC / "core" / "crypto" / "archive.py").read_text(encoding="utf-8")
    nombres = {n.name for n in ast.parse(fuente).body if isinstance(n, ast.FunctionDef)}
    assert "digest_file" in nombres


def test_los_importadores_de_archive_fuera_de_core_son_exactamente_los_fijados() -> None:
    assert importadores_fuera_de_core() == PERMITIDOS_FUERA_DE_CORE


def test_dentro_de_core_solo_lo_importa_el_propio_paquete_crypto() -> None:
    dentro = sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.glob("core/**/*.py")
        if importa_archive(path.read_text(encoding="utf-8"), path)
    )
    assert [d for d in dentro if not d.startswith("core/crypto/")] == []


# Controles con fuentes falsas ------------------------------------------------------------------


def test_control_las_formas_de_import_se_detectan() -> None:
    destino = SRC / "worker" / "jobs" / "falso.py"
    assert importa_archive("from app.core.crypto.archive import digest_file\n", destino) == [1]
    assert importa_archive("import app.core.crypto.archive\n", destino) == [1]
    assert importa_archive("from app.core.crypto import archive\n", destino) == [1]
    assert importa_archive("from ...core.crypto import archive\n", destino) == [1]
    assert importa_archive("from ...core.crypto.archive import digest_file\n", destino) == [1]
    assert importa_archive("def f():\n    from app.core.crypto import archive\n", destino) == [2]
    assert importa_archive("from app.core.crypto import digest\n", destino) == []
    assert importa_archive("from app.core.crypto.digest import sha256_hex\n", destino) == []


def test_control_un_importador_ajeno_a_la_lista_se_detecta() -> None:
    falso = "from app.core.crypto.archive import digest_file\n"
    for relativo in ("main.py", "cli.py", "core/backup_status.py", "modules/plans/service.py"):
        assert importa_archive(falso, SRC / relativo) == [1]
        assert relativo not in PERMITIDOS_FUERA_DE_CORE
