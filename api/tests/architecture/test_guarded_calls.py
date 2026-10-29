"""Llamadas que solo pueden aparecer en su sitio (S3-B1; S3-D56: L-6 y L-11; S3-D59: D-3).

Por AST sobre `src/app`:
- L-6: el argumento con nombre `enforce_retroactive_limit=` solo se pasa desde `cli.py` (la
  importación de N-24); nunca desde un `router.py` ni desde ningún otro archivo. Un router no
  puede saltarse el límite retroactivo de la venta.
- L-11: ninguna llamada a `create_async_engine(...)` ni a `.execution_options(...)` lleva
  `isolation_level`: todo el api corre en `READ COMMITTED`, el nivel sobre el que se diseñaron el
  orden de candados de D3 y la `EXCLUDE`. Excepción única (S4A-D44, H-2; E10): la conexión del
  candado de verificación `4_270_003` en `core/audit_verify.py` y `modules/audit/verify.py` (ruta
  relativa exacta), solo con `AUTOCOMMIT` (no abre transacción: ni lecturas ni escrituras de
  negocio), con controles de que cualquier otro archivo sigue fallando.
- D-3: `with_for_update` sobre `Membership` solo existe en `memberships/sell.py::lock_membership`
  (única puerta, con `populate_existing=True`); ningún otro archivo de `memberships` lo llama, y
  ningún archivo fuera de `memberships` nombra `Membership`.
- L-5 (S3-B4, S3-D56): `set_membership_gate(` solo se llama en `memberships/service.py`, una vez,
  al nivel del módulo (al importarse) y con `membership_payability`; ningún otro archivo de
  `src/app` lo llama (`payments/service.py` lo define). Las pruebas (`tests/`) sí pueden, para
  quitar y restaurar el gate.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
APP = SRC / "app"
MEMBERSHIPS = APP / "modules" / "memberships"


def _archivos() -> list[Path]:
    return sorted(APP.rglob("*.py"))


def _relativo(path: Path) -> str:
    return path.relative_to(APP).as_posix()


def _nombre_llamado(nodo: ast.Call) -> str | None:
    if isinstance(nodo.func, ast.Name):
        return nodo.func.id
    if isinstance(nodo.func, ast.Attribute):
        return nodo.func.attr
    return None


def con_argumento(fuente: str, argumento: str) -> list[int]:
    """Líneas de las llamadas que pasan `argumento=` con nombre."""
    return [
        nodo.lineno
        for nodo in ast.walk(ast.parse(fuente))
        if isinstance(nodo, ast.Call) and any(k.arg == argumento for k in nodo.keywords)
    ]


def con_isolation_level(fuente: str) -> list[int]:
    return [
        nodo.lineno
        for nodo in ast.walk(ast.parse(fuente))
        if isinstance(nodo, ast.Call)
        and _nombre_llamado(nodo) in {"create_async_engine", "create_engine", "execution_options"}
        and any(k.arg == "isolation_level" for k in nodo.keywords)
    ]


def for_update_por_funcion(fuente: str) -> dict[str, list[int]]:
    """`{función: [líneas]}` de cada llamada a `.with_for_update(` dentro de una función."""
    salida: dict[str, list[int]] = {}
    for funcion in ast.walk(ast.parse(fuente)):
        if not isinstance(funcion, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        lineas = [
            nodo.lineno
            for nodo in ast.walk(funcion)
            if isinstance(nodo, ast.Call) and _nombre_llamado(nodo) == "with_for_update"
        ]
        if lineas:
            salida[funcion.name] = lineas
    return salida


def llamadas_a(fuente: str, nombre: str) -> list[tuple[int, bool, list[str]]]:
    """`(línea, al_nivel_del_módulo, argumentos)` de cada llamada a `nombre(`; los argumentos como
    texto (`ast.unparse`)."""
    arbol = ast.parse(fuente)
    en_funciones = {
        id(nodo)
        for funcion in ast.walk(arbol)
        if isinstance(funcion, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda)
        for nodo in ast.walk(funcion)
    }
    return [
        (nodo.lineno, id(nodo) not in en_funciones, [ast.unparse(a) for a in nodo.args])
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call) and _nombre_llamado(nodo) == nombre
    ]


def test_set_membership_gate_solo_desde_la_fachada_de_memberships() -> None:
    """L-5: el gate de pagos lo registra solo `memberships/service.py`, al importarse, con el
    adaptador real."""
    llamadas = {
        _relativo(path): encontradas
        for path in _archivos()
        if (encontradas := llamadas_a(path.read_text(encoding="utf-8"), "set_membership_gate"))
    }
    assert set(llamadas) == {"modules/memberships/service.py"}, llamadas
    [(_, al_nivel_del_modulo, argumentos)] = llamadas["modules/memberships/service.py"]
    assert al_nivel_del_modulo
    assert argumentos == ["membership_payability"]


def test_enforce_retroactive_limit_solo_desde_el_cli() -> None:
    llamadas = {
        _relativo(path): lineas
        for path in _archivos()
        if (lineas := con_argumento(path.read_text(encoding="utf-8"), "enforce_retroactive_limit"))
    }
    fuera = {archivo: lineas for archivo, lineas in llamadas.items() if archivo != "cli.py"}
    assert fuera == {}, fuera
    assert not any(archivo.endswith("router.py") for archivo in llamadas)


AUTOCOMMIT_PERMITIDO: frozenset[str] = frozenset(
    {"core/audit_verify.py", "modules/audit/verify.py"}
)
"""S4A-D44 (H-2, E10): la conexión del candado `4_270_003` es la única con `isolation_level`, y
solo `AUTOCOMMIT`. Ruta relativa a `src/app` exacta (nunca un prefijo ni un nombre de archivo)."""


def fuera_de_la_excepcion(encontrados: dict[str, list[int]]) -> dict[str, list[int]]:
    """Los hallazgos de L-11 cuyo archivo no es exactamente uno de `AUTOCOMMIT_PERMITIDO`."""
    return {
        archivo: lineas
        for archivo, lineas in encontrados.items()
        if archivo not in AUTOCOMMIT_PERMITIDO
    }


def niveles_de_aislamiento(fuente: str) -> list[object]:
    """Valor (literal o `None` si no es constante) de cada `isolation_level=` de L-11."""
    return [
        k.value.value if isinstance(k.value, ast.Constant) else None
        for nodo in ast.walk(ast.parse(fuente))
        if isinstance(nodo, ast.Call)
        and _nombre_llamado(nodo) in {"create_async_engine", "create_engine", "execution_options"}
        for k in nodo.keywords
        if k.arg == "isolation_level"
    ]


def test_ningun_engine_ni_execution_options_fija_isolation_level() -> None:
    """L-11 con la excepción única de S4A-D44 (`AUTOCOMMIT_PERMITIDO`)."""
    encontrados = {
        _relativo(path): lineas
        for path in _archivos()
        if (lineas := con_isolation_level(path.read_text(encoding="utf-8")))
    }
    assert fuera_de_la_excepcion(encontrados) == {}


def test_la_excepcion_solo_admite_autocommit_y_se_usa() -> None:
    """S4A-D44: dentro de la excepción todo `isolation_level` es el literal `"AUTOCOMMIT"` y la
    conexión del candado existe (al menos un uso entre los dos archivos)."""
    niveles = [
        nivel
        for relativo in sorted(AUTOCOMMIT_PERMITIDO)
        if (APP / relativo).is_file()
        for nivel in niveles_de_aislamiento((APP / relativo).read_text(encoding="utf-8"))
    ]
    assert niveles, "la conexión del candado de verificación debe abrirse en AUTOCOMMIT"
    assert set(niveles) == {"AUTOCOMMIT"}, niveles


def test_lock_membership_es_la_unica_puerta_de_for_update_en_memberships() -> None:
    por_archivo = {
        path.name: for_update_por_funcion(path.read_text(encoding="utf-8"))
        for path in sorted(MEMBERSHIPS.glob("*.py"))
    }
    fuera = {
        archivo: funciones
        for archivo, funciones in por_archivo.items()
        if funciones and (archivo, set(funciones)) != ("sell.py", {"lock_membership"})
    }
    assert fuera == {}, fuera
    assert set(por_archivo.get("sell.py", {})) == {"lock_membership"}, (
        "lock_membership debe tomar la fila con with_for_update"
    )


def test_expirations_no_llama_with_for_update() -> None:
    """S4A-B2 (S4A-D2): el recálculo toma la fila por `sell.lock_membership`, nunca con su propio
    `FOR UPDATE` (y el archivo existe: la regla de arriba no lo cubriría si faltara)."""
    archivo = MEMBERSHIPS / "expirations.py"
    assert archivo.is_file()
    fuente = archivo.read_text(encoding="utf-8")
    assert for_update_por_funcion(fuente) == {}
    assert not [
        n
        for n in ast.walk(ast.parse(fuente))
        if isinstance(n, ast.Call) and _nombre_llamado(n) == "with_for_update"
    ]


def test_lock_membership_usa_populate_existing() -> None:
    arbol = ast.parse((MEMBERSHIPS / "sell.py").read_text(encoding="utf-8"))
    funcion = next(
        n
        for n in ast.walk(arbol)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "lock_membership"
    )
    opciones = [
        k.arg
        for n in ast.walk(funcion)
        if isinstance(n, ast.Call) and _nombre_llamado(n) == "execution_options"
        for k in n.keywords
    ]
    assert "populate_existing" in opciones


def test_fuera_de_memberships_nadie_nombra_membership() -> None:
    nombran = sorted(
        _relativo(path)
        for path in _archivos()
        if MEMBERSHIPS not in path.parents
        and any(
            isinstance(n, ast.Name) and n.id == "Membership"
            for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        )
    )
    assert nombran == []


# Controles con fuentes falsas ----------------------------------------------------------------


def test_los_analizadores_detectan_las_llamadas_prohibidas() -> None:
    router = "async def vender(s):\n    await service.sell(s, enforce_retroactive_limit=False)\n"
    assert con_argumento(router, "enforce_retroactive_limit") == [2]
    motor = (
        "create_async_engine(url, isolation_level='SERIALIZABLE')\n"
        "stmt.execution_options(isolation_level='REPEATABLE READ')\n"
        "stmt.execution_options(populate_existing=True)\n"
    )
    assert con_isolation_level(motor) == [1, 2]
    lifecycle = (
        "async def on_payment_registered(event, s):\n"
        "    await s.execute(select(Membership).with_for_update())\n"
        "async def lock_membership(s, i):\n"
        "    return select(Membership).with_for_update().execution_options(\n"
        "        populate_existing=True)\n"
    )
    assert for_update_por_funcion(lifecycle) == {
        "on_payment_registered": [2],
        "lock_membership": [4],
    }
    definicion = "async def sell(s, *, enforce_retroactive_limit: bool = True):\n    pass\n"
    assert con_argumento(definicion, "enforce_retroactive_limit") == []
    gate = (
        "payments_service.set_membership_gate(membership_payability)\n"
        "def f():\n"
        "    set_membership_gate(None)\n"
        "def set_membership_gate(gate):\n"
        "    pass\n"
    )
    assert llamadas_a(gate, "set_membership_gate") == [
        (1, True, ["membership_payability"]),
        (3, False, ["None"]),
    ]


CANDADO_FALSO = (
    "async def acquire():\n"
    "    conn = await db.get_engine().connect()\n"
    '    conn = await conn.execution_options(isolation_level="AUTOCOMMIT")\n'
    "    return conn\n"
    "async def otra():\n"
    '    return await (await engine.connect()).execution_options(isolation_level="AUTOCOMMIT")\n'
    "async def tercera():\n"
    "    async with engine.connect() as c:\n"
    "        await c.execution_options(isolation_level=NIVEL)\n"
)


@pytest.mark.parametrize(
    "archivo",
    [
        "modules/members/service.py",
        "modules/audit/router.py",
        "modules/audit/verify_extra.py",
        "core/audit_verify_copia.py",
        "audit_verify.py",
        "cli.py",
        "worker/runner.py",
    ],
)
def test_control_la_excepcion_de_l11_no_cubre_otro_archivo(archivo: str) -> None:
    """E10: la conexión `AUTOCOMMIT` dentro de una función (asignada, encadenada tras
    `connect(...)` o en un `async with`) se detecta y, fuera de las dos rutas exactas, falla."""
    lineas = con_isolation_level(CANDADO_FALSO)
    assert lineas == [3, 6, 9]
    assert fuera_de_la_excepcion({archivo: lineas}) == {archivo: [3, 6, 9]}


@pytest.mark.parametrize("archivo", sorted(AUTOCOMMIT_PERMITIDO))
def test_control_las_dos_rutas_exactas_si_quedan_exentas(archivo: str) -> None:
    assert fuera_de_la_excepcion({archivo: con_isolation_level(CANDADO_FALSO)}) == {}


def test_control_niveles_de_aislamiento_lee_el_literal_o_marca_lo_dinamico() -> None:
    assert niveles_de_aislamiento(CANDADO_FALSO) == ["AUTOCOMMIT", "AUTOCOMMIT", None]
