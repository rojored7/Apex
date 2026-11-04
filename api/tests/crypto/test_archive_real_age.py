"""`archive.py` con el binario `age` real y una terminal real (S4B-B3a, S4B-D58, S4B-D89, S4B-D103).

Solo Linux con `age` instalado: en el host Windows se saltan (se cuentan por archivo en el
cuaderno) y la CI las exige sin saltos (S4B-D103). Cada prueba corre el código bajo `pty.fork`
con un subproceso de Python, porque `age` pide la frase por `/dev/tty`:
- ida y vuelta: `export_kek_file` y `restore_kek_file` reproducen la KEK;
- recuperable sin APEX: `age -d` a mano con la misma frase entrega los mismos 32 bytes;
- frase equivocada: `restore_kek_file` falla y no deja la KEK.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from app.core.crypto import archive
from tests.factories.pty_run import correr_con_pty

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which(archive.AGE_BINARY) is None,
    reason="age real y pty solo en Linux",
)

FRASE = "una-frase-de-prueba-larga-y-unica-7391"

_PREAMBULO = (
    "import sys; from pathlib import Path; from types import SimpleNamespace;"
    "from app.core.crypto import archive;"
    "archive.get_settings = lambda: SimpleNamespace("
    "BACKUP_DIR=Path(sys.argv[3]), CRYPTO_LOCAL_KEK_PATH=Path(sys.argv[4]));"
)
_EXPORTAR = _PREAMBULO + "archive.export_kek_file(Path(sys.argv[1]), Path(sys.argv[2]))"
_RESTAURAR = _PREAMBULO + "archive.restore_kek_file(Path(sys.argv[1]), Path(sys.argv[2]))"


def _argumentos(codigo: str, a: Path, b: Path, tmp_path: Path, kek_viva: Path) -> list[str]:
    """`BACKUP_DIR` y la KEK viva llegan como argumentos: el subproceso no carga `Settings`."""
    return [sys.executable, "-c", codigo, str(a), str(b), str(tmp_path / "bk"), str(kek_viva)]


def _exportar(kek: Path, salida: Path, tmp_path: Path, frase: str = FRASE) -> int:
    codigo, _ = correr_con_pty(_argumentos(_EXPORTAR, kek, salida, tmp_path, kek), frase)
    return codigo


def test_ida_y_vuelta_con_age_real_reproduce_la_kek(kek_tmp: Path, tmp_path: Path) -> None:
    archivo = tmp_path / "salidas" / "kek.age"
    archivo.parent.mkdir()
    restaurada = tmp_path / "salidas" / "kek-restaurada.bin"

    assert _exportar(kek_tmp, archivo, tmp_path) == 0
    codigo, _ = correr_con_pty(
        _argumentos(_RESTAURAR, archivo, restaurada, tmp_path, kek_tmp), FRASE
    )

    assert codigo == 0
    assert restaurada.read_bytes() == kek_tmp.read_bytes()
    assert kek_tmp.read_bytes() not in archivo.read_bytes()


def test_age_d_a_mano_con_la_misma_frase_reproduce_la_kek(kek_tmp: Path, tmp_path: Path) -> None:
    archivo = tmp_path / "salidas" / "kek.age"
    archivo.parent.mkdir()
    manual = tmp_path / "salidas" / "manual.bin"
    assert _exportar(kek_tmp, archivo, tmp_path) == 0

    codigo, _ = correr_con_pty([archive.AGE_BINARY, "-d", "-o", str(manual), str(archivo)], FRASE)

    assert codigo == 0 and manual.read_bytes() == kek_tmp.read_bytes()


def test_frase_equivocada_falla_y_no_deja_la_kek(kek_tmp: Path, tmp_path: Path) -> None:
    archivo = tmp_path / "salidas" / "kek.age"
    archivo.parent.mkdir()
    restaurada = tmp_path / "salidas" / "kek-restaurada.bin"
    assert _exportar(kek_tmp, archivo, tmp_path) == 0

    codigo, _ = correr_con_pty(
        _argumentos(_RESTAURAR, archivo, restaurada, tmp_path, kek_tmp), "otra-frase-distinta"
    )

    assert codigo != 0
    assert not restaurada.exists() or restaurada.read_bytes() != kek_tmp.read_bytes()
