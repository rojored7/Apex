"""Protege la regla `banned-api` de ruff (CLAUDE.md, bus regla 8; US-002, T2 y T3).

Nadie puede aflojar la configuración sin que falle la suite, y la regla de
verdad bloquea un import de criptografía fuera de `core/crypto` y
`core/security`.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = API_ROOT / "pyproject.toml"
BANNED = ("cryptography", "oqs", "hashlib", "hmac", "jwt", "argon2")
ALLOWED_TID251 = {"src/app/core/crypto/**", "src/app/core/security.py"}

CODIGO_PROHIBIDO = (
    "import hashlib\n"
    "from cryptography.hazmat.primitives.ciphers.aead import AESGCM\n"
    "\n"
    "\n"
    "def huella(data: bytes) -> bytes:\n"
    "    AESGCM(b'k' * 32)\n"
    "    return hashlib.sha256(data).digest()\n"
)


def _ruff_lint() -> dict[str, Any]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    lint: dict[str, Any] = data["tool"]["ruff"]["lint"]
    return lint


def test_banned_api_lista_los_seis_modulos() -> None:
    banned = _ruff_lint()["flake8-tidy-imports"]["banned-api"]
    for name in BANNED:
        assert name in banned, f"{name} falta en banned-api"
        assert banned[name]["msg"], f"{name} no tiene mensaje"


def test_tid_esta_seleccionado() -> None:
    select = _ruff_lint()["select"]
    assert "TID" in select or "TID251" in select


def test_solo_crypto_y_security_ignoran_tid251() -> None:
    ignores = _ruff_lint()["per-file-ignores"]
    con_tid = {
        ruta for ruta, codigos in ignores.items() if any(c.startswith("TID") for c in codigos)
    }
    assert con_tid == ALLOWED_TID251


def _proyecto_temporal(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        PYPROJECT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def _ruff_check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", "--output-format", "concise", "src"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def test_import_prohibido_falla(tmp_path: Path) -> None:
    root = _proyecto_temporal(tmp_path)
    modulo = root / "src" / "app" / "modules" / "x" / "service.py"
    modulo.parent.mkdir(parents=True)
    modulo.write_text(CODIGO_PROHIBIDO, encoding="utf-8")

    resultado = _ruff_check(root)

    assert resultado.returncode != 0, resultado.stdout + resultado.stderr
    assert resultado.stdout.count("TID251") >= 2, resultado.stdout


def test_import_permitido_dentro_del_bus(tmp_path: Path) -> None:
    root = _proyecto_temporal(tmp_path)
    modulo = root / "src" / "app" / "core" / "crypto" / "bus.py"
    modulo.parent.mkdir(parents=True)
    modulo.write_text(CODIGO_PROHIBIDO, encoding="utf-8")

    resultado = _ruff_check(root)

    assert "TID251" not in resultado.stdout, resultado.stdout
