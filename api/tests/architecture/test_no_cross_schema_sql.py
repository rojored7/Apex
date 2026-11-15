"""Ningún SQL literal de un módulo nombra tablas del esquema de otro módulo (S3-B7, US-091; regla
de módulos 2, G-04, blueprint sección 7).

Por `ast`, en `app/modules/<modulo>/*.py` salvo `audit` (que lee la cadena de auditoría de todos):
cada cadena literal que se pasa a `text(...)`, `literal_column(...)` o `exec_driver_sql(...)`, y
toda cadena literal que contenga `FROM` o `JOIN` (en mayúsculas, como se escribe el SQL del
proyecto), no nombra `<esquema>.<tabla>` de otro esquema de módulo (`members`, `plans`,
`memberships`, `payments`, `auth`, `settings`). El esquema propio sí: el de un módulo es su
nombre. La resolución de nombres y estados entre módulos va por el `service.py` del dueño (por
ejemplo `members.service.names_for`, `payments.service.sums_not_voided`), nunca por un `JOIN`.
S7-C4c (M-1): tampoco se declara una tabla de otro esquema con `table("t", schema="otro")`
(o `Table`): `auth/kiosk.py` leía `classes.class_sessions` así, sin SQL literal.
Control con fuentes falsas: una cadena con `FROM members.members` en `memberships` falla; la
misma en `members`, o un `select(...)` del ORM, pasa.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

MODULES = Path(__file__).resolve().parents[2] / "src" / "app" / "modules"
# S7-D19 (S7-W0-4): `classes` entra ya; su módulo llega en A2 (S7-A2).
ESQUEMAS = (
    "members",
    "plans",
    "memberships",
    "payments",
    "auth",
    "settings",
    "notifications",
    "classes",
    "attachments",
    "wods",  # S8-W0-3: sus módulos llegan en A1 y B1
    "results",
)
# `classes` ya existe desde S7-A2; `wods` llega en S8-A1 y `results` en S8-B1 (cada slice lo saca).
MODULOS_PENDIENTES: frozenset[str] = frozenset({"wods", "results"})
EXCLUIDOS = frozenset({"audit"})
FUNCIONES_SQL = frozenset({"text", "literal_column", "exec_driver_sql"})
_SQL = re.compile(r"\b(FROM|JOIN)\b", re.IGNORECASE)
_TABLA = re.compile(r"(?<![\w.])(" + "|".join(ESQUEMAS) + r")\.([a-z_][a-z0-9_]*)", re.IGNORECASE)


def _nombre_llamado(nodo: ast.Call) -> str | None:
    if isinstance(nodo.func, ast.Name):
        return nodo.func.id
    if isinstance(nodo.func, ast.Attribute):
        return nodo.func.attr
    return None


def _constantes(arbol: ast.AST) -> dict[str, ast.Constant]:
    """`NOMBRE = "texto"` a nivel de módulo (S7-C4d, L-3): `text(NOMBRE)` y `schema=NOMBRE`."""
    salida: dict[str, ast.Constant] = {}
    for nodo in getattr(arbol, "body", []):
        if (
            isinstance(nodo, ast.Assign)
            and len(nodo.targets) == 1
            and isinstance(nodo.targets[0], ast.Name)
            and isinstance(nodo.value, ast.Constant)
            and isinstance(nodo.value.value, str)
        ):
            salida[nodo.targets[0].id] = nodo.value
    return salida


def _docstrings(arbol: ast.AST) -> set[int]:
    """Ids de las constantes que son docstring (prosa, no SQL)."""
    salida: set[int] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            primero = nodo.body[0] if nodo.body else None
            if isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant):
                salida.add(id(primero.value))
    return salida


def _cadenas_sql(arbol: ast.AST) -> list[tuple[int, str]]:
    """`(línea, texto)` de cada cadena pasada a una función SQL (literal o constante del módulo)
    y de cada literal con FROM/JOIN (sin docstrings)."""
    salida: list[tuple[int, str]] = []
    vistos: set[int] = set()
    constantes = _constantes(arbol)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and _nombre_llamado(nodo) in FUNCIONES_SQL:
            for argumento in nodo.args[:1]:
                if isinstance(argumento, ast.Constant) and isinstance(argumento.value, str):
                    salida.append((argumento.lineno, argumento.value))
                    vistos.add(id(argumento))
                elif isinstance(argumento, ast.Name) and argumento.id in constantes:
                    definicion = constantes[argumento.id]  # se informa en la línea de la constante
                    if id(definicion) not in vistos:
                        salida.append((definicion.lineno, str(definicion.value)))
                        vistos.add(id(definicion))
    docstrings = _docstrings(arbol)
    for nodo in ast.walk(arbol):
        if (
            isinstance(nodo, ast.Constant)
            and isinstance(nodo.value, str)
            and id(nodo) not in vistos
            and id(nodo) not in docstrings
            and _SQL.search(nodo.value)
        ):
            salida.append((nodo.lineno, nodo.value))
    return salida


def _esquemas_declarados(arbol: ast.AST) -> list[tuple[int, str]]:
    """`(línea, esquema)` de cada llamada con `schema="<esquema de módulo>"` o `schema=<constante
    del módulo>` (`table`, `Table`)."""
    salida: list[tuple[int, str]] = []
    constantes = _constantes(arbol)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            for palabra in nodo.keywords:
                valor = palabra.value
                if palabra.arg != "schema":
                    continue
                if isinstance(valor, ast.Name):
                    definicion = constantes.get(valor.id)
                    texto = None if definicion is None else str(definicion.value)
                elif isinstance(valor, ast.Constant) and isinstance(valor.value, str):
                    texto = valor.value
                else:
                    texto = None
                if texto is not None and texto.lower() in ESQUEMAS:
                    salida.append((nodo.lineno, texto.lower()))
    return salida


def hallazgos(fuente: str, modulo: str, archivo: str) -> list[str]:
    """`archivo:línea: esquema.tabla` por cada tabla de otro esquema nombrada en SQL literal o
    declarada con `schema=` (en ese caso `esquema.*`; S7-C4c, M-1)."""
    salida: list[str] = []
    arbol = ast.parse(fuente, filename=archivo)
    for linea, esquema in _esquemas_declarados(arbol):
        if esquema != modulo:
            salida.append(f"{archivo}:{linea}: {esquema}.*")
    for linea, cadena in _cadenas_sql(arbol):
        for esquema, tabla in _TABLA.findall(cadena):
            if esquema.lower() != modulo:
                salida.append(f"{archivo}:{linea}: {esquema.lower()}.{tabla.lower()}")
    return salida


def _modulos() -> list[Path]:
    return sorted(d for d in MODULES.iterdir() if d.is_dir() and not d.name.startswith("_"))


def test_hay_modulos_que_revisar() -> None:
    nombres = {d.name for d in _modulos()}
    assert set(ESQUEMAS) - MODULOS_PENDIENTES <= nombres
    assert "audit" in nombres


def test_ningun_modulo_nombra_tablas_de_otro_esquema_en_sql_literal() -> None:
    encontrados = [
        h
        for modulo in _modulos()
        if modulo.name not in EXCLUIDOS
        for archivo in sorted(modulo.rglob("*.py"))
        for h in hallazgos(
            archivo.read_text(encoding="utf-8"),
            modulo.name,
            archivo.relative_to(MODULES).as_posix(),
        )
    ]
    assert encontrados == [], "\n".join(encontrados)


# Controles con fuentes falsas ----------------------------------------------------------------

MALA = """
CUENTA = "SELECT count(*) FROM members.members WHERE deleted_at IS NULL"
def f(session, ids):
    session.execute(text("SELECT m.id FROM memberships.memberships m JOIN plans.plans p ON true"))
    session.execute(text(CUENTA))
    literal_column("payments.payments.amount_cop")
    conn.exec_driver_sql("DELETE FROM auth.refresh_tokens")
