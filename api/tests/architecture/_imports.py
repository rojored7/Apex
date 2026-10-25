"""Analizador de imports entre módulos (US-022; reglas de módulos 1 y 2 de CLAUDE.md).

Herramienta de prueba, no de `src/`. Recorre todo el árbol con `ast.walk`, así detecta
imports dentro de funciones y de bloques `if TYPE_CHECKING`, resuelve los relativos y
trata igual una llamada `importlib.import_module("...")` con una cadena literal.

Reglas:
- (a) `foreign_models`: `app.modules.<y>.models` con `y` distinto del módulo propio;
- (b) `router_models`: cualquier `app.modules.<*>.models` importado desde un `router.py`;
- (c) `foreign_router`: `app.modules.<y>.router` con `y` distinto del módulo propio;
- (d) `foreign_non_service`: solo con `ALLOW_FOREIGN_SCHEMAS = False`; `schemas.py` y
  `exceptions.py` ajenos son contrato público del service (decisión del gate, US-022).
- (e) `private_helper` (S2-D4, E8): un helper privado de otro módulo (`PRIVATE_HELPERS`, por
  ejemplo `app.modules.auth.rules`, `tokens` y `cookies`, y desde la revisión Python H1 los
  archivos en que se partió el service: `events`, `sessions`, `users` y `links`); el propio
  módulo sí los usa. Otro módulo ve los eventos y casos de uso por `auth.service`.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

ALLOW_FOREIGN_SCHEMAS: Final = True
PREFIX: Final = "app.modules."
FOREIGN_ALLOWED: Final[frozenset[str]] = frozenset({"service", "schemas", "exceptions"})
# Archivos privados por módulo: solo su propio módulo los importa (S2-D4).
PRIVATE_HELPERS: Final[dict[str, frozenset[str]]] = {
    "auth": frozenset({"rules", "tokens", "cookies", "events", "sessions", "users", "links"}),
    # S3-B1 (D7): `memberships` nace partido tras la fachada `service.py`.
    "memberships": frozenset({"rules", "events", "sell", "lifecycle", "queries"}),
}

Rule = Literal[
    "foreign_models", "router_models", "foreign_router", "foreign_non_service", "private_helper"
]


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    imported: str
    rule: Rule

    def __str__(self) -> str:
        return f"{self.file}:{self.line} importa {self.imported} ({self.rule})"


def _package_of(file: Path, module: str) -> str:
    """Paquete absoluto del archivo, asumiendo que vive bajo `app/modules/<module>/`."""
    partes = list(file.parts)
    if module in partes:
        indice = len(partes) - 1 - partes[::-1].index(module)
        sub = partes[indice + 1 : -1]
    else:
        sub = []
    return ".".join([PREFIX + module, *sub])


def _resolve_relative(package: str, level: int, name: str | None) -> str:
    base = package.split(".")
    base = base[: len(base) - (level - 1)] if level > 1 else base
    return ".".join([*base, name] if name else base)


def _imported_names(arbol: ast.AST, package: str) -> list[tuple[int, str]]:
    nombres: list[tuple[int, str]] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.extend((nodo.lineno, alias.name) for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            modulo = (
                _resolve_relative(package, nodo.level, nodo.module) if nodo.level else nodo.module
            )
            if modulo is None:
                continue
            nombres.append((nodo.lineno, modulo))
            nombres.extend((nodo.lineno, f"{modulo}.{alias.name}") for alias in nodo.names)
        elif (
            isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr == "import_module"
            and nodo.args
            and isinstance(nodo.args[0], ast.Constant)
            and isinstance(nodo.args[0].value, str)
        ):
            nombres.append((nodo.lineno, nodo.args[0].value))
    return nombres


def _rule_for(name: str, *, module: str, is_router: bool) -> tuple[str, Rule] | None:
    if not name.startswith(PREFIX):
        return None
    partes = name[len(PREFIX) :].split(".")
    if len(partes) < 2:
        return None
    owner, archivo = partes[0], partes[1]
    target = f"{PREFIX}{owner}.{archivo}"
    if archivo == "models":
        if owner != module:
            return target, "foreign_models"
        if is_router:
            return target, "router_models"
        return None
    if owner == module:
        return None
    if archivo in PRIVATE_HELPERS.get(owner, frozenset()):
        return target, "private_helper"
    if archivo == "router":
        return target, "foreign_router"
    if archivo not in FOREIGN_ALLOWED or (not ALLOW_FOREIGN_SCHEMAS and archivo != "service"):
        return target, "foreign_non_service"
    return None


def find_forbidden_imports(
    file: Path, *, module: str, source: str | None = None
) -> list[Violation]:
    """Violaciones del archivo `file` del módulo `module` (lee el archivo si no hay `source`)."""
    texto = source if source is not None else file.read_text(encoding="utf-8")
    arbol = ast.parse(texto, filename=str(file))
    package = _package_of(file, module)
    is_router = file.name == "router.py"
    vistas: set[tuple[int, str, str]] = set()
    salida: list[Violation] = []
    for linea, nombre in _imported_names(arbol, package):
        regla = _rule_for(nombre, module=module, is_router=is_router)
        if regla is None:
            continue
        target, rule = regla
        clave = (linea, target, rule)
        if clave in vistas:
            continue
        vistas.add(clave)
        salida.append(Violation(file=file.as_posix(), line=linea, imported=target, rule=rule))
    return salida


# Imports prohibidos fuera del bus (S2-B7, US-031; CLAUDE.md, bus regla 8) --------------------

BANNED_MODULES: Final[frozenset[str]] = frozenset(
    {"cryptography", "oqs", "hashlib", "hmac", "jwt", "argon2"}
)


@dataclass(frozen=True)
class BannedImport:
    file: str
    line: int
    imported: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} importa {self.imported}"


def _relative_to_app(path: str) -> str:
    rel = path.replace("\\", "/").removeprefix("./")
    rel = rel.removeprefix("src/")
    return rel.removeprefix("app/")


def is_allowed(path: str) -> bool:
    """`core/crypto/`, `core/security.py` y `core/security/` (relativo a `app/`)."""
    rel = _relative_to_app(path)
    return (
        rel.startswith("core/crypto/")
        or rel == "core/security.py"
        or rel.startswith("core/security/")
    )


def _is_banned(name: str) -> bool:
    return name.split(".", 1)[0] in BANNED_MODULES


def _literal_import(nodo: ast.Call) -> str | None:
    """`importlib.import_module("x")`, `import_module("x")` o `__import__("x")` con literal."""
    funcion = nodo.func
    nombre = (
        funcion.attr
        if isinstance(funcion, ast.Attribute)
        else funcion.id
        if isinstance(funcion, ast.Name)
        else None
    )
    if nombre not in {"import_module", "__import__"} or not nodo.args:
        return None
    primero = nodo.args[0]
    if isinstance(primero, ast.Constant) and isinstance(primero.value, str):
        return primero.value
    return None


def _all_imports(arbol: ast.AST) -> list[tuple[int, str]]:
    nombres: list[tuple[int, str]] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.extend((nodo.lineno, alias.name) for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level == 0 and nodo.module:
                nombres.append((nodo.lineno, nodo.module))
        elif isinstance(nodo, ast.Call):
            literal = _literal_import(nodo)
            if literal is not None:
                nombres.append((nodo.lineno, literal))
    return sorted(nombres)


def find_banned_imports(source: str, path: str) -> list[BannedImport]:
    """Imports prohibidos de `source` (archivo `path`); vacío si `is_allowed(path)`."""
    if is_allowed(path):
        return []
    arbol = ast.parse(source, filename=path)
    return [
        BannedImport(file=path, line=linea, imported=nombre)
        for linea, nombre in _all_imports(arbol)
        if _is_banned(nombre)
    ]
