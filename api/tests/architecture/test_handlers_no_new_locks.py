"""Ningún handler suscrito pide candados que el emisor no tenga (S3-B1; S3-D43 punto 4, H-3).

Por AST sobre `app/modules/memberships/lifecycle.py` (donde viven los handlers de pagos de B4 y B5):
cada función `on_*` no llama a `lock_member` (el candado del socio lo toma el emisor antes de
cualquier flush auditado, D3), no llama a `with_for_update` directo (la fila se pide por
`lock_membership`, D-3) y, si llama a `lock_membership`, es con el id del evento
(`event.membership_id`, la fila que el emisor ya bloqueó). Romperlo abre el interbloqueo de la
exploración (riesgo 2): `register` hace flush (cadena de auditoría) y el handler pediría el socio.

La lista de handlers es exacta y se actualiza en el slice que agrega uno: vacía en B1 y en B2
(`freeze` vive en `lifecycle.py` desde B2, pero es un caso de uso que emite, no un handler: toma
el candado del socio como emisor, D3); `on_payment_registered` en B4 y `on_payment_voided` en B5.
Prohibido `pytest.skip`: con la lista vacía la prueba igual corre el análisis sobre el archivo real.
"""

from __future__ import annotations

import ast
from pathlib import Path

LIFECYCLE = (
    Path(__file__).resolve().parents[2] / "src" / "app" / "modules" / "memberships" / "lifecycle.py"
)
HANDLERS_ESPERADOS: frozenset[str] = frozenset({"on_payment_registered"})  # B5: on_payment_voided
CASOS_DE_USO_ESPERADOS: frozenset[str] = frozenset({"freeze"})  # B2; B6 agrega `cancel`


def _nombre_llamado(nodo: ast.Call) -> str | None:
    if isinstance(nodo.func, ast.Name):
        return nodo.func.id
    if isinstance(nodo.func, ast.Attribute):
        return nodo.func.attr
    return None


def _es_id_del_evento(argumento: ast.expr, evento: str | None) -> bool:
    return (
        isinstance(argumento, ast.Attribute)
        and argumento.attr == "membership_id"
        and isinstance(argumento.value, ast.Name)
        and argumento.value.id == evento
    )


def _primer_parametro(funcion: ast.AsyncFunctionDef | ast.FunctionDef) -> str | None:
    return funcion.args.args[0].arg if funcion.args.args else None


def handlers(fuente: str) -> list[str]:
    return sorted(
        n.name
        for n in ast.parse(fuente).body
        if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef) and n.name.startswith("on_")
    )


def violaciones(fuente: str) -> list[str]:
    """`handler:línea: motivo` por cada candado que un handler `on_*` no debería pedir."""
    salida: list[str] = []
    for funcion in ast.parse(fuente).body:
        if not (
            isinstance(funcion, ast.AsyncFunctionDef | ast.FunctionDef)
            and funcion.name.startswith("on_")
        ):
            continue
        evento = _primer_parametro(funcion)
        for nodo in ast.walk(funcion):
            if not isinstance(nodo, ast.Call):
                continue
            llamado = _nombre_llamado(nodo)
            if llamado == "lock_member":
                salida.append(f"{funcion.name}:{nodo.lineno}: lock_member")
            elif llamado == "with_for_update":
                salida.append(f"{funcion.name}:{nodo.lineno}: with_for_update")
            elif llamado == "lock_membership":
                argumento = nodo.args[1] if len(nodo.args) >= 2 else None
                if argumento is None or not _es_id_del_evento(argumento, evento):
                    salida.append(f"{funcion.name}:{nodo.lineno}: lock_membership con otro id")
    return sorted(salida, key=lambda h: (h.split(":")[0], int(h.split(":")[1])))


def test_los_handlers_de_lifecycle_son_exactamente_los_del_slice() -> None:
    assert handlers(LIFECYCLE.read_text(encoding="utf-8")) == sorted(HANDLERS_ESPERADOS)


def test_ningun_handler_pide_candados_nuevos() -> None:
    assert violaciones(LIFECYCLE.read_text(encoding="utf-8")) == []


def test_freeze_vive_en_lifecycle_y_no_cuenta_como_handler() -> None:
    """S3-B2: `freeze` pide `lock_member` (es el emisor de `MembershipFrozen`) y por eso no puede
    llamarse `on_*`; no cuenta entre los handlers."""
    arbol = ast.parse(LIFECYCLE.read_text(encoding="utf-8"))
    funciones = {
        n.name for n in arbol.body if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef)
    }
    assert CASOS_DE_USO_ESPERADOS <= funciones
    assert not {f for f in funciones if f.startswith("on_")} - HANDLERS_ESPERADOS


def candados_del_handler(fuente: str, nombre: str) -> list[str]:
    """Las llamadas de candado (`lock_member`, `lock_membership`, `with_for_update`) del handler
    `nombre`, como texto (`ast.unparse`), en orden de aparición."""
    funcion = next(
        n
        for n in ast.parse(fuente).body
        if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef) and n.name == nombre
    )
    llamadas = [
        n
        for n in ast.walk(funcion)
        if isinstance(n, ast.Call)
        and _nombre_llamado(n) in {"lock_member", "lock_membership", "with_for_update"}
    ]
    return [ast.unparse(n) for n in sorted(llamadas, key=lambda n: (n.lineno, n.col_offset))]


def test_on_payment_registered_solo_bloquea_la_fila_del_evento() -> None:
    """S3-B4 (D3, D11): el handler vuelve a pedir la fila que el gate de `register` ya bloqueó,
    exactamente una vez y con el id del evento; ningún otro candado."""
    fuente = LIFECYCLE.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    funcion = next(
        n
        for n in arbol.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_payment_registered"
    )
    evento = _primer_parametro(funcion)
    sesion = funcion.args.args[1].arg if len(funcion.args.args) > 1 else None
    assert candados_del_handler(fuente, "on_payment_registered") == [
        f"lock_membership({sesion}, {evento}.membership_id)"
    ]


# Controles con fuentes falsas ----------------------------------------------------------------

FUENTE = """
async def on_payment_registered(event, session):
    await lock_membership(session, event.membership_id)

async def on_payment_voided(event, session):
    await lock_member(session, event.member_id)
    await lock_membership(session, otra_id)
    await session.execute(select(Membership).with_for_update())

async def freeze(session, membership_id):
    await lock_member(session, membership_id)
"""


def test_el_analizador_ve_los_handlers_y_sus_candados() -> None:
    assert handlers(FUENTE) == ["on_payment_registered", "on_payment_voided"]
    assert violaciones(FUENTE) == [
        "on_payment_voided:6: lock_member",
        "on_payment_voided:7: lock_membership con otro id",
        "on_payment_voided:8: with_for_update",
    ]
    assert candados_del_handler(FUENTE, "on_payment_registered") == [
        "lock_membership(session, event.membership_id)"
    ]
    assert candados_del_handler(FUENTE, "on_payment_voided") == [
        "lock_member(session, event.member_id)",
        "lock_membership(session, otra_id)",
        "select(Membership).with_for_update()",
    ]
