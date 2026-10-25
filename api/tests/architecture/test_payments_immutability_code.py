"""El código de `payments` no borra ni reescribe pagos (S3-B4, US-096; blueprint sección 7; regla de
datos 5, D13).

Por AST sobre `src/app/modules/payments/*.py`:
- ninguna llamada `session.delete(...)` (ni `.delete(` sobre ningún objeto), `delete(Payment)` ni
  `update(Payment)` (sentencias Core de SQLAlchemy);
- ninguna cadena contiene `TRUNCATE` ni `DELETE FROM` / `UPDATE ... payments.payments` (SQL crudo);
- las cuatro columnas de anulación (`voided`, `void_reason`, `voided_by`, `voided_at`) solo se
  asignan como atributo (`pago.voided = ...`) dentro de la función `void` (B5); en B4 `void` no
  existe: cero asignaciones;
- ninguna de las 10 columnas protegidas (`id`, `membership_id`, `member_id`, `amount_cop`,
  `method`, `reference`, `paid_at`, `registered_by`, `created_at`, `created_by`) se asigna como
  atributo en ningún sitio: se fijan una sola vez al construir el `Payment` (con argumentos con
  nombre, que no son asignaciones).
El trigger de `0011` es la red en la base (`tests/payments/test_immutability.py`); esta prueba
evita que el api intente lo que el trigger rechazaría.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

PAYMENTS = Path(__file__).resolve().parents[2] / "src" / "app" / "modules" / "payments"
PROTEGIDAS = frozenset(
    {
        "id",
        "membership_id",
        "member_id",
        "amount_cop",
        "method",
        "reference",
        "paid_at",
        "registered_by",
        "created_at",
        "created_by",
    }
)
DE_ANULACION = frozenset({"voided", "void_reason", "voided_by", "voided_at"})
FUNCION_DE_ANULAR = "void"
SQL_PROHIBIDO = (
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    re.compile(r"\bUPDATE\s+payments\.payments\b", re.IGNORECASE),
)


def _nombre_llamado(nodo: ast.Call) -> str | None:
    if isinstance(nodo.func, ast.Name):
        return nodo.func.id
    if isinstance(nodo.func, ast.Attribute):
        return nodo.func.attr
    return None


def borrados_y_reescrituras(fuente: str) -> list[str]:
    """`línea: motivo` por cada `.delete(`, `delete(Payment)`, `update(Payment)` o cadena SQL
    prohibida."""
    salida: list[str] = []
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Call):
            nombre = _nombre_llamado(nodo)
            argumentos = {a.id for a in nodo.args if isinstance(a, ast.Name)}
            if isinstance(nodo.func, ast.Attribute) and nombre == "delete":
                salida.append(f"{nodo.lineno}: .delete(")
            elif nombre in {"delete", "update"} and "Payment" in argumentos:
                salida.append(f"{nodo.lineno}: {nombre}(Payment)")
        elif isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            if any(patron.search(nodo.value) for patron in SQL_PROHIBIDO):
                salida.append(f"{nodo.lineno}: SQL")
    return sorted(salida, key=lambda hallazgo: int(hallazgo.split(":")[0]))


def asignaciones(fuente: str) -> list[tuple[str, str, int]]:
    """`(función, atributo, línea)` de cada asignación `x.<atributo> = ...` (también `+=` y con
    anotación) a una columna de `Payment`; `función` es `<módulo>` fuera de toda función."""
    salida: list[tuple[str, str, int]] = []
    columnas = PROTEGIDAS | DE_ANULACION

    def objetivos(nodo: ast.AST) -> list[ast.expr]:
        if isinstance(nodo, ast.Assign):
            return list(nodo.targets)
        if isinstance(nodo, ast.AugAssign | ast.AnnAssign):
            return [nodo.target]
        return []

    def visitar(nodo: ast.AST, funcion: str) -> None:
        for hijo in ast.iter_child_nodes(nodo):
            actual = (
                hijo.name if isinstance(hijo, ast.FunctionDef | ast.AsyncFunctionDef) else funcion
            )
            for objetivo in objetivos(hijo):
                for elemento in ast.walk(objetivo):
                    if isinstance(elemento, ast.Attribute) and elemento.attr in columnas:
                        salida.append((actual, elemento.attr, elemento.lineno))
            visitar(hijo, actual)

    visitar(ast.parse(fuente), "<módulo>")
    return salida


def _archivos() -> list[Path]:
    return sorted(PAYMENTS.glob("*.py"))


def test_hay_archivos_que_revisar() -> None:
    assert {"service.py", "rules.py", "router.py", "models.py"} <= {p.name for p in _archivos()}


def test_payments_no_borra_ni_reescribe_pagos() -> None:
    hallados = {
        path.name: encontrados
        for path in _archivos()
        if (encontrados := borrados_y_reescrituras(path.read_text(encoding="utf-8")))
    }
    assert hallados == {}


def test_las_columnas_de_anulacion_solo_se_asignan_dentro_de_void() -> None:
    fuera = {
        path.name: [
            (funcion, atributo, linea)
            for funcion, atributo, linea in asignaciones(path.read_text(encoding="utf-8"))
            if atributo in DE_ANULACION and funcion != FUNCION_DE_ANULAR
        ]
        for path in _archivos()
    }
    assert {nombre: hallado for nombre, hallado in fuera.items() if hallado} == {}


def test_ninguna_columna_protegida_se_asigna_despues_de_construir_el_pago() -> None:
    asignadas = {
        path.name: [
            (funcion, atributo, linea)
            for funcion, atributo, linea in asignaciones(path.read_text(encoding="utf-8"))
            if atributo in PROTEGIDAS
        ]
        for path in _archivos()
    }
    assert {nombre: hallado for nombre, hallado in asignadas.items() if hallado} == {}


# Controles con fuentes falsas ---------------------------------------------------------------------

FUENTE = """
SQL = "TRUNCATE payments.payments"
OTRA = "DELETE FROM payments.payments WHERE id = :id"
async def borrar(session, pago):
    await session.delete(pago)
    await session.execute(delete(Payment).where(Payment.id == pago.id))
    await session.execute(update(Payment).values(amount_cop=1))
    pago.amount_cop = 1
    pago.voided = True
async def void(session, pago):
    pago.voided = True
    pago.void_reason: str = "x"
    pago.voided_by = actor
    pago.voided_at = ahora
    pago.paid_at += delta
def crear():
    return Payment(amount_cop=1, voided=False)
"""


def test_el_analizador_detecta_lo_prohibido_y_acepta_la_construccion() -> None:
    assert borrados_y_reescrituras(FUENTE) == [
        "2: SQL",
        "3: SQL",
        "5: .delete(",
        "6: delete(Payment)",
        "7: update(Payment)",
    ]
    assert sorted(asignaciones(FUENTE), key=lambda a: a[2]) == [
        ("borrar", "amount_cop", 8),
        ("borrar", "voided", 9),
        ("void", "voided", 11),
        ("void", "void_reason", 12),
        ("void", "voided_by", 13),
        ("void", "voided_at", 14),
        ("void", "paid_at", 15),
    ]
