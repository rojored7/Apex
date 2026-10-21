"""`core/crypto/digest.py`: SHA-256 hexadecimal, sin llave, solo `hashlib` (US-015 T3, N-06)."""

from __future__ import annotations

import ast
from pathlib import Path

from app.core.crypto.digest import sha256_hex

DIGEST = Path(__file__).resolve().parents[2] / "src" / "app" / "core" / "crypto" / "digest.py"


def test_vectores_conocidos() -> None:
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert sha256_hex(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_formato_hexadecimal_minuscula_de_64() -> None:
    valor = sha256_hex("ñandú".encode())
    assert len(valor) == 64
    assert valor == valor.lower()
    assert set(valor) <= set("0123456789abcdef")


def test_determinista() -> None:
    assert sha256_hex(b"x" * 1000) == sha256_hex(b"x" * 1000)
    assert sha256_hex(b"a") != sha256_hex(b"b")


def test_solo_importa_hashlib() -> None:
    arbol = ast.parse(DIGEST.read_text(encoding="utf-8"))
    modulos = {
        (a.name if isinstance(n, ast.Import) else n.module)
        for n in ast.walk(arbol)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    assert modulos <= {"hashlib", "__future__"}, modulos
