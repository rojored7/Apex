"""El SQL literal de `app/modules` y `app/core` es constante (S3-B1; E6, S3-D56, L-4, S608).

Regla (E6): todo argumento posicional de `text(`, `literal_column(` y `exec_driver_sql(` es un
`ast.Constant` de tipo `str` (la concatenación implícita de literales ya es una sola constante) o
un `Name` que resuelve a una constante de módulo de tipo `str` en el mismo archivo. Se rechaza
cualquier cadena construida en tiempo de ejecución: f-string (`JoinedStr`), `BinOp` con `%` o `+`,
`.format(...)` o un nombre que no es una constante de módulo. Los valores viajan como parámetros
ligados (`:id`). `execute(<sentencia ORM o Core>)` no se inspecciona.

La misma prueba fija las llaves de los candados asesores fijos (`AUDIT_CHAIN_LOCK_KEY ==
4_270_002`, `MIGRATION_LOCK_KEY == 4_270_001`) y que el candado del socio (`core/locks.py`) usa
`hashtextextended` en SQL (S3-D54), para que ninguna llave nueva choque con ellas.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.core.audit import AUDIT_CHAIN_LOCK_KEY
from app.core.db import MIGRATION_LOCK_KEY
from app.core.locks import MEMBER_LOCK_SQL

SRC = Path(__file__).resolve().parents[2] / "src"
RAICES = (SRC / "app" / "modules", SRC / "app" / "core")
FUNCIONES_SQL = frozenset({"text", "literal_column", "exec_driver_sql"})


def _constantes_de_modulo(arbol: ast.Module) -> set[str]:
    """Nombres asignados una vez en el nivel del módulo a una cadena literal."""
    nombres: set[str] = set()
    for nodo in arbol.body:
        objetivo: ast.expr | None = None
        valor: ast.expr | None = None
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1:
            objetivo, valor = nodo.targets[0], nodo.value
        elif isinstance(nodo, ast.AnnAssign) and nodo.value is not None:
            objetivo, valor = nodo.target, nodo.value
        if (
            isinstance(objetivo, ast.Name)
            and isinstance(valor, ast.Constant)
            and isinstance(valor.value, str)
        ):
            nombres.add(objetivo.id)
    return nombres


def _llamada_sql(nodo: ast.Call) -> str | None:
    if isinstance(nodo.func, ast.Name) and nodo.func.id in FUNCIONES_SQL:
        return nodo.func.id
    if isinstance(nodo.func, ast.Attribute) and nodo.func.attr in FUNCIONES_SQL:
        return nodo.func.attr
    return None


def _es_constante(argumento: ast.expr, constantes: set[str]) -> bool:
    if isinstance(argumento, ast.Constant):
        return isinstance(argumento.value, str)
    return isinstance(argumento, ast.Name) and argumento.id in constantes


def hallazgos(fuente: str, archivo: str) -> list[str]:
    """`archivo:línea: función` por cada SQL literal construido dinámicamente."""
    arbol = ast.parse(fuente, filename=archivo)
    constantes = _constantes_de_modulo(arbol)
    salida: list[str] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        funcion = _llamada_sql(nodo)
        if funcion is None or not nodo.args:
            continue
        if not _es_constante(nodo.args[0], constantes):
            salida.append(f"{archivo}:{nodo.lineno}: {funcion}")
    return salida


def test_hay_llamadas_sql_que_revisar() -> None:
    total = sum(
        1
        for raiz in RAICES
        for path in raiz.rglob("*.py")
        for nodo in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(nodo, ast.Call) and _llamada_sql(nodo)
    )
    assert total > 10


def test_ningun_sql_literal_se_construye_en_tiempo_de_ejecucion() -> None:
    encontrados = [
        h
        for raiz in RAICES
        for path in sorted(raiz.rglob("*.py"))
        for h in hallazgos(path.read_text(encoding="utf-8"), path.relative_to(SRC).as_posix())
    ]
    assert encontrados == [], "\n".join(encontrados)


def test_las_llaves_de_los_candados_fijos_no_cambian() -> None:
    assert AUDIT_CHAIN_LOCK_KEY == 4_270_002
    assert MIGRATION_LOCK_KEY == 4_270_001


def test_el_candado_del_socio_usa_hashtextextended_con_parametro_ligado() -> None:
    fuente = (SRC / "app" / "core" / "locks.py").read_text(encoding="utf-8")
    assert "hashtextextended" in fuente
    assert "hashtextextended(:m, :ns)" in MEMBER_LOCK_SQL  # PL2 de Fase 4: semilla ligada
    assert hallazgos(fuente, "app/core/locks.py") == []


# Controles con fuentes falsas ----------------------------------------------------------------

MALA = """
SQL = "SELECT 1"
def f(tabla, n):
    text(f"SELECT * FROM {tabla}")
    text("SELECT * FROM " + tabla)
    text("SELECT * FROM %s" % tabla)
    text("SELECT * FROM {}".format(tabla))
    literal_column(n)
    conn.exec_driver_sql(f"SET lock_timeout = {n}")
    sa.text(SQL + " WHERE x")
"""

BUENA = """
SQL = "SELECT pg_advisory_xact_lock(hashtextextended(:m, 0))"
TIPADA: Final = "SELECT 1"
def f(session, m):
    session.execute(text(SQL), {"m": m})
    session.execute(text(TIPADA))
    session.execute(text("SELECT id FROM plans.plans WHERE id = :id"), {"id": m})
    session.execute(select(Plan).where(Plan.id == m))
    literal_column("daterange(start_date, end_date, '[]')")
    sa.text("deleted_at IS NULL")
    texto = "no es una llamada"
"""


def test_la_fuente_mala_da_un_hallazgo_por_cada_construccion_dinamica() -> None:
    assert [h.rsplit(": ", 1)[1] for h in hallazgos(MALA, "mala.py")] == [
        "text",
        "text",
        "text",
        "text",
        "literal_column",
        "exec_driver_sql",
        "text",
    ]


def test_la_fuente_buena_pasa() -> None:
    assert hallazgos(BUENA, "buena.py") == []
