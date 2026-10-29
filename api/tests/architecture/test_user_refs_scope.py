"""`user_refs_for` (con correo) solo lo usa `audit` (S4A-B4; S4A-D54, L-3; S4A-D19).

`auth.service` publica dos lecturas de quién actuó: `user_names_for` (solo `display_name`, para
`members` y `dashboard`, que ve el coach) y `user_refs_for` (`UserRef` con el correo, para el admin
en `audit`). Por AST, sobre todo el árbol de cada archivo (también dentro de funciones):
- `app/modules/members/**` y `app/modules/dashboard/**` (cuando exista) no nombran
  `user_refs_for` (llamada, atributo, `from ... import` o `importlib.import_module`) ni `UserRef`;
  sin `UserRef` no pueden leer su `.email`;
- fuera de `auth`, el único módulo que nombra `user_refs_for` es `audit` (su lista y detalle lo
  usan desde S4A-B4);
- S4A-B5: `audit/queries.py::member_history` (el historial del socio que sirve `members`) usa
  `user_names_for` y no `user_refs_for` ni `UserRef`.
Los controles (fuentes falsas) prueban que el detector ve cada forma.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import app

MODULES_DIR = Path(app.__file__).resolve().parent / "modules"
VIGILADOS: Final = ("members", "dashboard")
PROHIBIDOS: Final[frozenset[str]] = frozenset({"user_refs_for", "UserRef"})


def nombres_prohibidos(fuente: str, prohibidos: frozenset[str] = PROHIBIDOS) -> list[str]:
    """`"<nombre>:<línea>"` por cada mención de un nombre prohibido en el árbol de `fuente`."""
    hallados: list[str] = []
    for nodo in ast.walk(ast.parse(fuente)):
        nombres: list[str] = []
        if isinstance(nodo, ast.Name):
            nombres.append(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            nombres.append(nodo.attr)
        elif isinstance(nodo, ast.ImportFrom | ast.Import):
            for alias in nodo.names:
                nombres.extend([alias.name, *alias.name.split(".")])
        elif (
            isinstance(nodo, ast.Call)
            and nodo.args
            and isinstance(nodo.args[0], ast.Constant)
            and isinstance(nodo.args[0].value, str)
        ):
            nombres.extend(nodo.args[0].value.split("."))
        hallados.extend(
            f"{n}:{getattr(nodo, 'lineno', 0)}" for n in dict.fromkeys(nombres) if n in prohibidos
        )
    return hallados


def _archivos(modulo: str) -> list[Path]:
    carpeta = MODULES_DIR / modulo
    return sorted(carpeta.rglob("*.py")) if carpeta.is_dir() else []


def test_members_y_dashboard_no_usan_user_refs_for_ni_user_ref() -> None:
    violaciones = [
        f"{archivo.relative_to(MODULES_DIR)}: {hallado}"
        for modulo in VIGILADOS
        for archivo in _archivos(modulo)
        for hallado in nombres_prohibidos(archivo.read_text(encoding="utf-8"))
    ]
    assert _archivos("members"), "no se encontró app/modules/members: la prueba no revisaría nada"
    assert violaciones == [], "\n".join(violaciones)


def test_fuera_de_auth_solo_audit_usa_user_refs_for() -> None:
    usuarios = {
        carpeta.name
        for carpeta in sorted(MODULES_DIR.iterdir())
        if carpeta.is_dir() and carpeta.name != "auth"
        for archivo in _archivos(carpeta.name)
        if nombres_prohibidos(archivo.read_text(encoding="utf-8"), frozenset({"user_refs_for"}))
    }
    assert usuarios == {"audit"}


def _funcion(fuente: str, nombre: str) -> ast.AsyncFunctionDef | ast.FunctionDef | None:
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.AsyncFunctionDef | ast.FunctionDef) and nodo.name == nombre:
            return nodo
    return None


def _nombra(nodo: ast.AST, nombre: str) -> bool:
    return any(
        (isinstance(n, ast.Name) and n.id == nombre)
        or (isinstance(n, ast.Attribute) and n.attr == nombre)
        for n in ast.walk(nodo)
    )


def test_el_historial_del_socio_usa_user_names_for_y_no_user_refs_for() -> None:
    """S4A-B5 (S4A-D20, S4A-D54, L-3): el historial que sirve `members` (lo ve el coach) toma los
    nombres de `user_names_for` en `audit/queries.py::member_history`, nunca `user_refs_for` ni
    `UserRef` (con el correo). `members` delega sin tocar ninguno de los dos."""
    fuente = (MODULES_DIR / "audit" / "queries.py").read_text(encoding="utf-8")
    funcion = _funcion(fuente, "member_history")
    assert funcion is not None, "audit/queries.py sin member_history"
    assert _nombra(funcion, "user_names_for"), "member_history debe usar user_names_for"
    assert not _nombra(funcion, "user_refs_for")
    assert not _nombra(funcion, "UserRef")
    servicio = (MODULES_DIR / "members" / "service.py").read_text(encoding="utf-8")
    assert nombres_prohibidos(servicio) == []


# Controles del detector --------------------------------------------------------------------

FUENTE_MALA = """
from app.modules.auth.service import user_refs_for
from app.modules.auth.schemas import UserRef
from app.modules.auth import service as auth_service

async def f(session, ids):
    refs = await auth_service.user_refs_for(session, ids)
    import importlib
    importlib.import_module("app.modules.auth.service").user_refs_for
    return [r.email for r in refs.values()]
"""

FUENTE_BUENA = """
from app.modules.auth import service as auth_service

async def f(session, ids, socio):
    nombres = await auth_service.user_names_for(session, ids)
    return nombres, socio.email
"""


def test_el_detector_ve_imports_atributos_y_llamadas() -> None:
    hallados = {h.split(":")[0] for h in nombres_prohibidos(FUENTE_MALA)}
    assert hallados == {"user_refs_for", "UserRef"}
    assert len(nombres_prohibidos(FUENTE_MALA)) >= 4


def test_el_detector_no_marca_user_names_for_ni_el_email_de_un_socio() -> None:
    assert nombres_prohibidos(FUENTE_BUENA) == []
