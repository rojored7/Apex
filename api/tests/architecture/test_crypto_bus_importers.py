"""Quién importa `app.core.crypto.bus` y `app.core.crypto.types` fuera de `core/` (S4A-B6;
S4A-D21, C7; blueprint B6).

Por AST sobre `src/app` (también imports dentro de funciones y `importlib.import_module` con una
cadena literal). Los importadores reales, calculados con grep al abrir B6 y fijados aquí, son:
- `modules/members/service.py` y `changes.py` (`bus`: índices ciegos y cifrado del documento);
- `modules/members/detail.py` (`types`: la única puerta `_decrypt_fields`) y `models.py`
  (`types`: los tipos de columna `Encrypted` y `BlindIndexed`);
- el arranque: `main.py`, `cli.py` y `worker/runtime.py`, que solo importan
  `install_crypto_type_listeners` de `types` (cablean los listeners al crear el proceso).

Lista blanca: `app.core.*`, `app.modules.members.*`, `athletes` y `attachments` cuando existan
(v0.3 y v0.6), y el arranque con ese único nombre. `members/contact.py` no entra: descifra por
`detail._decrypt_fields` y nunca importa el bus (S4A-D21). Control con una fuente falsa en
`notifications`, que debe fallar.

Revisión de B6 (`security-reviewer` LOW): los imports relativos (`from ..core.crypto import bus`)
se resuelven contra el paquete del archivo, y el acceso por atributo `.bus` o `.types` sobre
`app.core.crypto` importado como módulo (`import app.core.crypto as c; c.bus`, `from app.core
import crypto; crypto.types`, `import app.core.crypto; app.core.crypto.bus`) cuenta como importar
el módulo entero.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

APP: Final = Path(__file__).resolve().parents[2] / "src" / "app"
PAQUETE: Final = "app.core.crypto"
VIGILADOS: Final = frozenset({f"{PAQUETE}.bus", f"{PAQUETE}.types"})
INSTALADOR: Final = "install_crypto_type_listeners"

IMPORTADORES_REALES: Final = frozenset(
    {
        "cli.py",
        "main.py",
        "worker/runtime.py",
        "modules/members/changes.py",
        "modules/members/detail.py",
        "modules/members/models.py",
        "modules/members/service.py",
    }
)
ARRANQUE: Final = frozenset({"cli.py", "main.py", "worker/runtime.py"})
PREFIJOS_PERMITIDOS: Final = (
    "core/",
    "modules/members/",
    "modules/athletes/",
    "modules/attachments/",
)


def _absoluto(nodo: ast.ImportFrom, paquete: str) -> str:
    """El módulo de un `from ... import` con los relativos resueltos contra `paquete`."""
    if nodo.level == 0:
        return nodo.module or ""
    partes = paquete.split(".")
    base = partes[: len(partes) - (nodo.level - 1)]
    return ".".join([*base, nodo.module] if nodo.module else base)


def _dotted(nodo: ast.expr) -> str | None:
    """`a.b.c` de una cadena de atributos sobre un nombre; `None` si no lo es."""
    if isinstance(nodo, ast.Name):
        return nodo.id
    if isinstance(nodo, ast.Attribute):
        cabeza = _dotted(nodo.value)
        return None if cabeza is None else f"{cabeza}.{nodo.attr}"
    return None


def _alias_del_paquete(arbol: ast.Module, paquete: str) -> set[str]:
    """Nombres locales ligados a `app.core.crypto` como módulo, más su ruta completa."""
    alias = {PAQUETE}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            alias.update(a.asname for a in nodo.names if a.name == PAQUETE and a.asname)
        elif isinstance(nodo, ast.ImportFrom):
            modulo = _absoluto(nodo, paquete)
            for a in nodo.names:
                if f"{modulo}.{a.name}" == PAQUETE:
                    alias.add(a.asname or a.name)
    return alias


def _vistas_de_import(nodo: ast.AST, paquete: str) -> list[tuple[str, str]]:
    """Pares `(módulo vigilado, nombre)` de un nodo de import o de `import_module`."""
    if isinstance(nodo, ast.ImportFrom):
        modulo = _absoluto(nodo, paquete)
        if modulo == PAQUETE:
            vigilados = (f"{PAQUETE}.{a.name}" for a in nodo.names)
            return [(m, "*") for m in vigilados if m in VIGILADOS]
        return [(modulo, a.name) for a in nodo.names] if modulo in VIGILADOS else []
    if isinstance(nodo, ast.Import):
        return [(a.name, "*") for a in nodo.names if a.name in VIGILADOS]
    if (
        isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and nodo.func.attr == "import_module"
        and nodo.args
        and isinstance(nodo.args[0], ast.Constant)
        and nodo.args[0].value in VIGILADOS
    ):
        return [(str(nodo.args[0].value), "*")]
    return []


def importaciones(fuente: str, paquete: str = "app") -> dict[str, set[str]]:
    """`{módulo vigilado: nombres importados}`; `"*"` cuando se importa el módulo entero.
    `paquete` es el paquete del archivo (para resolver los imports relativos)."""
    arbol = ast.parse(fuente)
    alias = _alias_del_paquete(arbol, paquete)
    vistas: dict[str, set[str]] = {}
    for nodo in ast.walk(arbol):
        for modulo, nombre in _vistas_de_import(nodo, paquete):
            vistas.setdefault(modulo, set()).add(nombre)
        if isinstance(nodo, ast.Attribute) and _dotted(nodo.value) in alias:
            modulo = f"{PAQUETE}.{nodo.attr}"
            if modulo in VIGILADOS:
                vistas.setdefault(modulo, set()).add("*")
    return vistas


def _paquete_de(relativo: str) -> str:
    """`modules/members/detail.py` -> `app.modules.members`."""
    return ".".join(["app", *Path(relativo).parent.parts])


def permitido(relativo: str, vistas: dict[str, set[str]]) -> bool:
    if relativo.startswith(PREFIJOS_PERMITIDOS):
        return True
    if relativo in ARRANQUE:
        return set(vistas) == {f"{PAQUETE}.types"} and vistas[f"{PAQUETE}.types"] == {INSTALADOR}
    return False


def _importadores() -> dict[str, dict[str, set[str]]]:
    salida: dict[str, dict[str, set[str]]] = {}
    for archivo in sorted(APP.rglob("*.py")):
        relativo = archivo.relative_to(APP).as_posix()
        if relativo.startswith("core/"):
            continue
        vistas = importaciones(archivo.read_text(encoding="utf-8"), _paquete_de(relativo))
        if vistas:
            salida[relativo] = vistas
    return salida


def test_los_importadores_fuera_de_core_son_exactamente_los_fijados() -> None:
    assert set(_importadores()) == IMPORTADORES_REALES


def test_todo_importador_esta_en_la_lista_blanca() -> None:
    malos = [r for r, vistas in _importadores().items() if not permitido(r, vistas)]
    assert malos == [], malos


def test_el_arranque_solo_importa_el_instalador_de_types() -> None:
    importadores = _importadores()
    for relativo in ARRANQUE:
        assert importadores[relativo] == {f"{PAQUETE}.types": {INSTALADOR}}, relativo


def test_members_contact_no_importa_el_bus_ni_types() -> None:
    """S4A-D21: el contacto descifra solo por `detail._decrypt_fields` (única puerta)."""
    archivo = APP / "modules" / "members" / "contact.py"
    assert archivo.is_file()
    assert importaciones(archivo.read_text(encoding="utf-8")) == {}


# Controles del analizador ------------------------------------------------------------------------

FUENTE_NOTIFICACIONES = """
from app.core.crypto import bus
import app.core.crypto.types as tipos
from app.core.crypto.types import reveal

