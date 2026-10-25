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

S3-B7 (S3-D53, E11, E13): la lista exacta se amplía con los handlers de invalidación de la caché
del resumen (`memberships/summary.py::_mark_summary_dirty`; en `queries.py` hasta S3-D90), que
solo marcan `session.info` (sin `await`, sin candados, sin otro uso de la sesión), y con la lista
exacta de suscriptores de los eventos que cambian el resumen.
"""

from __future__ import annotations

import ast
from pathlib import Path

LIFECYCLE = (
    Path(__file__).resolve().parents[2] / "src" / "app" / "modules" / "memberships" / "lifecycle.py"
)
HANDLERS_ESPERADOS: frozenset[str] = frozenset({"on_payment_registered", "on_payment_voided"})
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


def test_on_payment_voided_solo_bloquea_la_fila_del_evento() -> None:
    """S3-B5 (D13, H-3 punto 3): el handler vuelve a pedir la fila que el gate de `void` ya
    bloqueó, exactamente una vez y con el id del evento; ningún otro candado (ni el del socio, ni
    `FOR UPDATE` del pago)."""
    fuente = LIFECYCLE.read_text(encoding="utf-8")
    funcion = next(
        n
        for n in ast.parse(fuente).body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_payment_voided"
    )
    evento = _primer_parametro(funcion)
    sesion = funcion.args.args[1].arg if len(funcion.args.args) > 1 else None
    assert candados_del_handler(fuente, "on_payment_voided") == [
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


# Handlers de invalidación de la caché del resumen (S3-B7; S3-D53, E11, E13) -------------------
#
# `memberships/summary.py` (S3-D90) define los handlers `_mark_*` que el `service.py` suscribe a
# los eventos que cambian el resumen. Lista exacta: `_mark_summary_dirty`. No piden candados, no
# esperan nada (`await`) y solo tocan la sesión por `session.info` (la marca que el listener de
# `after_commit` lee después del commit real). Además, los suscriptores de esos siete eventos
# son exactamente los de la tabla `SUSCRIPTORES_ESPERADOS` (L5 de la revisión de B1: todo
# suscriptor nuevo de `MembershipSold` y compañía entra aquí con nombre).

QUERIES = LIFECYCLE.parent / "summary.py"  # S3-D90: el resumen salió de `queries.py`
HANDLERS_DE_CACHE: frozenset[str] = frozenset({"_mark_summary_dirty"})
MARCA = "app.modules.memberships.summary._mark_summary_dirty"
SUSCRIPTORES_ESPERADOS: dict[str, list[str]] = {
    "MembershipSold": [MARCA],
    "MembershipActivated": [MARCA],
    "MembershipActivationReverted": [MARCA],
    "MembershipFrozen": [MARCA],
    "MembershipCancelled": [MARCA],
    "PaymentRegistered": ["app.modules.memberships.lifecycle.on_payment_registered", MARCA],
    "PaymentVoided": ["app.modules.memberships.lifecycle.on_payment_voided", MARCA],
    # Fase 4 del Sprint 3 (M1, PM1; S3-D89; cierra B7 LOW-1): baja y reactivación del socio.
    "MemberDeactivated": [MARCA],
    "MemberReactivated": [MARCA],
}


def handlers_de_cache(fuente: str) -> list[str]:
    return sorted(
        n.name
        for n in ast.parse(fuente).body
        if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef) and n.name.startswith("_mark_")
    )


def _segundo_parametro(funcion: ast.AsyncFunctionDef | ast.FunctionDef) -> str | None:
    return funcion.args.args[1].arg if len(funcion.args.args) > 1 else None


def violaciones_de_cache(fuente: str) -> list[str]:
    """`handler:línea: motivo` por cada uso de la sesión distinto de `session.info`, cada `await`
    y cada llamada de candado en un handler `_mark_*`."""
    salida: list[str] = []
    for funcion in ast.parse(fuente).body:
        if not (
            isinstance(funcion, ast.AsyncFunctionDef | ast.FunctionDef)
            and funcion.name.startswith("_mark_")
        ):
            continue
        sesion = _segundo_parametro(funcion)
        info = {
            id(n.value)
            for n in ast.walk(funcion)
            if isinstance(n, ast.Attribute) and n.attr == "info" and isinstance(n.value, ast.Name)
        }
        for nodo in ast.walk(funcion):
            if isinstance(nodo, ast.Await):
                salida.append(f"{funcion.name}:{nodo.lineno}: await")
            elif isinstance(nodo, ast.Name) and nodo.id == sesion and id(nodo) not in info:
                salida.append(f"{funcion.name}:{nodo.lineno}: usa la sesión fuera de info")
            elif isinstance(nodo, ast.Call) and _nombre_llamado(nodo) in {
                "lock_member",
                "lock_membership",
                "with_for_update",
            }:
                salida.append(f"{funcion.name}:{nodo.lineno}: candado")
    return salida


def test_los_handlers_de_cache_son_exactamente_los_del_slice() -> None:
    assert handlers_de_cache(QUERIES.read_text(encoding="utf-8")) == sorted(HANDLERS_DE_CACHE)


def test_los_handlers_de_cache_solo_tocan_session_info() -> None:
    assert violaciones_de_cache(QUERIES.read_text(encoding="utf-8")) == []


def test_los_suscriptores_de_los_eventos_del_resumen_son_exactamente_los_esperados() -> None:
    from app.core import events
    from app.modules.members import service as members_service
    from app.modules.memberships import service as memberships_service
    from app.modules.payments import service as payments_service

    tipos = {
        **{n: getattr(memberships_service, n) for n in list(SUSCRIPTORES_ESPERADOS)[:5]},
        "PaymentRegistered": payments_service.PaymentRegistered,
        "PaymentVoided": payments_service.PaymentVoided,
        "MemberDeactivated": members_service.MemberDeactivated,
        "MemberReactivated": members_service.MemberReactivated,
    }
    obtenidos = {
        nombre: [f"{h.__module__}.{h.__qualname__}" for h in events.subscribers_for(tipo)]
        for nombre, tipo in tipos.items()
    }
    assert obtenidos == SUSCRIPTORES_ESPERADOS


FUENTE_CACHE = """
async def _mark_summary_dirty(event, session):
    session.info["apex.summary_dirty"] = True

async def _mark_mal(event, session):
    await session.execute(select(1))
    session.flush
    await lock_membership(session, event.membership_id)

def no_es_handler(session):
    session.execute(1)
"""


def test_el_analizador_de_cache_ve_los_handlers_y_sus_usos() -> None:
    assert handlers_de_cache(FUENTE_CACHE) == ["_mark_mal", "_mark_summary_dirty"]
    assert sorted(violaciones_de_cache(FUENTE_CACHE)) == sorted(
        [
            "_mark_mal:6: await",
            "_mark_mal:6: usa la sesión fuera de info",
            "_mark_mal:7: usa la sesión fuera de info",
            "_mark_mal:8: await",
            "_mark_mal:8: candado",
            "_mark_mal:8: usa la sesión fuera de info",
        ]
    )
