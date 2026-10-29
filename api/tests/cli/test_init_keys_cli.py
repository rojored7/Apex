"""`init-keys` por la CLI real (`CliRunner`; S4A-D39: `cli.py` entra en la cobertura).

Sobre un directorio vacío crea la KEK (32 bytes), la semilla de firma (32 bytes) y el par JWT
Ed25519 en PEM, con modo 600 (en POSIX; NTFS no guarda esos bits); una segunda corrida dice "ya
existe" para los tres y no cambia ni un byte (A-1). `--as` solo se anota en la salida y
`--data-class` sale con 2 (US-140).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from app.cli import KEK_LEN, SEED_LEN, app, key_paths_in
from tests.cli._apoyo import correr


def _contenidos(directorio: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directorio.iterdir())}


def test_init_keys_crea_los_cuatro_archivos_privados(tmp_path: Path) -> None:
    directorio = tmp_path / "keys"
    rutas = key_paths_in(directorio)

    resultado = correr(app, ["init-keys", "--dir", str(directorio)])

    assert resultado.exit_code == 0, resultado.output
    assert resultado.output.count(": creada") == 3
    assert len(rutas.kek.read_bytes()) == KEK_LEN
    assert len(rutas.signing_key.read_bytes()) == SEED_LEN
    # La cabecera va partida para que `detect-private-key` de pre-commit no la tome por una llave.
    assert rutas.jwt_private.read_bytes().startswith(b"-----BEGIN " + b"PRIVATE KEY-----")
    assert rutas.jwt_public.read_bytes().startswith(b"-----BEGIN PUBLIC KEY-----")
    if os.name != "nt":
        for ruta in (rutas.kek, rutas.signing_key, rutas.jwt_private, rutas.jwt_public):
            assert stat.S_IMODE(ruta.stat().st_mode) == 0o600, ruta


def test_init_keys_es_idempotente(tmp_path: Path) -> None:
    directorio = tmp_path / "keys"
    primera = correr(app, ["init-keys", "--dir", str(directorio)])
    antes = _contenidos(directorio)

    segunda = correr(app, ["init-keys", "--dir", str(directorio), "--as", "ana@test.apex"])

    assert primera.exit_code == 0 and segunda.exit_code == 0
    assert segunda.output.count(": ya existe (por ana@test.apex)") == 3
    assert ": creada" not in segunda.output
    assert _contenidos(directorio) == antes


def test_init_keys_data_class_no_implementado_sale_con_2(tmp_path: Path) -> None:
    directorio = tmp_path / "keys"

    resultado = correr(app, ["init-keys", "--dir", str(directorio), "--data-class", "member.x"])

    assert resultado.exit_code == 2
    assert not directorio.exists()
