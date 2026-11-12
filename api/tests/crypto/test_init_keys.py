"""`cli init-keys`: KEK, llave de firma y par JWT con modo 600, idempotente (US-023 T12; A-1)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.cli import app, key_paths_in
from app.core.crypto.digest import sha256_hex

runner = CliRunner()
SOLO_POSIX = pytest.mark.skipif(os.name == "nt", reason="NTFS no conserva el modo POSIX")


def _modo(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _huellas(directorio: Path) -> dict[str, str]:
    # S6-W0-2: layout con subcarpetas custody/ y jwt/ (rglob, claves relativas).
    return {
        p.relative_to(directorio).as_posix(): sha256_hex(p.read_bytes())
        for p in sorted(directorio.rglob("*"))
        if p.is_file()
    }


def test_crea_los_cuatro_archivos(tmp_path: Path) -> None:
    directorio = tmp_path / "keys"
    resultado = runner.invoke(app, ["init-keys", "--dir", str(directorio)])
    assert resultado.exit_code == 0, resultado.output
    rutas = key_paths_in(directorio)
    assert rutas.kek.read_bytes().__len__() == 32
    assert rutas.signing_key.read_bytes().__len__() == 32
    pem = rutas.jwt_private.read_text(encoding="ascii")
    assert ("BEGIN " + "PRIVATE KEY") in pem
    assert "BEGIN PUBLIC KEY" in rutas.jwt_public.read_text(encoding="ascii")
    # S6-W0-2 (S6-D58): custody/ (KEK y firma) y jwt/ (el par JWT) bajo la raíz del volumen.
    assert rutas.kek == directorio / "custody" / "kek.bin"
    assert rutas.jwt_private == directorio / "jwt" / "jwt_ed25519.pem"
    assert sorted(p.name for p in directorio.iterdir()) == ["custody", "jwt"]
    assert sorted(p.name for p in (directorio / "custody").iterdir()) == [
        "kek.bin",
        "sign-ed25519.key",
    ]
    assert sorted(p.name for p in (directorio / "jwt").iterdir()) == [
        "jwt_ed25519.pem",
        "jwt_ed25519.pub",
    ]
    assert "creada" in resultado.output


@SOLO_POSIX
def test_modo_600_y_directorio_700(tmp_path: Path) -> None:
    directorio = tmp_path / "keys"
    assert runner.invoke(app, ["init-keys", "--dir", str(directorio)]).exit_code == 0
    # S6-W0-2: las subcarpetas custody/ y jwt/ en 700 y cada archivo en 600.
    for subcarpeta in (directorio / "custody", directorio / "jwt"):
        assert _modo(subcarpeta) == 0o700, subcarpeta
        for ruta in subcarpeta.iterdir():
            assert _modo(ruta) == 0o600, ruta


def test_segunda_ejecucion_es_idempotente_y_no_toca_nada(tmp_path: Path) -> None:
    directorio = tmp_path / "keys"
    assert runner.invoke(app, ["init-keys", "--dir", str(directorio)]).exit_code == 0
    antes = _huellas(directorio)
    segunda = runner.invoke(app, ["init-keys", "--dir", str(directorio)])
    assert segunda.exit_code == 0, segunda.output
    assert _huellas(directorio) == antes
    assert "ya existe" in segunda.output and "creada" not in segunda.output


def test_completa_solo_lo_que_falta(tmp_path: Path) -> None:
    directorio = tmp_path / "keys"
    assert runner.invoke(app, ["init-keys", "--dir", str(directorio)]).exit_code == 0
    rutas = key_paths_in(directorio)
    kek_antes = rutas.kek.read_bytes()
    rutas.jwt_private.unlink()
    rutas.jwt_public.unlink()
    resultado = runner.invoke(app, ["init-keys", "--dir", str(directorio)])
    assert resultado.exit_code == 0
    assert rutas.kek.read_bytes() == kek_antes
    assert rutas.jwt_private.is_file() and rutas.jwt_public.is_file()


def test_as_solo_se_anota_y_data_class_solo_admite_clases_de_firma(tmp_path: Path) -> None:
    """Desde A2 (US-141) la opcion --data-class existe de verdad: una clase que no es de firma
    sale con 2 y unknown_data_class, sin tocar el directorio de llaves."""
    directorio = tmp_path / "keys"
    resultado = runner.invoke(
        app, ["init-keys", "--dir", str(directorio), "--as", "ana@apex.local"]
    )
    assert resultado.exit_code == 0, resultado.output
    con_clase = runner.invoke(
        app, ["init-keys", "--dir", str(directorio), "--data-class", "member.document"]
    )
    assert con_clase.exit_code == 2
    assert "unknown_data_class" in con_clase.output


def test_la_salida_no_contiene_material(tmp_path: Path) -> None:
    directorio = tmp_path / "keys"
    resultado = runner.invoke(app, ["init-keys", "--dir", str(directorio)])
    rutas = key_paths_in(directorio)
    for ruta in (rutas.kek, rutas.signing_key):
        assert ruta.read_bytes().hex() not in resultado.output
    assert ("BEGIN " + "PRIVATE KEY") not in resultado.output
