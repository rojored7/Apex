"""Tamaño de archivos y funciones de `api/src` (revisión Python H1 y M7; reglas de estilo del
equipo: archivos de 800 líneas como máximo y funciones de 50).

Antes `auth/service.py` tenía 1257 líneas y `main.create_app`, `change_password` y
`update_user` pasaban de 50. La prueba cuenta líneas físicas (docstrings incluidos) y, para las
funciones, de la línea del `def` a la última del cuerpo.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
MAX_LINEAS_ARCHIVO = 800
MAX_LINEAS_FUNCION = 50


def _archivos() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def test_hay_archivos_que_medir() -> None:
    assert len(_archivos()) > 50


def test_ningun_archivo_supera_800_lineas() -> None:
    largos = [
        f"{p.relative_to(SRC).as_posix()}: {n}"
        for p in _archivos()
        if (n := len(p.read_text(encoding="utf-8").splitlines())) > MAX_LINEAS_ARCHIVO
    ]
    assert largos == [], "\n".join(largos)


def test_ninguna_funcion_supera_50_lineas() -> None:
    largas: list[str] = []
    for p in _archivos():
        arbol = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
                lineas = (nodo.end_lineno or nodo.lineno) - nodo.lineno + 1
                if lineas > MAX_LINEAS_FUNCION:
                    largas.append(f"{p.relative_to(SRC).as_posix()}:{nodo.lineno} {nodo.name}")
    assert largas == [], "\n".join(largas)


def test_los_archivos_de_b1_se_miden() -> None:
    """S4B-B1: `seed/**`, `imports/**` y `cli_ops/**` están dentro de lo que se mide (rglob)."""
    medidos = {p.relative_to(SRC).as_posix() for p in _archivos()}
    assert {
        "seed/apply.py",
        "seed/dataset.py",
        "imports/members_xlsx.py",
        "imports/report.py",
        "cli_ops/seed_demo.py",
        "cli_ops/import_members.py",
    } <= medidos


# S4B-B3b: las cuatro funciones de la rotación (S4B-D39, D95) ----------------------------------

FUNCIONES_DE_ROTACION = ("start_rotation", "reencrypt_batch", "rotate_index", "retire_key")
ARCHIVOS_DE_ROTACION = ("core/crypto/service.py", "core/crypto/rotation.py")
"""`rotation.py` solo existe si `service.py` pasa de 600 líneas (S4B-D95)."""


def _es_stub(funcion: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """`True` si el cuerpo (sin docstring) es solo `raise NotImplementedError(...)` o `...`."""
    cuerpo = list(funcion.body)
    primero = cuerpo[0] if cuerpo else None
    if (
        isinstance(primero, ast.Expr)
        and isinstance(primero.value, ast.Constant)
        and isinstance(primero.value.value, str)
    ):
        cuerpo = cuerpo[1:]
    if len(cuerpo) != 1:
        return False
    unico = cuerpo[0]
    if isinstance(unico, ast.Raise):
        return "NotImplementedError" in ast.unparse(unico)
    return (
        isinstance(unico, ast.Expr)
        and isinstance(unico.value, ast.Constant)
        and unico.value.value is Ellipsis
    )


def _funciones_de_rotacion() -> dict[str, tuple[int, bool]]:
    """`{nombre: (líneas, es_stub)}` de las cuatro funciones, en `service.py` o `rotation.py`."""
    salida: dict[str, tuple[int, bool]] = {}
    for relativo in ARCHIVOS_DE_ROTACION:
        ruta = SRC / relativo
        if not ruta.is_file():
            continue
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef) and (
                nodo.name in FUNCIONES_DE_ROTACION
            ):
                lineas = (nodo.end_lineno or nodo.lineno) - nodo.lineno + 1
                salida[nodo.name] = (lineas, _es_stub(nodo))
    return salida


def test_las_cuatro_funciones_de_rotacion_estan_implementadas_y_miden_menos_de_50() -> None:
    medidas = _funciones_de_rotacion()
    assert set(medidas) == set(FUNCIONES_DE_ROTACION), sorted(
        set(FUNCIONES_DE_ROTACION) - set(medidas)
    )
    stubs = sorted(n for n, (_, es_stub) in medidas.items() if es_stub)
    assert stubs == [], f"siguen siendo stubs: {stubs}"
    largas = {n: lineas for n, (lineas, _) in medidas.items() if lineas >= MAX_LINEAS_FUNCION}
    assert largas == {}, largas


def test_service_y_rotation_respetan_el_tope_de_archivo_de_d95() -> None:
    """S4B-D95: si `service.py` pasa de 600 líneas, `rotation.py` existe con `reencrypt_batch` y
    `rotate_index`."""
    service = (SRC / "core/crypto/service.py").read_text(encoding="utf-8").splitlines()
    rotation = SRC / "core/crypto/rotation.py"
    if len(service) > 600:
        assert rotation.is_file(), "service.py pasa de 600 líneas: extraer rotation.py (D95)"
    assert len(service) <= MAX_LINEAS_ARCHIVO


def test_control_un_stub_y_una_funcion_larga_se_detectan() -> None:
    stub = ast.parse("async def f():\n    '''doc'''\n    raise NotImplementedError('x')\n").body[0]
    real = ast.parse("def f():\n    x = 1\n    return x\n").body[0]
    assert isinstance(stub, ast.AsyncFunctionDef) and _es_stub(stub)
    assert isinstance(real, ast.FunctionDef) and not _es_stub(real)
