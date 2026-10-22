"""`find_banned_imports(source, path)` e `is_allowed(path)` de `_imports.py` (S2-B7, US-031).

Fuera de `core/crypto/`, `core/security.py` y `core/security/` ningún archivo importa
`cryptography`, `oqs`, `hashlib`, `hmac`, `jwt` ni `argon2` (CLAUDE.md, bus regla 8): ni con
`import`, ni con `from ... import`, ni con `importlib.import_module("...")`, `import_module(...)`
o `__import__("...")` con un literal. Cada hallazgo trae archivo, línea y el nombre importado.
"""

from __future__ import annotations

import pytest

from tests.architecture._imports import (
    BANNED_MODULES,
    BannedImport,
    find_banned_imports,
    is_allowed,
)

SERVICIO = "app/modules/members/service.py"


def _nombres(source: str, path: str = SERVICIO) -> list[tuple[int, str]]:
    return [(h.line, h.imported) for h in find_banned_imports(source, path)]


def test_la_lista_prohibida_es_la_de_claude_md() -> None:
    assert frozenset({"cryptography", "oqs", "hashlib", "hmac", "jwt", "argon2"}) == BANNED_MODULES


def test_import_hashlib_en_el_service_se_reporta_con_archivo_y_linea() -> None:
    hallazgos = find_banned_imports('"""doc."""\n\nimport hashlib\n', SERVICIO)
    assert hallazgos == [BannedImport(file=SERVICIO, line=3, imported="hashlib")]
    assert str(hallazgos[0]) == f"{SERVICIO}:3 importa hashlib"


def test_from_cryptography_hazmat_se_reporta() -> None:
    fuente = "x = 1\nfrom cryptography.hazmat.primitives import hashes\n"
    assert _nombres(fuente) == [(2, "cryptography.hazmat.primitives")]


@pytest.mark.parametrize(
    ("fuente", "esperado"),
    [
        ('import importlib\nimportlib.import_module("hmac")\n', [(2, "hmac")]),
        ('from importlib import import_module\nimport_module("argon2")\n', [(2, "argon2")]),
        ('__import__("jwt")\n', [(1, "jwt")]),
        ('__import__("oqs.kem")\n', [(1, "oqs.kem")]),
    ],
)
def test_los_imports_dinamicos_con_literal_se_reportan(
    fuente: str, esperado: list[tuple[int, str]]
) -> None:
    assert _nombres(fuente) == esperado


def test_los_imports_dentro_de_funciones_y_type_checking_se_reportan() -> None:
    fuente = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    import jwt\n"
        "def f() -> None:\n"
        "    import argon2.low_level\n"
    )
    assert _nombres(fuente) == [(3, "jwt"), (5, "argon2.low_level")]


def test_varios_alias_en_una_linea_se_reportan_todos() -> None:
    assert _nombres("import os, hashlib, hmac\n") == [(1, "hashlib"), (1, "hmac")]


@pytest.mark.parametrize(
    "fuente",
    [
        "import hashlibx\n",
        "import jwtools\n",
        "from oqsy import x\n",
        "from . import hashlib\n",  # relativo: el propio paquete, no la biblioteca
        "importlib.import_module(nombre)\n",  # no es un literal
        'texto = "import hashlib"\n',
    ],
)
def test_lo_que_no_es_un_import_prohibido_no_se_reporta(fuente: str) -> None:
    assert _nombres(fuente) == []


@pytest.mark.parametrize(
    "path",
    [
        "app/core/crypto/aead.py",
        "app/core/crypto/mac.py",
        "app/core/security.py",
        "app/core/security/tokens.py",
        "src/app/core/crypto/bus.py",
        "core/security.py",
    ],
)
def test_el_bus_y_security_pueden_importar(path: str) -> None:
    assert is_allowed(path)
    assert find_banned_imports("import hashlib\nfrom cryptography import x\n", path) == []


@pytest.mark.parametrize(
    "path",
    [
        SERVICIO,
        "app/core/audit.py",
        "app/core/securityx.py",
        "app/core/cryptox/a.py",
        "app/modules/auth/core/crypto/a.py",
        "app/core/logging.py",
    ],
)
def test_fuera_del_bus_no_esta_permitido(path: str) -> None:
    assert not is_allowed(path)
    assert _nombres("import hashlib\n", path) == [(1, "hashlib")]


def test_una_ruta_de_windows_se_normaliza() -> None:
    assert is_allowed(r"app\core\crypto\aead.py")
    assert not is_allowed(r"app\modules\members\service.py")
