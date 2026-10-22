"""Grafo de imports entre los `service.py` de los módulos (S2-D53; CLAUDE.md, reglas de
módulos 2 bis y 3; G-03 y G-04).

- Nodo: cada módulo `app/modules/<m>/`. Arista `a → b`: algún archivo de `a` importa
  `app.modules.b.service` (en cualquier forma: `import`, `from ... import service`, relativo,
  dentro de una función o `importlib.import_module("...")` literal). Desde la revisión Python
  H1 se revisan todos los archivos del módulo, no solo `service.py`: el de auth se partió en
  `sessions.py`, `users.py` y `links.py`, y la arista `auth → settings` vive en `users.py`.
- El grafo es acíclico. El sentido minoritario de una dependencia mutua usa un puerto que el
  dueño registra al arrancar, o un import perezoso de la lista blanca.
- Aristas permitidas en v0.1 (mapa de contextos): `audit → auth` y `auth → settings`
  (`GET /auth/me` lee `settings.service.gym_name`, S2-D14). Una arista nueva se agrega aquí con
  su decisión.
- Import perezoso (dentro de una función) de otro service: solo los pares de
  `LAZY_IMPORT_WHITELIST`, vacía hasta el Sprint 3 (`memberships ↔ payments`, ...).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import app

MODULES_DIR: Final = Path(app.__file__).resolve().parent / "modules"
PREFIX: Final = "app.modules."
ALLOWED_EDGES: Final[frozenset[tuple[str, str]]] = frozenset(
    {("audit", "auth"), ("auth", "settings")}
)
LAZY_IMPORT_WHITELIST: Final[frozenset[tuple[str, str]]] = frozenset()


def _destino(nombre: str) -> str | None:
    """`app.modules.<b>.service[...]` → `b`; cualquier otra cosa → `None`."""
    if not nombre.startswith(PREFIX):
        return None
    partes = nombre[len(PREFIX) :].split(".")
    if len(partes) >= 2 and partes[1] == "service":
        return partes[0]
    return None


def _nombres(nodo: ast.AST, modulo: str) -> list[str]:
    if isinstance(nodo, ast.Import):
        return [alias.name for alias in nodo.names]
    if isinstance(nodo, ast.ImportFrom):
        if nodo.level:
            # Dentro de `app/modules/<m>/service.py`: nivel 1 es el paquete del módulo y
            # nivel 2 es `app.modules`.
            base = {1: f"{PREFIX}{modulo}", 2: PREFIX.rstrip(".")}.get(nodo.level, "")
            origen = f"{base}.{nodo.module}" if nodo.module else base
        else:
            origen = nodo.module or ""
        return [origen, *(f"{origen}.{alias.name}" for alias in nodo.names)]
    if (
        isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and nodo.func.attr == "import_module"
        and nodo.args
        and isinstance(nodo.args[0], ast.Constant)
        and isinstance(nodo.args[0].value, str)
    ):
        return [nodo.args[0].value]
    return []


def service_edges(fuente: str, modulo: str) -> tuple[set[str], set[str]]:
    """`(arriba, perezosas)`: services ajenos importados a nivel de módulo y dentro de
    funciones."""
    arbol = ast.parse(fuente)
    arriba: set[str] = set()
    perezosas: set[str] = set()

    def visitar(nodo: ast.AST, dentro_de_funcion: bool) -> None:
        for hijo in ast.iter_child_nodes(nodo):
            en_funcion = dentro_de_funcion or isinstance(
                hijo, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
            )
            for nombre in _nombres(hijo, modulo):
                destino = _destino(nombre)
                if destino is not None and destino != modulo:
                    (perezosas if en_funcion else arriba).add(destino)
            visitar(hijo, en_funcion)

    visitar(arbol, False)
    return arriba, perezosas


def find_cycle(grafo: dict[str, set[str]]) -> list[str] | None:
    """Un ciclo del grafo dirigido (lista de nodos con el primero repetido al final) o `None`."""
    estado: dict[str, int] = {}  # 1 = en la pila, 2 = terminado
    pila: list[str] = []

    def dfs(nodo: str) -> list[str] | None:
        estado[nodo] = 1
        pila.append(nodo)
        for vecino in sorted(grafo.get(nodo, set())):
            if estado.get(vecino) == 1:
                return [*pila[pila.index(vecino) :], vecino]
            if vecino not in estado:
                ciclo = dfs(vecino)
                if ciclo:
                    return ciclo
        pila.pop()
        estado[nodo] = 2
        return None

    for nodo in sorted(grafo):
        if nodo not in estado:
            ciclo = dfs(nodo)
            if ciclo:
                return ciclo
    return None


def _grafo_real() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    grafo: dict[str, set[str]] = {}
    perezosas: dict[str, set[str]] = {}
    for servicio in sorted(MODULES_DIR.glob("*/service.py")):
        modulo = servicio.parent.name
        grafo[modulo], perezosas[modulo] = set(), set()
        for archivo in sorted(servicio.parent.glob("*.py")):
            arriba, lazy = service_edges(archivo.read_text(encoding="utf-8"), modulo)
            grafo[modulo] |= arriba | lazy
            perezosas[modulo] |= lazy
    return grafo, perezosas


def test_hay_services_que_revisar() -> None:
    grafo, _ = _grafo_real()
    assert {"auth", "settings", "members", "plans"} <= set(grafo)


def test_las_aristas_del_mapa_se_ven_tras_partir_auth() -> None:
    """Control (revisión Python H1): `auth → settings` está en `users.py`, no en `service.py`;
    si el grafo mirara solo `service.py` la arista desaparecería sin que nada fallara."""
    grafo, _ = _grafo_real()
    assert "settings" in grafo["auth"]
    assert "auth" in grafo["audit"]


def test_plans_no_agrega_aristas() -> None:
    """S2-B9: `plans` no importa ningún service ajeno ni nadie importa el suyo todavía (lo hará
    `memberships` en el Sprint 3, con su decisión)."""
    grafo, _ = _grafo_real()
    assert grafo["plans"] == set()
    assert [a for a, destinos in grafo.items() if "plans" in destinos] == []


def test_el_grafo_de_services_es_aciclico() -> None:
    grafo, _ = _grafo_real()
    assert find_cycle(grafo) is None, f"ciclo entre services: {find_cycle(grafo)}"


def test_solo_existen_las_aristas_del_mapa_de_contextos() -> None:
    grafo, _ = _grafo_real()
    aristas = {(a, b) for a, destinos in grafo.items() for b in destinos}
    sobrantes = sorted(aristas - ALLOWED_EDGES)
    assert sobrantes == [], f"aristas sin decisión: {sobrantes}"


def test_ningun_import_perezoso_fuera_de_la_lista_blanca() -> None:
    _, perezosas = _grafo_real()
    fuera = sorted((a, b) for a, destinos in perezosas.items() for b in destinos)
    fuera = [par for par in fuera if par not in LAZY_IMPORT_WHITELIST]
    assert fuera == [], f"imports perezosos de otro service sin lista blanca: {fuera}"
    assert frozenset() == LAZY_IMPORT_WHITELIST  # vacía hasta el Sprint 3 (S2-D53)


# Controles del analizador ------------------------------------------------------------------


def test_el_analizador_ve_todas_las_formas_de_import() -> None:
    fuente = (
        "from app.modules.settings import service as settings_service\n"
        "import app.modules.plans.service\n"
        "from ..members import service\n"
        "from app.modules.auth.schemas import UserOut\n"
        "from . import rules\n"
        "def f():\n"
        "    from app.modules.payments.service import payability\n"
        "    import importlib\n"
        "    importlib.import_module('app.modules.classes.service')\n"
    )
    arriba, perezosas = service_edges(fuente, "auth")
    assert arriba == {"settings", "plans", "members"}
    assert perezosas == {"payments", "classes"}


def test_el_propio_service_no_es_arista() -> None:
    arriba, perezosas = service_edges("from app.modules.auth import service\n", "auth")
    assert arriba == set() and perezosas == set()


def test_find_cycle_detecta_un_ciclo_y_acepta_un_dag() -> None:
    assert find_cycle({"audit": {"auth"}, "auth": {"settings"}, "settings": set()}) is None
    ciclo = find_cycle({"a": {"b"}, "b": {"c"}, "c": {"a"}})
    assert ciclo is not None and ciclo[0] == ciclo[-1] and set(ciclo) == {"a", "b", "c"}
    assert find_cycle({"a": {"a"}}) == ["a", "a"]
