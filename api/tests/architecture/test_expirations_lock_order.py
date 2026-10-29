"""Orden de candados y forma de las transacciones del recálculo diario (S4A-B2; S4A-D2, S4A-D57).

Por AST sobre `app/modules/memberships/expirations.py`:
- en `_apply_to_member` (el cuerpo de la transacción de un socio) la primera llamada a
  `lock_member` precede a la primera de `lock_membership`, y esta al primer `flush`; hay un solo
  `flush` (el primer toque a la cadena de auditoría va después de los dos candados: orden D3,
  socio → fila → cadena);
- `_recompute_member` llama a `_apply_to_member` dentro de un `async with ... begin()` (una
  transacción por socio);
- ningún `await asyncio.sleep(...)` (ni `sleep(...)`) dentro de un `async with` que abra
  `begin()`: las esperas de reintento van fuera de la transacción (S4A-D57);
- `_candidate_member_ids` (fase 1) se llama dentro de un `async with` que no abre `begin()` ni
  llama a la fase 2 (`_recompute_member`, `_apply_to_member`): la sesión de lectura se cierra
  antes de la fase 2 (S4A-D57).
Controles con fuentes falsas: el orden invertido, la espera dentro de la transacción y la fase 1
dentro de la fase 2 se detectan.
"""

from __future__ import annotations

import ast
from pathlib import Path

EXPIRATIONS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "app"
    / "modules"
    / "memberships"
    / "expirations.py"
)
FASE_2 = frozenset({"_recompute_member", "_apply_to_member"})


def _nombre(nodo: ast.Call) -> str | None:
    if isinstance(nodo.func, ast.Name):
        return nodo.func.id
    if isinstance(nodo.func, ast.Attribute):
        return nodo.func.attr
    return None


def _funcion(arbol: ast.AST, nombre: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.AsyncFunctionDef | ast.FunctionDef) and nodo.name == nombre:
            return nodo
    raise AssertionError(f"no existe la función {nombre}")


def _llamadas(nodo: ast.AST, nombre: str) -> list[ast.Call]:
    encontradas = [n for n in ast.walk(nodo) if isinstance(n, ast.Call) and _nombre(n) == nombre]
    return sorted(encontradas, key=lambda n: (n.lineno, n.col_offset))


def _abre_transaccion(bloque: ast.AsyncWith) -> bool:
    return any(_llamadas(item.context_expr, "begin") for item in bloque.items)


def orden_de_candados(fuente: str) -> list[str]:
    """Problemas del orden en `_apply_to_member` (lista vacía si está bien)."""
    funcion = _funcion(ast.parse(fuente), "_apply_to_member")
    socio = _llamadas(funcion, "lock_member")
    fila = _llamadas(funcion, "lock_membership")
    flush = _llamadas(funcion, "flush")
    problemas: list[str] = []
    if not socio:
        problemas.append("sin lock_member")
    if not fila:
        problemas.append("sin lock_membership")
    if len(flush) != 1:
        problemas.append(f"{len(flush)} flush (se espera uno)")
    if problemas:
        return problemas
    posicion = {
        "lock_member": (socio[0].lineno, socio[0].col_offset),
        "lock_membership": (fila[0].lineno, fila[0].col_offset),
        "flush": (flush[0].lineno, flush[0].col_offset),
    }
    if not posicion["lock_member"] < posicion["lock_membership"]:
        problemas.append("lock_membership antes de lock_member")
    if not posicion["lock_membership"] < posicion["flush"]:
        problemas.append("flush antes de lock_membership")
    return problemas


def esperas_en_transaccion(fuente: str) -> list[int]:
    """Líneas de `sleep(...)` dentro de un `async with` que abre `begin()`."""
    return sorted(
        llamada.lineno
        for bloque in ast.walk(ast.parse(fuente))
        if isinstance(bloque, ast.AsyncWith) and _abre_transaccion(bloque)
        for llamada in _llamadas(bloque, "sleep")
    )


def fase_1_mezclada(fuente: str) -> list[str]:
    """Problemas de la fase 1: llamada ausente, fuera de un `async with`, o dentro de uno que
    abre `begin()` o llama a la fase 2."""
    arbol = ast.parse(fuente)
    llamadas = _llamadas(arbol, "_candidate_member_ids")
    if not llamadas:
        return ["sin llamada a _candidate_member_ids"]
    problemas: list[str] = []
    for llamada in llamadas:
        contenedores = [
            b
            for b in ast.walk(arbol)
            if isinstance(b, ast.AsyncWith) and llamada in list(ast.walk(b))
        ]
        if not contenedores:
            problemas.append(f"{llamada.lineno}: fuera de una sesión")
        for bloque in contenedores:
            if _abre_transaccion(bloque):
                problemas.append(f"{llamada.lineno}: dentro de begin()")
            if any(_llamadas(bloque, nombre) for nombre in FASE_2):
                problemas.append(f"{llamada.lineno}: comparte sesión con la fase 2")
    return problemas


