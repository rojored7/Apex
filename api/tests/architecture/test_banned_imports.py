"""Ningún archivo de `src/app` fuera del bus importa criptografía (CLAUDE.md, bus regla 8).

Primera versión (US-002): recorría el árbol con `ast` solo por `import` y `from`. S2-B7 (US-031)
la pasa al analizador compartido `find_banned_imports` de `_imports.py`, que también reporta
`importlib.import_module("...")`, `import_module("...")` y `__import__("...")` con literal, y
agrega un control en un directorio temporal. Complementa la regla `banned-api` de ruff.

S3-B1 (US-083, E11): el recorrido cubre `core/locks.py` y todos los archivos de
`modules/memberships` (y de `modules/payments` desde B3): ninguno es parte del bus y ninguno
importa `hashlib`, `hmac`, `cryptography`, `jwt`, `argon2` ni `oqs`; el candado del socio calcula
su llave con `hashtextextended` en SQL.
"""

from __future__ import annotations

from pathlib import Path

from tests.architecture._imports import BannedImport, find_banned_imports, is_allowed

SRC = Path(__file__).resolve().parents[2] / "src"
APP = SRC / "app"


def _hallazgos(raiz: Path, base: Path) -> list[BannedImport]:
    salida: list[BannedImport] = []
    for path in sorted(raiz.rglob("*.py")):
        relativo = path.relative_to(base).as_posix()
        salida.extend(find_banned_imports(path.read_text(encoding="utf-8"), relativo))
    return salida


def test_sin_imports_de_criptografia_fuera_del_bus() -> None:
    assert [str(h) for h in _hallazgos(APP, SRC)] == []


def test_el_recorrido_cubre_locks_memberships_y_payments() -> None:
    """S3-B1 y S3-B3 (US-083, E11): los archivos nuevos están dentro del recorrido de `APP` y
    ninguno es parte del bus (no los deja pasar `is_allowed`)."""
    revisados = {p.relative_to(SRC).as_posix() for p in APP.rglob("*.py")}
    nuevos = {
        "app/core/locks.py",
        *(f"app/modules/payments/{n}.py" for n in ("models", "rules", "queries", "service")),
        *(f"app/modules/memberships/{n}.py" for n in ("sell", "lifecycle", "queries")),
    }
    assert nuevos <= revisados, sorted(nuevos - revisados)
    assert not [n for n in nuevos if is_allowed(n)]


def test_el_recorrido_si_visita_el_bus_y_lo_deja_pasar() -> None:
    """El bus sí importa primitivas: si el recorrido no lo viera, la prueba no probaría nada."""
    aead = APP / "core" / "crypto" / "aead.py"
    assert "cryptography" in aead.read_text(encoding="utf-8")
    assert is_allowed(aead.relative_to(SRC).as_posix())
    assert find_banned_imports(aead.read_text(encoding="utf-8"), "app/modules/x/service.py")


def test_control_en_un_arbol_temporal_reporta_archivo_y_linea(tmp_path: Path) -> None:
    """US-031 criterios 1 a 3: el mismo import falla en un módulo y pasa dentro del bus."""
    servicio = tmp_path / "app" / "modules" / "members" / "service.py"
    bus = tmp_path / "app" / "core" / "crypto" / "aead.py"
    seguridad = tmp_path / "app" / "core" / "security.py"
    for archivo in (servicio, bus, seguridad):
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text(
            '"""m."""\n\nimport hashlib\nfrom cryptography.hazmat.primitives import hashes\n'
            'def f() -> None:\n    __import__("jwt")\n',
            encoding="utf-8",
        )
    (tmp_path / "app" / "modules" / "members" / "router.py").write_text(
        'import importlib\nimportlib.import_module("hmac")\n', encoding="utf-8"
    )

    assert [str(h) for h in _hallazgos(tmp_path / "app", tmp_path)] == [
        "app/modules/members/router.py:2 importa hmac",
        "app/modules/members/service.py:3 importa hashlib",
        "app/modules/members/service.py:4 importa cryptography.hazmat.primitives",
        "app/modules/members/service.py:6 importa jwt",
    ]


MEMBERSHIPS_ARCHIVOS = (
    "__init__",
    "models",
    "rules",
    "events",
    "sell",
    "lifecycle",
    "queries",
    "exceptions",
    "schemas",
    "router",
    "service",
)


def test_el_recorrido_cubre_core_locks_y_memberships() -> None:
    visitados = {path.relative_to(SRC).as_posix() for path in APP.rglob("*.py")}
    esperados = {"app/core/locks.py"} | {
        f"app/modules/memberships/{nombre}.py" for nombre in MEMBERSHIPS_ARCHIVOS
    }
    assert esperados <= visitados, sorted(esperados - visitados)
    for relativo in sorted(esperados):
        assert not is_allowed(relativo), relativo
        fuente = (SRC / relativo).read_text(encoding="utf-8")
        assert find_banned_imports(fuente, relativo) == [], relativo


def test_el_candado_del_socio_usa_hashtextextended_en_sql() -> None:
    fuente = (APP / "core" / "locks.py").read_text(encoding="utf-8")
    assert "hashtextextended" in fuente
    assert find_banned_imports(fuente, "app/core/locks.py") == []


def test_el_analizador_respeta_core_crypto() -> None:
    assert is_allowed((APP / "core" / "crypto" / "bus.py").relative_to(SRC).as_posix())
    assert is_allowed((APP / "core" / "security.py").relative_to(SRC).as_posix())
    assert not is_allowed((APP / "core" / "audit.py").relative_to(SRC).as_posix())
    assert not is_allowed("app/modules/members/service.py")
