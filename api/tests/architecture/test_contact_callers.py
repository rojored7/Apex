"""Quién puede llamar a `contact_for_notification` (S4A-B6; S4A-D50, M-6 punto 1).

La función es pública en la fachada `members.service`; nada impide por imports que otro módulo
obtenga teléfono y correo en claro sin `members-reveal`. Por AST sobre `src/app`:
- `CONTACT_CALLERS` es la tabla de archivos fuera de `modules/members/` que pueden referenciarla.
  En el Sprint 4A está VACÍA; el Sprint 5 agrega solo `modules/notifications/service.py`.
- Ningún archivo fuera de `modules/members/` (incluye `cli.py` y `worker/`) referencia el nombre,
  ni como nombre, atributo, import o cadena literal (`getattr(svc, "contact_for_notification")`).
- Ningún `router.py` (tampoco el de `members`) la referencia: no hay ruta que la exponga.
- Dentro de `members`, solo `contact.py` (la define) y `service.py` (la re-exporta).
- Revisión de B6 (`security-reviewer` LOW): también cuenta un `from app.modules.members.* import *`
  (trae el nombre sin escribirlo), un `getattr(...)` con un argumento de cadena que contiene
  `contact_` y una concatenación de cadenas literales que forma el nombre (`"contact_" + "for..."`).
Control con fuentes falsas.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

APP: Final = Path(__file__).resolve().parents[2] / "src" / "app"
NOMBRE: Final = "contact_for_notification"
MEMBERS: Final = "modules/members/"

CONTACT_CALLERS: Final[frozenset[str]] = frozenset()
"""Archivos fuera de `modules/members/` autorizados (ruta relativa a `app/`). Vacío en 4A."""

EN_MEMBERS: Final = frozenset({"modules/members/contact.py", "modules/members/service.py"})


PAQUETE_MEMBERS: Final = "app.modules.members"
PREFIJO_SOSPECHOSO: Final = "contact_"


def _cadena(nodo: ast.expr) -> str | None:
    """El texto de una cadena literal o de una concatenación (`+`) de cadenas literales."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
        izquierda, derecha = _cadena(nodo.left), _cadena(nodo.right)
        if izquierda is not None and derecha is not None:
            return izquierda + derecha
    return None


def _importa_todo_de_members(nodo: ast.ImportFrom) -> bool:
    modulo = nodo.module or ""
    es_members = modulo == PAQUETE_MEMBERS or modulo.startswith(f"{PAQUETE_MEMBERS}.")
    return es_members and any(a.name == "*" for a in nodo.names)


def _getattr_sospechoso(nodo: ast.Call) -> bool:
    if not (isinstance(nodo.func, ast.Name) and nodo.func.id == "getattr"):
        return False
    # La concatenación entera si es literal; si no, cada cadena literal de sus piezas.
    textos = [_cadena(arg) for arg in nodo.args]
    textos += [
        sub.value
        for arg in nodo.args
        for sub in ast.walk(arg)
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
    ]
    return any(t is not None and PREFIJO_SOSPECHOSO in t for t in textos)


def _es_referencia(nodo: ast.AST) -> bool:
    if isinstance(nodo, ast.Name):
        return nodo.id == NOMBRE
    if isinstance(nodo, ast.Attribute):
        return nodo.attr == NOMBRE
    if isinstance(nodo, ast.ImportFrom):
        return any(a.name == NOMBRE for a in nodo.names) or _importa_todo_de_members(nodo)
    if isinstance(nodo, ast.Constant | ast.BinOp):
        return _cadena(nodo) == NOMBRE
    if isinstance(nodo, ast.Call):
        return _getattr_sospechoso(nodo)
    if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
        return nodo.name == NOMBRE
    return False


def referencias(fuente: str) -> list[int]:
    """Líneas (sin repetir) donde aparece el nombre como `Name`, atributo, alias de import,
    definición, cadena literal o concatenación de cadenas; más los `import *` de `members` y los
    `getattr` con una cadena que contiene `contact_`."""
    lineas = {
        nodo.lineno
        for nodo in ast.walk(ast.parse(fuente))
        if isinstance(nodo, ast.stmt | ast.expr) and _es_referencia(nodo)
    }
    return sorted(lineas)


def _con_referencias() -> dict[str, list[int]]:
    salida: dict[str, list[int]] = {}
    for archivo in sorted(APP.rglob("*.py")):
        lineas = referencias(archivo.read_text(encoding="utf-8"))
        if lineas:
            salida[archivo.relative_to(APP).as_posix()] = lineas
    return salida


def test_contact_callers_esta_vacio_en_el_sprint_4a() -> None:
    assert frozenset() == CONTACT_CALLERS


def test_nadie_fuera_de_members_la_referencia() -> None:
    fuera = {
        r: lineas
        for r, lineas in _con_referencias().items()
        if not r.startswith(MEMBERS) and r not in CONTACT_CALLERS
    }
    assert fuera == {}, fuera


def test_el_barrido_cubre_cli_y_worker() -> None:
    barridos = {p.relative_to(APP).as_posix() for p in APP.rglob("*.py")}
    assert "cli.py" in barridos
    assert any(r.startswith("worker/") for r in barridos)


def test_ningun_router_la_referencia() -> None:
    routers = [r for r in _con_referencias() if r.endswith("router.py")]
    assert routers == [], routers


def test_dentro_de_members_solo_contact_y_la_fachada() -> None:
    dentro = {r for r in _con_referencias() if r.startswith(MEMBERS)}
    assert dentro == EN_MEMBERS


# Controles del analizador ------------------------------------------------------------------------

FUENTE_MALA = """
from app.modules.members import service as members_service
from app.modules.members.service import contact_for_notification as contacto

async def avisar(session, socio):
    await members_service.contact_for_notification(session, socio, "notify")
    return getattr(members_service, "contact_for_notification")
"""

FUENTE_LIMPIA = """
from app.modules.members import service as members_service

async def ficha(session, socio):
    return await members_service.get(session, socio)
"""


def test_control_el_analizador_detecta_import_atributo_y_cadena() -> None:
    assert referencias(FUENTE_MALA) == [3, 6, 7]
    assert referencias(FUENTE_LIMPIA) == []


FUENTE_MALA_REVISION = """
from app.modules.members.service import *
from app.modules.members.contact import *

async def avisar(session, socio, svc):
    nombre = "contact_" + "for_" + "notification"
    funcion = getattr(svc, "contact_" + elegido)
    return getattr(svc, "contact_for_" + "notification"), getattr(svc, "contact_x")
"""

FUENTE_LIMPIA_REVISION = """
from app.modules.payments.service import *

def ficha(svc, campo):
    contacto = "emergency_contact"
    return getattr(svc, "get"), getattr(svc, campo), "contact_" + campo
"""


def test_control_el_analizador_detecta_import_estrella_getattr_y_concatenacion() -> None:
    """Revisión de B6 (`security-reviewer` LOW): `import *` de `members`, `getattr` con
    `contact_` (también concatenado) y una concatenación literal que forma el nombre."""
    assert referencias(FUENTE_MALA_REVISION) == [2, 3, 6, 7, 8]
    assert referencias(FUENTE_LIMPIA_REVISION) == []
