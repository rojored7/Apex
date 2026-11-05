"""`types.reveal` tiene una sola puerta fuera de `core/` (S3-B9b; D-4, S3-D59, N-01, N-21).

Por AST sobre `src/app` (salvo `app/core`, dueño del bus):
- la llamada a `reveal(...)` (como `types.reveal(...)`, `crypto_types.reveal(...)` o el
  nombre importado de `app.core.crypto.types`) está en `modules/members/detail.py`, dentro de la
  función `_decrypt_fields` (más la segunda puerta de la exportación, S5-B12); así ninguna
  ruta nueva descifra un campo de socio sin pasar por la
  función que recibe el propósito (`mask` en la ficha, `reveal` en B10);
- ningún archivo fuera de `core/` llama a `bus.decrypt(...)` (descifrar a mano saltaría el
  propósito y el `record_id` que pone `types.reveal`).

Controles con fuentes falsas: una llamada fuera de `_decrypt_fields`, un alias importado y un
`bus.decrypt` se detectan; la puerta legítima pasa.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "src" / "app"
PUERTA = ("modules/members/detail.py", "_decrypt_fields")
# S5-B12 (S5-D60, M-10): la exportación descifra por lote con propósito `export`; es la SEGUNDA
# y última puerta permitida (Rojo B12).
PUERTA_EXPORTACION = ("modules/members/exports.py", "_decrypt_batch")
TYPES_MODULE = "app.core.crypto.types"
BUS_MODULE = "app.core.crypto.bus"


def _alias(arbol: ast.AST) -> tuple[set[str], set[str], set[str]]:
    """`(módulos types, nombres de reveal, módulos bus)` con que el archivo los importa."""
    tipos: set[str] = set()
    reveals: set[str] = set()
    buses: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module == TYPES_MODULE:
            reveals |= {a.asname or a.name for a in nodo.names if a.name == "reveal"}
        if isinstance(nodo, ast.ImportFrom) and nodo.module == "app.core.crypto":
            tipos |= {a.asname or a.name for a in nodo.names if a.name == "types"}
            buses |= {a.asname or a.name for a in nodo.names if a.name == "bus"}
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                if a.name == TYPES_MODULE:
                    tipos.add(a.asname or a.name)
                if a.name == BUS_MODULE:
                    buses.add(a.asname or a.name)
    return tipos, reveals, buses


def _texto(expr: ast.expr) -> str:
    return ast.unparse(expr)


def llamadas(fuente: str) -> tuple[list[tuple[str | None, int]], list[int]]:
    """`(reveal, decrypt)`: cada llamada a `reveal` con la función que la contiene (o `None`) y
    las líneas de `bus.decrypt(...)`."""
    arbol = ast.parse(fuente)
    tipos, reveals, buses = _alias(arbol)
    de_reveal: list[tuple[str | None, int]] = []
    de_decrypt: list[int] = []

    def visitar(nodo: ast.AST, funcion: str | None) -> None:
        for hijo in ast.iter_child_nodes(nodo):
            actual = funcion
            if isinstance(hijo, ast.FunctionDef | ast.AsyncFunctionDef):
                actual = hijo.name
            if isinstance(hijo, ast.Call):
                f = hijo.func
                if isinstance(f, ast.Name) and f.id in reveals:
                    de_reveal.append((actual, hijo.lineno))
                if isinstance(f, ast.Attribute) and f.attr == "reveal":
                    if _texto(f.value) in tipos or _texto(f.value).endswith("types"):
                        de_reveal.append((actual, hijo.lineno))
                if isinstance(f, ast.Attribute) and f.attr == "decrypt":
                    if _texto(f.value) in buses or _texto(f.value).endswith("bus"):
                        de_decrypt.append(hijo.lineno)
            visitar(hijo, actual)

    visitar(arbol, None)
    return de_reveal, de_decrypt


def _fuera_de_core() -> list[Path]:
    return sorted(
        p for p in APP.rglob("*.py") if not p.relative_to(APP).as_posix().startswith("core/")
    )


def test_reveal_solo_se_llama_en_decrypt_fields_de_members_detail() -> None:
    encontradas: list[tuple[str, str | None]] = []
    for archivo in _fuera_de_core():
        de_reveal, _ = llamadas(archivo.read_text(encoding="utf-8"))
        relativo = archivo.relative_to(APP).as_posix()
        encontradas.extend((relativo, funcion) for funcion, _ in de_reveal)
    assert PUERTA in encontradas
    assert set(encontradas) <= {PUERTA, PUERTA_EXPORTACION}, encontradas


def test_la_exportacion_es_la_segunda_puerta_de_reveal_y_solo_una_vez() -> None:
    """S5-B12 (S5-D60): `members/exports.py::_decrypt_batch` llama a `types.reveal` (un lote, una
    fila de `crypto_ops` por clase) y es la única llamada fuera de `_decrypt_fields`."""
    encontradas: list[tuple[str, str | None]] = []
    for archivo in _fuera_de_core():
        de_reveal, _ = llamadas(archivo.read_text(encoding="utf-8"))
        relativo = archivo.relative_to(APP).as_posix()
        encontradas.extend((relativo, funcion) for funcion, _ in de_reveal)
    assert sorted(encontradas, key=str) == sorted([PUERTA, PUERTA_EXPORTACION], key=str)


def test_nadie_fuera_de_core_llama_a_bus_decrypt() -> None:
    malas = [
        f"{archivo.relative_to(APP).as_posix()}:{linea}"
        for archivo in _fuera_de_core()
        for linea in llamadas(archivo.read_text(encoding="utf-8"))[1]
    ]
    assert malas == [], malas


# Controles del analizador --------------------------------------------------------------------

FUENTE_PUERTA = """
from app.core.crypto import types