"""

BUENA = """
PROPIA = "SELECT id FROM memberships.memberships WHERE member_id = :m"
def f(session, ids):
    session.execute(text(PROPIA), {"m": ids})
    session.execute(text("SELECT 1 FROM memberships.membership_freezes"))
    session.execute(select(Membership).where(Membership.member_id.in_(ids)))
    texto = "los socios viven en members.members; esto no es SQL"
"""


def test_la_fuente_mala_da_un_hallazgo_por_tabla_ajena() -> None:
    assert sorted(hallazgos(MALA, "memberships", "mala.py")) == sorted(
        [
            "mala.py:2: members.members",
            "mala.py:4: plans.plans",
            "mala.py:6: payments.payments",
            "mala.py:7: auth.refresh_tokens",
        ]
    )


def test_la_fuente_buena_pasa_y_el_esquema_propio_tambien() -> None:
    assert hallazgos(BUENA, "memberships", "buena.py") == []
    assert hallazgos(MALA, "members", "mala.py") != []
    propia = 'X = "SELECT id FROM members.members"\n'
    assert hallazgos(propia, "members", "propia.py") == []
    assert hallazgos(propia, "memberships", "ajena.py") == ["ajena.py:1: members.members"]


DECLARADA = """
from sqlalchemy import Uuid, column, table
_T = table("class_sessions", column("id", Uuid()), schema="classes")
_PROPIA = table("members", column("id", Uuid()), schema="members")
_LIBRE = table("x", column("id", Uuid()), schema="otro")
"""


def test_una_tabla_declarada_con_schema_ajeno_es_un_hallazgo() -> None:
    """S7-C4c (M-1): `table(..., schema="classes")` dentro de `auth` no lleva SQL literal."""
    assert hallazgos(DECLARADA, "auth", "kiosk.py") == [
        "kiosk.py:3: classes.*",
        "kiosk.py:4: members.*",
    ]
    assert hallazgos(DECLARADA, "classes", "q.py") == ["q.py:4: members.*"]


# S7-C4d (L-3): attachments, mayúsculas, constantes del módulo y `schema=<constante>` --------------

CONSTANTES = '''
"""Docstring: lee from members.members en prosa; no es SQL."""
ACTUALIZA = "UPDATE members.members SET first_name = :n"
BORRA = "DELETE   FROM   attachments.attachments"
ESQUEMA = "classes"
def f(session):
    session.execute(text(ACTUALIZA))
    session.execute(text(BORRA))
    session.execute(text("select id from Plans.plans"))
    return table("class_sessions", schema=ESQUEMA)
'''


def test_las_constantes_las_mayusculas_y_attachments_son_hallazgos() -> None:
    assert sorted(hallazgos(CONSTANTES, "memberships", "c.py")) == sorted(
        [
            "c.py:3: members.members",
            "c.py:4: attachments.attachments",
            "c.py:9: plans.plans",
            "c.py:10: classes.*",
        ]
    )


def test_attachments_es_un_esquema_de_modulo() -> None:
    assert "attachments" in ESQUEMAS
    assert hallazgos('X = "SELECT 1 FROM attachments.attachments"\n', "attachments", "a.py") == []
