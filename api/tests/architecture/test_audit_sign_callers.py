"""Solo el worker y el CLI firman la auditoría (V11, revisión de seguridad L2; S6-D40, S6-D81).

Con `CRYPTO_PROVIDER=local` el api monta el volumen `keys` en solo lectura, incluida la llave de
firma; la barrera real es el grant (`apex_api` solo tiene SELECT en `audit.signatures`). Esta
prueba fija el lado del código: ningún módulo ni router del api llama `sign_latest` ni el
`sign` del bus. Los únicos llamadores de `sign_latest` son `worker/jobs/sign_audit.py` y
`cli_ops/sign_audit.py`; el `sign` del bus solo lo importa `core/audit_sign.py` (que lo usa
dentro de `sign_latest`) y lo que vive bajo `core/crypto/`.
Controles con fuentes falsas: cada regla debe fallar ante su violación.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

SRC: Final = Path(__file__).resolve().parents[2] / "src" / "app"
FIRMANTES: Final = frozenset({"worker/jobs/sign_audit.py", "cli_ops/sign_audit.py"})
DEFINIDOR: Final = "core/audit_sign.py"
BUS: Final = "app.core.crypto.bus"


def usa_sign_latest(fuente: str) -> bool:
    """Cualquier mención del nombre `sign_latest` (import, llamada o atributo)."""
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Name) and nodo.id == "sign_latest":
            return True
        if isinstance(nodo, ast.Attribute) and nodo.attr == "sign_latest":
            return True
        if isinstance(nodo, ast.alias) and nodo.name == "sign_latest":
            return True
    return False


def usa_sign_del_bus(fuente: str) -> bool:
    """`from app.core.crypto.bus import sign` o `bus.sign(...)` con el módulo importado."""
    arbol = ast.parse(fuente)
    alias_del_bus: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom):
            if nodo.module == BUS and any(a.name == "sign" for a in nodo.names):
                return True
            if nodo.module == "app.core.crypto":
                alias_del_bus |= {a.asname or a.name for a in nodo.names if a.name == "bus"}
        elif isinstance(nodo, ast.Import):
            alias_del_bus |= {a.asname or a.name for a in nodo.names if a.name == BUS}
    for nodo in ast.walk(arbol):
        if (
            isinstance(nodo, ast.Attribute)
            and nodo.attr == "sign"
            and isinstance(nodo.value, ast.Name)
            and nodo.value.id in alias_del_bus
        ):
            return True
    return False


def _archivos() -> list[tuple[str, str]]:
    return [
        (a.relative_to(SRC).as_posix(), a.read_text(encoding="utf-8"))
        for a in sorted(SRC.rglob("*.py"))
    ]


def test_solo_el_worker_y_el_cli_llaman_sign_latest() -> None:
    llamadores = {
        ruta for ruta, fuente in _archivos() if ruta != DEFINIDOR and usa_sign_latest(fuente)
    }
    assert llamadores == FIRMANTES


def test_solo_audit_sign_importa_el_sign_del_bus_fuera_de_core_crypto() -> None:
    usuarios = {
        ruta
        for ruta, fuente in _archivos()
        if not ruta.startswith("core/crypto/") and usa_sign_del_bus(fuente)
    }
    assert usuarios == {DEFINIDOR}


def test_ningun_modulo_ni_router_firma() -> None:
    for ruta, fuente in _archivos():
        if ruta.startswith("modules/") or ruta in {"main.py"}:
            assert not usa_sign_latest(fuente), ruta
            assert not usa_sign_del_bus(fuente), ruta


def test_control_las_fuentes_falsas_se_detectan() -> None:
    assert usa_sign_latest("from app.core.audit_sign import sign_latest\n")
    assert usa_sign_latest("from app.core import audit_sign\nawait audit_sign.sign_latest(s)\n")
    assert usa_sign_del_bus("from app.core.crypto.bus import sign as f\n")
    assert usa_sign_del_bus("from app.core.crypto import bus\nawait bus.sign('x', b'')\n")
    assert usa_sign_del_bus("import app.core.crypto.bus\n") is False
    assert not usa_sign_latest("from app.core.audit_sign import late_hours\n")