def abrir():
    import importlib
    return importlib.import_module("app.core.crypto.bus")
"""


def test_control_una_fuente_falsa_en_notifications_falla() -> None:
    vistas = importaciones(FUENTE_NOTIFICACIONES)
    assert vistas == {
        f"{PAQUETE}.bus": {"*"},
        f"{PAQUETE}.types": {"*", "reveal"},
    }
    assert not permitido("modules/notifications/service.py", vistas)


def test_control_el_arranque_con_otro_nombre_falla_y_la_lista_blanca_pasa() -> None:
    con_bus = importaciones("from app.core.crypto import bus\n")
    assert not permitido("main.py", con_bus)
    otro = importaciones("from app.core.crypto.types import reveal\n")
    assert not permitido("worker/runtime.py", otro)
    instalador = importaciones(f"from app.core.crypto.types import {INSTALADOR}\n")
    assert permitido("cli.py", instalador)
    assert permitido("modules/attachments/service.py", con_bus)
    assert permitido("modules/athletes/service.py", con_bus)
    assert not permitido("modules/payments/service.py", con_bus)
    assert importaciones("from app.core.crypto.secret import Secret\n") == {}


FUENTE_RELATIVA = """
from ...core.crypto import bus
from ...core.crypto.types import reveal
from ... import core
"""

FUENTE_POR_ATRIBUTO = """
import app.core.crypto as c
from app.core import crypto as cripto
import app.core.crypto

def abrir(blob):
    c.bus.decrypt(blob)
    app.core.crypto.types.reveal
    return cripto.types
"""

FUENTE_POR_ATRIBUTO_LIMPIA = """
import app.core.crypto as c
from app.core import crypto

def f(blob):
    return c.digest(blob), crypto.digest
"""


def test_control_los_imports_relativos_se_resuelven_contra_el_paquete() -> None:
    """Revisión de B6 (`security-reviewer` LOW): `from ...core.crypto import bus` desde
    `modules/notifications/` es `app.core.crypto.bus`."""
    paquete = _paquete_de("modules/notifications/service.py")
    assert paquete == "app.modules.notifications"
    vistas = importaciones(FUENTE_RELATIVA, paquete)
    assert vistas == {f"{PAQUETE}.bus": {"*"}, f"{PAQUETE}.types": {"reveal"}}
    assert not permitido("modules/notifications/service.py", vistas)
    assert importaciones("from .detail import _decrypt_fields", "app.modules.members") == {}


def test_control_el_acceso_por_atributo_al_paquete_cuenta_como_import() -> None:
    """Revisión de B6 (`security-reviewer` LOW): `c.bus`, `cripto.types` y
    `app.core.crypto.types` sobre el paquete importado como módulo."""
    vistas = importaciones(FUENTE_POR_ATRIBUTO)
    assert vistas == {f"{PAQUETE}.bus": {"*"}, f"{PAQUETE}.types": {"*"}}
    assert not permitido("modules/notifications/service.py", vistas)
    assert importaciones(FUENTE_POR_ATRIBUTO_LIMPIA) == {}
