"""El api nunca carga la llave de firma (S7-D4, S7-D23 (5), M-4).

AST: solo `worker/` y `cli*` pasan `with_signing=True` / `signing_key=True`; el cierre de imports
de `main.py` (incluidos `recovery` y `rotate_job`) nunca lo hace; y los únicos lectores de
`CRYPTO_LOCAL_SIGNING_KEY_PATH` son los de la lista cerrada de la exploración (E3).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
FLAGS = {"with_signing", "signing_key"}
LECTORES_DE_LA_VARIABLE = {
    "core/config.py",
    "core/crypto/local_provider.py",
    "core/crypto/provider.py",
    "cli.py",
    "cli_ops/keys.py",
    "cli_ops/openapi.py",
}


def _modulos() -> dict[str, ast.Module]:
    return {
        p.relative_to(SRC).as_posix(): ast.parse(p.read_text(encoding="utf-8"))
        for p in sorted(SRC.rglob("*.py"))
    }


def _pasa_true(arbol: ast.Module) -> list[int]:
    lineas: list[int] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            for kw in nodo.keywords:
                if (
                    kw.arg in FLAGS
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ):
                    lineas.append(nodo.lineno)
    return lineas


def _es_zona_de_firma(ruta: str) -> bool:
    return ruta.startswith("worker/") or ruta.startswith("cli")


def _importados(ruta: str, arbol: ast.Module) -> set[str]:
    salida: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.module.startswith("app."):
            base = nodo.module.removeprefix("app.").replace(".", "/")
            salida.add(f"{base}.py")
            salida.add(f"{base}/__init__.py")
            for alias in nodo.names:
                salida.add(f"{base}/{alias.name}.py")
        elif isinstance(nodo, ast.Import):
            for alias in nodo.names:
                if alias.name.startswith("app."):
                    salida.add(alias.name.removeprefix("app.").replace(".", "/") + ".py")
    return salida


def test_fuera_de_worker_y_cli_nadie_pasa_true() -> None:
    culpables = {
        ruta: lineas
        for ruta, arbol in _modulos().items()
        if not _es_zona_de_firma(ruta) and (lineas := _pasa_true(arbol))
    }

    assert culpables == {}, f"solo worker/ y cli* pasan with_signing=True: {culpables}"


def test_el_cierre_de_imports_de_main_nunca_pasa_true() -> None:
    modulos = _modulos()
    visto: set[str] = set()
    pendientes = ["main.py"]
    while pendientes:
        ruta = pendientes.pop()
        if ruta in visto or ruta not in modulos:
            continue
        visto.add(ruta)
        pendientes.extend(_importados(ruta, modulos[ruta]))

    assert "core/crypto/recovery.py" in visto
    culpables = {r: _pasa_true(modulos[r]) for r in visto if _pasa_true(modulos[r])}
    assert culpables == {}, f"main.py alcanza código que pasa with_signing=True: {culpables}"


def test_los_lectores_de_la_variable_son_los_de_la_lista_cerrada() -> None:
    lectores = {
        ruta
        for ruta, arbol in _modulos().items()
        if any(
            isinstance(n, ast.Attribute) and n.attr == "CRYPTO_LOCAL_SIGNING_KEY_PATH"
            for n in ast.walk(arbol)
        )
    }

    assert lectores <= LECTORES_DE_LA_VARIABLE, sorted(lectores - LECTORES_DE_LA_VARIABLE)


def test_los_valores_por_omision_son_false() -> None:
    """M-4: la fábrica abierta por omisión reabriría el residual con la próxima llamada."""
    omisiones: dict[str, object] = {}
    for ruta in ("core/crypto/provider.py", "core/crypto/recovery.py", "core/config.py"):
        for nodo in ast.walk(ast.parse((SRC / ruta).read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
                args = nodo.args
                nombres = [a.arg for a in args.args + args.kwonlyargs]
                defaults = [None] * (len(args.args) - len(args.defaults)) + list(args.defaults)
                defaults += list(args.kw_defaults)
                for nombre, default in zip(nombres, defaults, strict=False):
                    if nombre in FLAGS:
                        omisiones[f"{ruta}:{nodo.name}"] = (
                            default.value if isinstance(default, ast.Constant) else default
                        )

    assert omisiones, "no hay funciones con with_signing/signing_key"
    # sin valor por omisión (parámetro obligatorio) también es cerrado: nadie lo abre sin pedirlo
    assert all(v is False or v is None for v in omisiones.values()), omisiones