def _decrypt_fields(socio, campos, purpose):
    return {c: types.reveal(socio, c, purpose) for c in campos}
"""

FUENTE_MALA = """
from app.core.crypto import bus, types
from app.core.crypto.types import reveal as abrir
import app.core.crypto.types as tipos

def get(socio):
    return types.reveal(socio, "document", "mask")

def otra(socio):
    return abrir(socio, "phone", "reveal"), tipos.reveal(socio, "email", "mask")

def a_mano(blob, aad):
    return bus.decrypt(blob, aad)

valor = types.reveal(None, "document", "mask")
"""


def test_el_analizador_acepta_la_puerta() -> None:
    assert llamadas(FUENTE_PUERTA) == ([("_decrypt_fields", 5)], [])


def test_el_analizador_detecta_llamadas_fuera_de_la_puerta_alias_y_decrypt() -> None:
    de_reveal, de_decrypt = llamadas(FUENTE_MALA)
    assert sorted(de_reveal, key=lambda par: par[1]) == [
        ("get", 7),
        ("otra", 10),
        ("otra", 10),
        (None, 15),
    ]
    assert de_decrypt == [13]


# S5-B7 (S5-D27, S5-D32, M-9): el teléfono de un aviso sale por `contact_for_notification` ----


def test_notifications_no_descifra_a_mano_ni_importa_el_bus() -> None:
    """Ningún archivo de `modules/notifications/` llama a `types.reveal` ni a `bus.decrypt`, ni
    importa `app.core.crypto`: el teléfono del enlace de WhatsApp se obtiene solo con
    `members.service.contact_for_notification` (que audita `reveal` y escribe `crypto_ops`)."""
    archivos = sorted((APP / "modules" / "notifications").rglob("*.py"))
    assert archivos, "el módulo notifications debe existir"
    for archivo in archivos:
        fuente = archivo.read_text(encoding="utf-8")
        de_reveal, de_decrypt = llamadas(fuente)
        assert de_reveal == [] and de_decrypt == [], archivo.name
        assert "app.core.crypto" not in fuente, archivo.name
