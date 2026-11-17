"""Los handlers de `athletes` no piden candados (S9-B3; S9-D7 punto 5, S9-D42).

Por AST sobre `app/modules/athletes/derive.py`: el emisor (`results`) ya tiene `lock_member` (paso 2
de `record_result` y `void_result`), que serializa todo lo que decide «el vigente» de un socio.
Ninguna función del archivo (handler o ayuda) llama a `lock_member`, `lock_membership`,
`with_for_update` ni a un candado asesor (`pg_advisory*`); pedirlos invertiría el orden único de
candados (socio, sesión, WOD, catálogo, resultado, récord, cadena) y abriría un ciclo.

La lista de handlers es exacta y la amplía el slice que agrega uno: `on_wod_result_validated` en B3;
B5 suma `on_wod_result_superseded` y `on_wod_result_voided`. Prohibido `pytest.skip`.
"""

from __future__ import annotations

import ast
from pathlib import Path

DERIVE = Path(__file__).resolve().parents[2] / "src" / "app" / "modules" / "athletes" / "derive.py"
HANDLERS_ESPERADOS: frozenset[str] = frozenset({"on_wod_result_validated"})
LLAMADAS_PROHIBIDAS: frozenset[str] = frozenset(
    {"lock_member", "lock_membership", "with_for_update"}
)
TEXTOS_PROHIBIDOS: tuple[str, ...] = ("for update", "for share", "pg_advisory", "pg_try_advisory")


def _nombre(llamada: ast.Call) -> str | None:
    if isinstance(llamada.func, ast.Name):
        return llamada.func.id
    if isinstance(llamada.func, ast.Attribute):
        return llamada.func.attr
    return None


def handlers(fuente: str) -> list[str]:
    return sorted(
        n.name
        for n in ast.walk(ast.parse(fuente))
        if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef) and n.name.startswith("on_")
    )


def violaciones(fuente: str) -> list[str]:
    """`línea: motivo` por cada candado pedido en cualquier punto del archivo."""
    salida: list[str] = []
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Call) and _nombre(nodo) in LLAMADAS_PROHIBIDAS:
            salida.append(f"{nodo.lineno}: {_nombre(nodo)}")
        elif isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            bajo = nodo.value.lower()
            if any(t in bajo for t in TEXTOS_PROHIBIDOS) and len(bajo) < 200:
                salida.append(f"{nodo.lineno}: texto de candado")
    return sorted(salida, key=lambda s: int(s.split(":")[0]))


def test_los_handlers_de_derive_son_exactamente_los_del_slice() -> None:
    assert DERIVE.is_file()
    assert handlers(DERIVE.read_text(encoding="utf-8")) == sorted(HANDLERS_ESPERADOS)


def test_ninguna_funcion_de_derive_pide_candados() -> None:
    assert violaciones(DERIVE.read_text(encoding="utf-8")) == []


def test_athletes_service_suscribe_el_handler_de_validado() -> None:
    """S9-D7 (2): `athletes/service.py` suscribe los handlers al importarse."""
    from app.core import events
    from app.modules.athletes import service  # noqa: F401  (el import suscribe)
    from app.modules.results.events import WodResultValidated

    nombres = [
        f"{h.__module__}.{h.__qualname__}" for h in events.subscribers_for(WodResultValidated)
    ]

    assert "app.modules.athletes.derive.on_wod_result_validated" in nombres


FUENTE = """
async def on_uno(event, session):
    await lock_member(session, event.member_id)
    await session.execute(select(X).with_for_update())
    await session.execute(text("SELECT pg_advisory_xact_lock(1)"))

async def _ayuda(session):
    await lock_membership(session, 1)

async def on_limpio(event, session):
    await session.execute(select(X))
"""


def test_el_analizador_ve_los_handlers_y_los_candados() -> None:
    assert handlers(FUENTE) == ["on_limpio", "on_uno"]
    assert violaciones(FUENTE) == [
        "3: lock_member",
        "4: with_for_update",
        "5: texto de candado",
        "8: lock_membership",
    ]