def apply_fuera_de_transaccion(fuente: str) -> bool:
    """Verdadero si `_recompute_member` llama a `_apply_to_member` fuera de `async with ...
    begin()` (o no lo llama)."""
    funcion = _funcion(ast.parse(fuente), "_recompute_member")
    dentro = [
        llamada
        for bloque in ast.walk(funcion)
        if isinstance(bloque, ast.AsyncWith) and _abre_transaccion(bloque)
        for llamada in _llamadas(bloque, "_apply_to_member")
    ]
    return not dentro or len(dentro) != len(_llamadas(funcion, "_apply_to_member"))


# Sobre el archivo real ----


def _fuente() -> str:
    assert EXPIRATIONS.is_file()
    return EXPIRATIONS.read_text(encoding="utf-8")


def test_apply_to_member_toma_socio_luego_fila_y_hace_un_solo_flush_al_final() -> None:
    assert orden_de_candados(_fuente()) == []


def test_recompute_member_aplica_dentro_de_una_transaccion_por_socio() -> None:
    assert not apply_fuera_de_transaccion(_fuente())


def test_ninguna_espera_dentro_de_una_transaccion() -> None:
    fuente = _fuente()
    assert _llamadas(ast.parse(fuente), "sleep"), "el reintento debe esperar (RETRY_DELAYS_S)"
    assert esperas_en_transaccion(fuente) == []


def test_la_fase_1_cierra_su_sesion_antes_de_la_fase_2() -> None:
    assert fase_1_mezclada(_fuente()) == []


# Controles con fuentes falsas ----

FUENTE_BIEN = """
async def recompute_statuses(session_factory, *, today):
    async with session_factory() as s:
        ids = await _candidate_member_ids(s, today, 7, None)
    for member_id in ids:
        await _recompute_member(session_factory, member_id, today, 7)

async def _recompute_member(session_factory, member_id, today, expiring_days):
    for espera in (0.5, 1.0):
        try:
            async with session_factory() as s, s.begin():
                return await _apply_to_member(s, member_id, today, expiring_days)
        except Busy:
            await asyncio.sleep(espera)

async def _apply_to_member(session, member_id, today, expiring_days):
    await lock_member(session, member_id)
    fila = await lock_membership(session, otra)
    fila.status = "expired"
    await session.flush()
"""

FUENTE_MAL = """
async def recompute_statuses(session_factory, *, today):
    async with session_factory() as s, s.begin():
        ids = await _candidate_member_ids(s, today, 7, None)
        for member_id in ids:
            await _apply_to_member(s, member_id, today, 7)

async def _recompute_member(session_factory, member_id, today, expiring_days):
    async with session_factory() as s, s.begin():
        await asyncio.sleep(0.5)
    return await _apply_to_member(s, member_id, today, expiring_days)

async def _apply_to_member(session, member_id, today, expiring_days):
    fila = await lock_membership(session, otra)
    await session.flush()
    await lock_member(session, member_id)
    await session.flush()
"""

FUENTE_INVERTIDA = """
async def _apply_to_member(session, member_id, today, expiring_days):
    fila = await lock_membership(session, otra)
    await lock_member(session, member_id)
    await session.flush()
"""

FUENTE_FLUSH_ANTES = """
async def _apply_to_member(session, member_id, today, expiring_days):
    await lock_member(session, member_id)
    await session.flush()
    fila = await lock_membership(session, otra)
"""


def test_control_la_fuente_correcta_pasa() -> None:
    assert orden_de_candados(FUENTE_BIEN) == []
    assert not apply_fuera_de_transaccion(FUENTE_BIEN)
    assert esperas_en_transaccion(FUENTE_BIEN) == []
    assert fase_1_mezclada(FUENTE_BIEN) == []


def test_control_el_orden_invertido_se_detecta() -> None:
    assert orden_de_candados(FUENTE_INVERTIDA) == ["lock_membership antes de lock_member"]
    assert orden_de_candados(FUENTE_FLUSH_ANTES) == ["flush antes de lock_membership"]
    assert orden_de_candados(FUENTE_MAL) == ["2 flush (se espera uno)"]


def test_control_espera_dentro_de_la_transaccion_y_fase_1_mezclada_se_detectan() -> None:
    assert esperas_en_transaccion(FUENTE_MAL) == [10]
    assert apply_fuera_de_transaccion(FUENTE_MAL)
    assert fase_1_mezclada(FUENTE_MAL) == [
        "4: dentro de begin()",
        "4: comparte sesión con la fase 2",
    ]
