"""El api nunca carga la llave de firma (S7-D4, S7-D23 (5), M-4; endurecida en S7-W0-3b, M-3).

AST: solo `worker/` y `cli*` pasan algo distinto de `False` a `with_signing` / `signing_key` (ni
una variable, ni `1`, ni `**{...}` hacia las funciones que los declaran); el cierre de imports de
`main.py` (con `importlib.import_module`, incluido el f-string de módulos) nunca lo hace ni alcanza
`cli*` o `worker/`; `core/` y `modules/` nunca importan `app.cli*`; el proveedor local solo se
construye en `provider.py`; `DEFAULT_SIGNING_KEY_PATH` solo lo importa `config.py`; y los únicos
lectores de `CRYPTO_LOCAL_SIGNING_KEY_PATH` son los de la lista cerrada (E3).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
FLAGS = {"with_signing", "signing_key"}
LECTORES_DE_LA_VARIABLE = {
    "core/config.py",
    "core/config_signing.py",
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


def _funciones_con_flag(modulos: dict[str, ast.Module]) -> set[str]:
    """Nombres de las funciones que declaran `with_signing` o `signing_key` como parámetro."""
    return {
        n.name
        for arbol in modulos.values()
        for n in ast.walk(arbol)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
        and any(a.arg in FLAGS for a in n.args.args + n.args.kwonlyargs)
    }


def _nombre_llamado(llamada: ast.Call) -> str:
    f = llamada.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def _pasa_abierto(arbol: ast.AST, con_flag: set[str]) -> list[int]:
    """Llamadas que pasan a un flag algo que no es `False` ni el reenvío del mismo parámetro, o un
    `**` hacia una función que lo declara (M-3)."""
    lineas: list[int] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        for kw in nodo.keywords:
            if kw.arg is None and _nombre_llamado(nodo) in con_flag:
                lineas.append(nodo.lineno)
            elif kw.arg in FLAGS:
                cerrado = isinstance(kw.value, ast.Constant) and kw.value.value is False
                reenvio = isinstance(kw.value, ast.Name) and kw.value.id == kw.arg
                if not (cerrado or reenvio):
                    lineas.append(nodo.lineno)
    return lineas


def _es_zona_de_firma(ruta: str) -> bool:
    return ruta.startswith("worker/") or ruta.startswith("cli")


def _por_importlib(arg: ast.expr) -> set[str]:
    """`import_module("app.a.b")` o el f-string `f"app.modules.{x}.service"` (todos los módulos)."""
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        if arg.value.startswith("app."):
            return {arg.value.removeprefix("app.").replace(".", "/") + ".py"}
        return set()
    if isinstance(arg, ast.JoinedStr):
        trozos = [v.value if isinstance(v, ast.Constant) else None for v in arg.values]
        if trozos and trozos[0] == "app.modules." and trozos[-1]:
            cola = str(trozos[-1]).removeprefix(".").replace(".", "/")
            carpetas = (d for d in (SRC / "modules").iterdir() if d.is_dir())
            return {f"modules/{d.name}/{cola}.py" for d in carpetas}
    return set()


def _importados(arbol: ast.Module) -> set[str]:
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
        elif isinstance(nodo, ast.Call) and _nombre_llamado(nodo) == "import_module" and nodo.args:
            salida |= _por_importlib(nodo.args[0])
    return salida


def _cierre_de_main(modulos: dict[str, ast.Module]) -> set[str]:
    visto: set[str] = set()
    pendientes = ["main.py"]
    while pendientes:
        ruta = pendientes.pop()
        if ruta in visto or ruta not in modulos:
            continue
        visto.add(ruta)
        pendientes.extend(_importados(modulos[ruta]))
    return visto


def test_fuera_de_worker_y_cli_nadie_pasa_algo_distinto_de_false() -> None:
    modulos = _modulos()
    con_flag = _funciones_con_flag(modulos)
    culpables = {
        ruta: lineas
        for ruta, arbol in modulos.items()
        if not _es_zona_de_firma(ruta) and (lineas := _pasa_abierto(arbol, con_flag))
    }

    assert culpables == {}, f"solo worker/ y cli* abren with_signing/signing_key: {culpables}"


def test_el_detector_ve_variables_literales_distintos_y_doble_asterisco() -> None:
    """El propio detector: lo que antes se le escapaba."""
    con_flag = {"abrir"}
    for codigo in (
        "abrir(with_signing=True)",
        "abrir(with_signing=1)",
        "abrir(with_signing=x)",
        "abrir(with_signing=not False)",
        "abrir(**{'with_signing': True})",
    ):
        assert _pasa_abierto(ast.parse(codigo), con_flag), codigo
    for codigo in ("abrir(with_signing=False)", "abrir(with_signing=with_signing)", "abrir(x=1)"):
        assert not _pasa_abierto(ast.parse(codigo), con_flag), codigo


def test_el_cierre_de_imports_de_main_nunca_abre_y_no_alcanza_cli_ni_worker() -> None:
    modulos = _modulos()
    visto = _cierre_de_main(modulos)
    con_flag = _funciones_con_flag(modulos)

    assert "core/crypto/recovery.py" in visto
    assert "modules/auth/service.py" in visto, "el cierre debe seguir importlib.import_module"
    culpables = {r: _pasa_abierto(modulos[r], con_flag) for r in visto}
    assert {r: v for r, v in culpables.items() if v} == {}
    alcanzados = sorted(r for r in visto if _es_zona_de_firma(r))
    assert alcanzados == [], f"main.py alcanza código de firma: {alcanzados}"


def _importa_cli(nodo: ast.AST) -> bool:
    if isinstance(nodo, ast.ImportFrom):
        modulo = nodo.module or ""
        return modulo.startswith("app.cli") or (
            modulo == "app" and any(a.name.startswith("cli") for a in nodo.names)
        )
    if isinstance(nodo, ast.Import):
        return any(a.name.startswith("app.cli") for a in nodo.names)
    return False


def test_core_y_modules_nunca_importan_cli() -> None:
    culpables = {
        ruta: [ast.unparse(n) for n in ast.walk(arbol) if _importa_cli(n)]
        for ruta, arbol in _modulos().items()
        if ruta.startswith(("core/", "modules/"))
    }

    assert {r: v for r, v in culpables.items() if v} == {}


def test_el_proveedor_local_solo_se_construye_en_provider() -> None:
    constructores = {
        ruta
        for ruta, arbol in _modulos().items()
        if any(
            isinstance(n, ast.Call) and _nombre_llamado(n) == "LocalFileProvider"
            for n in ast.walk(arbol)
        )
    }

    assert constructores <= {"core/crypto/provider.py"}, sorted(constructores)


def test_el_valor_por_omision_de_la_ruta_solo_lo_usa_config() -> None:
    usuarios = {
        ruta
        for ruta, arbol in _modulos().items()
        if any(
            (isinstance(n, ast.Name) and n.id == "DEFAULT_SIGNING_KEY_PATH")
            or (isinstance(n, ast.Attribute) and n.attr == "DEFAULT_SIGNING_KEY_PATH")
            or (isinstance(n, ast.alias) and n.name == "DEFAULT_SIGNING_KEY_PATH")
            for n in ast.walk(arbol)
        )
    }

    assert usuarios <= {"core/config.py", "core/config_signing.py"}, sorted(usuarios)


def _lee_la_variable(n: ast.AST) -> bool:
    nombre = "CRYPTO_LOCAL_SIGNING_KEY_PATH"
    return (
        (isinstance(n, ast.Attribute) and n.attr == nombre)
        or (isinstance(n, ast.Name) and n.id == nombre)
        or (isinstance(n, ast.keyword) and n.arg == nombre)
        or (isinstance(n, ast.Constant) and n.value == nombre)
    )


def test_los_lectores_de_la_variable_son_los_de_la_lista_cerrada() -> None:
    lectores = {
        ruta
        for ruta, arbol in _modulos().items()
        if any(_lee_la_variable(n) for n in ast.walk(arbol))
    }

    assert lectores <= LECTORES_DE_LA_VARIABLE, sorted(lectores - LECTORES_DE_LA_VARIABLE)


def test_los_valores_por_omision_son_false_en_todo_src() -> None:
    """M-4: la fábrica abierta por omisión reabriría el residual con la próxima llamada. Se
    revisan TODAS las funciones de `src/app` (antes solo tres archivos)."""
    omisiones: dict[str, object] = {}
    for ruta, arbol in _modulos().items():
        for nodo in ast.walk(arbol):
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
    assert "core/crypto/sign_rotation.py:switch_provider" in omisiones
    # sin valor por omisión (parámetro obligatorio) también es cerrado: nadie lo abre sin pedirlo
    assert all(v is False or v is None for v in omisiones.values()), omisiones
