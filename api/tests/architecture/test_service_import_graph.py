"""Grafo de imports entre los `service.py` de los módulos (S2-D53; CLAUDE.md, reglas de
módulos 2 bis y 3; G-03 y G-04; reescrita en S3-B1 por D2 del blueprint del Sprint 3).

- Nodo: cada módulo `app/modules/<m>/`. Arista `a → b`: algún archivo de `a` importa
  `app.modules.b.service` (en cualquier forma: `import`, `from ... import service`, relativo,
  dentro de una función o `importlib.import_module("...")` literal). Se revisan todos los
  archivos del módulo, no solo `service.py` (revisión Python H1: el de auth se partió y la arista
  `auth → settings` vive en `users.py`; `memberships` nace partido, D7).
- D2: las aristas de **nivel de módulo** y las **perezosas** (dentro de una función) se separan.
  El grafo acíclico se exige solo sobre las de nivel de módulo; cada perezosa se valida contra
  `LAZY_IMPORT_WHITELIST` y lleva el comentario `# lazy: G-03` en su línea o en la anterior
  (sección 0 del plan del Sprint 3).
- `ALLOWED_EDGES` (mapa de contextos) crece slice a slice con su decisión: `audit → auth`,
  `auth → settings` (S2-D14) y, desde S3-B1, `memberships → members` (`get_ref`, `names_for`),
  `memberships → plans` (`get(for_share=True)`, `names_for`) y `memberships → settings`
  (`memberships_policy`). S3-B3 agrega `payments → settings` (`memberships_policy`,
  `payment_methods`); S3-B4 `memberships → payments` (`register`, el puerto `MembershipGate`,
  `PaymentRegistered`, `sum_not_voided`); B8 `payments → members` (`search_ids`,
  `ensure_exists`) y `payments → auth` (`names_for`), donde tienen uso real (S3-D80). Cada arista
  permitida existe de verdad.
- `payments` no importa `memberships` a nivel de módulo (D1: habla con él solo por el puerto
  `MembershipGate`, que `memberships` registra al importarse); la perezosa `payments → memberships`
  (lista blanca) llega con B8. Desde B4 el par se importa limpio en los dos órdenes
  (`memberships, payments` y `payments, memberships`).
- `LAZY_IMPORT_WHITELIST` es exactamente `{payments → memberships, members → memberships,
  plans → memberships}` (G-03); hoy no se usa ninguna.
- Cada par de `ALLOWED_EDGES` se importa en un subproceso limpio (`python -I -c`) en los dos
  órdenes (DoD de US-071): un ciclo de imports al arrancar fallaría ahí aunque el análisis
  estático no lo viera.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

import app

MODULES_DIR: Final = Path(app.__file__).resolve().parent / "modules"
API_ROOT: Final = Path(app.__file__).resolve().parents[2]
PREFIX: Final = "app.modules."
ALLOWED_EDGES: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("audit", "auth"),
        ("auth", "settings"),
        ("memberships", "members"),
        ("memberships", "payments"),
        ("memberships", "plans"),
        ("memberships", "settings"),
        ("payments", "settings"),
    }
)
LAZY_IMPORT_WHITELIST: Final[frozenset[tuple[str, str]]] = frozenset(
    {("payments", "memberships"), ("members", "memberships"), ("plans", "memberships")}
)
LAZY_MARK: Final = "# lazy: G-03"


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


def lazy_imports_sin_marca(fuente: str, modulo: str) -> list[int]:
    """Líneas de imports perezosos de otro service sin `# lazy: G-03` en la línea o la anterior."""
    lineas = fuente.splitlines()
    faltan: list[int] = []

    def visitar(nodo: ast.AST, dentro_de_funcion: bool) -> None:
        for hijo in ast.iter_child_nodes(nodo):
            en_funcion = dentro_de_funcion or isinstance(
                hijo, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
            )
            destinos = {_destino(n) for n in _nombres(hijo, modulo)} - {None, modulo}
            if en_funcion and destinos and isinstance(hijo, ast.stmt | ast.expr):
                numero = hijo.lineno
                vecinas = lineas[max(0, numero - 2) : numero]
                if not any(LAZY_MARK in linea for linea in vecinas):
                    faltan.append(numero)
            visitar(hijo, en_funcion)

    visitar(ast.parse(fuente), False)
    return faltan


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
    """`(arriba, perezosas)` por módulo: aristas de nivel de módulo y dentro de funciones."""
    arriba: dict[str, set[str]] = {}
    perezosas: dict[str, set[str]] = {}
    for servicio in sorted(MODULES_DIR.glob("*/service.py")):
        modulo = servicio.parent.name
        arriba[modulo], perezosas[modulo] = set(), set()
        for archivo in sorted(servicio.parent.glob("*.py")):
            de_arriba, lazy = service_edges(archivo.read_text(encoding="utf-8"), modulo)
            arriba[modulo] |= de_arriba
            perezosas[modulo] |= lazy
    return arriba, perezosas


def _aristas(grafo: dict[str, set[str]]) -> set[tuple[str, str]]:
    return {(a, b) for a, destinos in grafo.items() for b in destinos}


def test_hay_services_que_revisar() -> None:
    arriba, _ = _grafo_real()
    assert {"auth", "settings", "members", "plans", "memberships", "payments"} <= set(arriba)


def test_las_aristas_del_mapa_se_ven_tras_partir_auth() -> None:
    """Control (revisión Python H1): `auth → settings` está en `users.py`, no en `service.py`;
    si el grafo mirara solo `service.py` la arista desaparecería sin que nada fallara."""
    arriba, _ = _grafo_real()
    assert "settings" in arriba["auth"]
    assert "auth" in arriba["audit"]


def test_el_grafo_de_nivel_de_modulo_es_aciclico() -> None:
    arriba, _ = _grafo_real()
    assert find_cycle(arriba) is None, f"ciclo entre services: {find_cycle(arriba)}"


def test_solo_existen_las_aristas_del_mapa_de_contextos() -> None:
    arriba, _ = _grafo_real()
    sobrantes = sorted(_aristas(arriba) - ALLOWED_EDGES)
    assert sobrantes == [], f"aristas sin decisión: {sobrantes}"


def test_cada_arista_permitida_existe() -> None:
    """Una arista declarada que nadie usa es una decisión sin código (o un import que se perdió):
    `ALLOWED_EDGES` es exactamente el grafo de nivel de módulo."""
    arriba, _ = _grafo_real()
    faltan = sorted(ALLOWED_EDGES - _aristas(arriba))
    assert faltan == [], f"aristas declaradas sin import: {faltan}"


def test_memberships_depende_de_members_payments_plans_y_settings() -> None:
    """S3-B1 (D2): `sell` toma el socio, el plan y la política por sus services. S3-B4 (D1, D2):
    `memberships` registra el gate, se suscribe a `PaymentRegistered` y registra el primer pago
    por `payments.service`, a nivel de módulo (sentido mayoritario de G-03)."""
    arriba, perezosas = _grafo_real()
    assert arriba["memberships"] == {"members", "payments", "plans", "settings"}
    assert perezosas["memberships"] == set()


def test_payments_depende_de_settings_y_no_de_memberships() -> None:
    """S3-B3 (D1, D2, S3-D80): la arista `payments → settings` existe y no hay ninguna hacia
    `memberships`, ni de nivel de módulo ni perezosa (el puerto `MembershipGate` lo evita).
    `payments → members` y `payments → auth` llegan con B8 (S3-D80). S3-B4: el sentido
    `memberships → payments` sí existe a nivel de módulo; el grafo sigue acíclico."""
    arriba, perezosas = _grafo_real()
    assert arriba["payments"] == {"settings"}
    assert perezosas["payments"] == set()
    assert "memberships" not in arriba["payments"]
    assert "payments" in arriba["memberships"]


def test_plans_no_importa_services_y_solo_memberships_lo_importa() -> None:
    """Reescrita en S3-B1 (D2; antes `test_plans_no_agrega_aristas`)."""
    arriba, perezosas = _grafo_real()
    assert arriba["plans"] == set() and perezosas["plans"] == set()
    importadores = {a for a, destinos in arriba.items() if "plans" in destinos}
    assert importadores == {"memberships"}


def test_ningun_import_perezoso_fuera_de_la_lista_blanca() -> None:
    """Toda perezosa real está en la lista blanca (hoy no hay ninguna)."""
    _, perezosas = _grafo_real()
    fuera = sorted(_aristas(perezosas) - LAZY_IMPORT_WHITELIST)
    assert fuera == [], f"imports perezosos de otro service sin lista blanca: {fuera}"


def test_la_lista_blanca_es_la_de_g03() -> None:
    esperada = {("payments", "memberships"), ("members", "memberships"), ("plans", "memberships")}
    assert frozenset(esperada) == LAZY_IMPORT_WHITELIST
    assert not LAZY_IMPORT_WHITELIST & ALLOWED_EDGES


def test_todo_import_perezoso_lleva_su_comentario() -> None:
    faltan = [
        f"{archivo.relative_to(MODULES_DIR).as_posix()}:{linea}"
        for archivo in sorted(MODULES_DIR.glob("*/*.py"))
        for linea in lazy_imports_sin_marca(
            archivo.read_text(encoding="utf-8"), archivo.parent.name
        )
    ]
    assert faltan == [], f"imports perezosos sin '{LAZY_MARK}': {faltan}"


PARES_EN_AMBOS_ORDENES = sorted({par for a, b in ALLOWED_EDGES for par in ((a, b), (b, a))})


@pytest.mark.parametrize(
    ("primero", "segundo"),
    PARES_EN_AMBOS_ORDENES,
    ids=[f"{a}-{b}" for a, b in PARES_EN_AMBOS_ORDENES],
)
def test_los_services_se_importan_en_un_proceso_limpio_en_ambos_ordenes(
    primero: str, segundo: str
) -> None:
    orden = f"import app.modules.{primero}.service, app.modules.{segundo}.service"
    resultado = subprocess.run(  # noqa: S603 - comando fijo armado con nombres de módulo
        [sys.executable, "-I", "-c", orden],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr[-2000:]


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


def test_un_ciclo_solo_con_perezosas_no_cuenta_como_ciclo() -> None:
    """D2: `memberships → payments` arriba y `payments → memberships` perezosa (G-03) no son un
    ciclo de nivel de módulo."""
    memberships = "from app.modules.payments import service as payments_service\n"
    payments = (
        "def enriquecer():\n"
        "    # lazy: G-03 (payments -> memberships)\n"
        "    from app.modules.memberships import service\n"
    )
    arriba = {"memberships": service_edges(memberships, "memberships")[0]}
    arriba["payments"], perezosas = service_edges(payments, "payments")
    assert find_cycle(arriba) is None
    assert perezosas == {"memberships"}
    assert lazy_imports_sin_marca(payments, "payments") == []


def test_lazy_imports_sin_marca_ve_el_comentario_en_la_linea_o_la_anterior() -> None:
    fuente = (
        "from app.modules.members import service as members_service\n"
        "def con_marca():\n"
        "    # lazy: G-03 (payments -> memberships)\n"
        "    from app.modules.memberships import service\n"
        "def en_la_misma_linea():\n"
        "    from app.modules.memberships import service  # lazy: G-03\n"
        "def sin_marca():\n"
        "    from app.modules.memberships import service\n"
        "def ajeno():\n"
        "    from app.modules.memberships import schemas\n"
    )
    assert lazy_imports_sin_marca(fuente, "payments") == [8]


def test_find_cycle_detecta_un_ciclo_y_acepta_un_dag() -> None:
    assert find_cycle({"audit": {"auth"}, "auth": {"settings"}, "settings": set()}) is None
    ciclo = find_cycle({"a": {"b"}, "b": {"c"}, "c": {"a"}})
    assert ciclo is not None and ciclo[0] == ciclo[-1] and set(ciclo) == {"a", "b", "c"}
    assert find_cycle({"a": {"a"}}) == ["a", "a"]
