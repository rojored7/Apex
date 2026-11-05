"""`register_health_check` solo se llama desde `main.py` y `core/` (S4B-B2, revisión de seguridad).

`/health` es público: quien registra una comprobación decide qué valores salen en el cuerpo y qué
baja el 200. Por AST, ningún archivo de `src/app` fuera de `main.py` y de `app/core/` puede
llamar a `register_health_check` (ni importarla). Controles con fuentes falsas.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

SRC: Final = Path(__file__).resolve().parents[2] / "src" / "app"
NOMBRE: Final = "register_health_check"


def usa_registro(fuente: str) -> list[int]:
    """Líneas donde `fuente` llama o importa `register_health_check`."""
    lineas: list[int] = []
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Call):
            f = nodo.func
            nombre = (
                f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            )
            if nombre == NOMBRE:
                lineas.append(nodo.lineno)
        elif isinstance(nodo, ast.ImportFrom) and any(a.name == NOMBRE for a in nodo.names):
            lineas.append(nodo.lineno)
    return sorted(lineas)


def permitido(path: Path) -> bool:
    relativo = path.relative_to(SRC).as_posix()
    return relativo == "main.py" or relativo.startswith("core/")


def infractores() -> list[str]:
    return [
        p.relative_to(SRC).as_posix()
        for p in sorted(SRC.rglob("*.py"))
        if not permitido(p) and usa_registro(p.read_text(encoding="utf-8"))
    ]


def test_solo_main_y_core_registran_comprobaciones_de_salud() -> None:
    assert infractores() == []


def test_main_si_registra_el_check_de_backup() -> None:
    assert usa_registro((SRC / "main.py").read_text(encoding="utf-8")), "main.py no registra"


def test_control_las_llamadas_e_imports_se_ven() -> None:
    assert usa_registro("register_health_check('x', f, critical=False)\n") == [1]
    assert usa_registro("from app.core import health\nhealth.register_health_check('x', f)\n") == [
        2
    ]
    assert usa_registro("from app.core.health import register_health_check\n") == [1]
    assert usa_registro("def f():\n    health.clear_health_checks()\n") == []


def test_control_el_permiso_es_solo_main_y_core() -> None:
    assert permitido(SRC / "main.py")
    assert permitido(SRC / "core" / "health.py")
    assert not permitido(SRC / "worker" / "jobs" / "backup_check.py")
    assert not permitido(SRC / "modules" / "dashboard" / "service.py")
    assert not permitido(SRC / "cli.py")


def nombres_registrados(fuente: str) -> set[str]:
    """Primer argumento literal de cada `register_health_check(...)` de `fuente`."""
    nombres: set[str] = set()
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Call) and nodo.args and isinstance(nodo.args[0], ast.Constant):
            f = nodo.func
            nombre = (
                f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            )
            if nombre == NOMBRE:
                nombres.add(str(nodo.args[0].value))
    return nombres


def test_s5_b3_crypto_se_registra_solo_desde_main() -> None:
    """S5-B3 (S5-D13): el check `crypto` (crítico) lo registra `main.py` y nadie más; ni `core/`
    ni `worker/` ni los módulos."""
    assert "crypto" in nombres_registrados((SRC / "main.py").read_text(encoding="utf-8"))
    fuera = [
        p.relative_to(SRC).as_posix()
        for p in sorted(SRC.rglob("*.py"))
        if p != SRC / "main.py" and "crypto" in nombres_registrados(p.read_text(encoding="utf-8"))
    ]
    assert fuera == []


def test_control_nombres_registrados_ve_el_literal() -> None:
    fuente = (
        "health.register_health_check('crypto', f, critical=True)\nregister_health_check(x, f)\n"
    )
    assert nombres_registrados(fuente) == {"crypto"}
