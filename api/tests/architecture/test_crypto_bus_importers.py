"""Quién importa `app.core.crypto.bus` y `app.core.crypto.types` fuera de `core/` (S4A-B6;
S4A-D21, C7; blueprint B6).

Por AST sobre `src/app` (también imports dentro de funciones y `importlib.import_module` con una
cadena literal). Los importadores reales, calculados con grep al abrir B6 y fijados aquí, son:
- `modules/members/service.py` y `changes.py` (`bus`: índices ciegos y cifrado del documento);
- `modules/members/detail.py` (`types`: la única puerta `_decrypt_fields`) y `models.py`
  (`types`: los tipos de columna `Encrypted` y `BlindIndexed`);
- el arranque: `main.py`, `cli_base.py` (S4B-D30) y `worker/runtime.py`, que solo importan
  `install_crypto_type_listeners` de `types` (cablean los listeners al crear el proceso).

Lista blanca: `app.core.*`, `app.modules.members.*`, `athletes` y `attachments` cuando existan
(v0.3 y v0.6), y el arranque con ese único nombre. `members/contact.py` no entra: descifra por
`detail._decrypt_fields` y nunca importa el bus (S4A-D21). Control con una fuente falsa en
`notifications`, que debe fallar.

Revisión de B6 (`security-reviewer` LOW): los imports relativos (`from ..core.crypto import bus`)
se resuelven contra el paquete del archivo, y el acceso por atributo `.bus` o `.types` sobre
`app.core.crypto` importado como módulo (`import app.core.crypto as c; c.bus`, `from app.core
import crypto; crypto.types`, `import app.core.crypto; app.core.crypto.bus`) cuenta como importar
el módulo entero.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

APP: Final = Path(__file__).resolve().parents[2] / "src" / "app"
PAQUETE: Final = "app.core.crypto"
RECOVERY: Final = f"{PAQUETE}.recovery"
VIGILADOS: Final = frozenset({f"{PAQUETE}.bus", f"{PAQUETE}.types", RECOVERY})
INSTALADOR: Final = "install_crypto_type_listeners"

IMPORTADORES_REALES: Final = frozenset(
    {
        "cli_base.py",
        "cli_manifest.py",
        "main.py",
        "worker/jobs/backup_check.py",
        "worker/jobs/notify.py",
        "worker/runtime.py",
        "modules/members/changes.py",
        "modules/members/detail.py",
        "modules/members/models.py",
        "modules/members/service.py",
    }
)
ARRANQUE: Final = frozenset({"cli_base.py", "main.py", "worker/runtime.py"})
ARRANQUE_CON_RECOVERY: Final = frozenset({"main.py", "worker/runtime.py"})
"""S5-B3 (S5-D16, S5-D20): el arranque del api (sondeo) y el del worker (`with_crypto`) importan
`recovery` y solo los nombres de `NOMBRES_DE_RECOVERY`; `cli_base.py` no."""
NOMBRES_DE_RECOVERY: Final = frozenset(
    {"try_load", "poll_forever", "is_loaded", "observe", "reset"}
)  # S5-D198, S5-D202
SOLO_FIRMA: Final = frozenset({"cli_manifest.py", "worker/jobs/backup_check.py"})
"""S5-B13 (S5-D72): verifican la firma del manifiesto por el bus y nada más; el único nombre
que pueden importar de `bus` es `verified_manifest_bytes`."""
PUERTA_DE_FIRMA: Final = "verified_manifest_bytes"
SOLO_RECOVERY: Final = frozenset({"worker/jobs/notify.py"})
"""S5-B8 (S5-D16): el job `notify` llama `recovery.try_load` al comienzo; importa el módulo
`recovery` (las pruebas lo espían por ese nombre) y nada más del bus."""
PREFIJOS_PERMITIDOS: Final = (
    "core/",
    "modules/members/",
    "modules/athletes/",
    "modules/attachments/",
)


def _absoluto(nodo: ast.ImportFrom, paquete: str) -> str:
    """El módulo de un `from ... import` con los relativos resueltos contra `paquete`."""
    if nodo.level == 0:
        return nodo.module or ""
    partes = paquete.split(".")
    base = partes[: len(partes) - (nodo.level - 1)]
    return ".".join([*base, nodo.module] if nodo.module else base)


def _dotted(nodo: ast.expr) -> str | None:
    """`a.b.c` de una cadena de atributos sobre un nombre; `None` si no lo es."""
    if isinstance(nodo, ast.Name):
        return nodo.id
    if isinstance(nodo, ast.Attribute):
        cabeza = _dotted(nodo.value)
        return None if cabeza is None else f"{cabeza}.{nodo.attr}"
    return None


def _alias_del_paquete(arbol: ast.Module, paquete: str) -> set[str]:
    """Nombres locales ligados a `app.core.crypto` como módulo, más su ruta completa."""
    alias = {PAQUETE}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            alias.update(a.asname for a in nodo.names if a.name == PAQUETE and a.asname)
        elif isinstance(nodo, ast.ImportFrom):
            modulo = _absoluto(nodo, paquete)
            for a in nodo.names:
                if f"{modulo}.{a.name}" == PAQUETE:
                    alias.add(a.asname or a.name)
    return alias


def _vistas_de_import(nodo: ast.AST, paquete: str) -> list[tuple[str, str]]:
    """Pares `(módulo vigilado, nombre)` de un nodo de import o de `import_module`."""
    if isinstance(nodo, ast.ImportFrom):
        modulo = _absoluto(nodo, paquete)
        if modulo == PAQUETE:
            vigilados = (f"{PAQUETE}.{a.name}" for a in nodo.names)
            return [(m, "*") for m in vigilados if m in VIGILADOS]
        return [(modulo, a.name) for a in nodo.names] if modulo in VIGILADOS else []
    if isinstance(nodo, ast.Import):
        return [(a.name, "*") for a in nodo.names if a.name in VIGILADOS]
    if (
        isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and nodo.func.attr == "import_module"
        and nodo.args
        and isinstance(nodo.args[0], ast.Constant)
        and nodo.args[0].value in VIGILADOS
    ):
        return [(str(nodo.args[0].value), "*")]
    return []


def importaciones(fuente: str, paquete: str = "app") -> dict[str, set[str]]:
    """`{módulo vigilado: nombres importados}`; `"*"` cuando se importa el módulo entero.
    `paquete` es el paquete del archivo (para resolver los imports relativos)."""
    arbol = ast.parse(fuente)
    alias = _alias_del_paquete(arbol, paquete)
    vistas: dict[str, set[str]] = {}
    for nodo in ast.walk(arbol):
        for modulo, nombre in _vistas_de_import(nodo, paquete):
            vistas.setdefault(modulo, set()).add(nombre)
        if isinstance(nodo, ast.Attribute) and _dotted(nodo.value) in alias:
            modulo = f"{PAQUETE}.{nodo.attr}"
            if modulo in VIGILADOS:
                vistas.setdefault(modulo, set()).add("*")
    return vistas


def _paquete_de(relativo: str) -> str:
    """`modules/members/detail.py` -> `app.modules.members`."""
    return ".".join(["app", *Path(relativo).parent.parts])


def permitido(relativo: str, vistas: dict[str, set[str]]) -> bool:
    if relativo.startswith(PREFIJOS_PERMITIDOS):
        return True
    if relativo in SOLO_RECOVERY:
        return set(vistas) == {RECOVERY} and vistas[RECOVERY] <= NOMBRES_DE_RECOVERY | {"*"}
    if relativo in SOLO_FIRMA:
        return vistas == {f"{PAQUETE}.bus": {PUERTA_DE_FIRMA}}
    if relativo in ARRANQUE:
        propias = dict(vistas)
        recuperacion = propias.pop(RECOVERY, None)
        if recuperacion is not None and not (
            relativo in ARRANQUE_CON_RECOVERY and recuperacion <= NOMBRES_DE_RECOVERY
        ):
            return False
        return set(propias) == {f"{PAQUETE}.types"} and propias[f"{PAQUETE}.types"] == {INSTALADOR}
    return False


def _importadores() -> dict[str, dict[str, set[str]]]:
    salida: dict[str, dict[str, set[str]]] = {}
    for archivo in sorted(APP.rglob("*.py")):
        relativo = archivo.relative_to(APP).as_posix()
        if relativo.startswith("core/"):
            continue
        vistas = importaciones(archivo.read_text(encoding="utf-8"), _paquete_de(relativo))
        if vistas:
            salida[relativo] = vistas
    return salida


def test_los_importadores_fuera_de_core_son_exactamente_los_fijados() -> None:
    assert set(_importadores()) == IMPORTADORES_REALES


def test_todo_importador_esta_en_la_lista_blanca() -> None:
    malos = [r for r, vistas in _importadores().items() if not permitido(r, vistas)]
    assert malos == [], malos


def test_el_arranque_solo_importa_el_instalador_de_types() -> None:
    importadores = _importadores()
    for relativo in ARRANQUE:
        propias = {m: n for m, n in importadores[relativo].items() if m != RECOVERY}
        assert propias == {f"{PAQUETE}.types": {INSTALADOR}}, relativo


def test_members_contact_no_importa_el_bus_ni_types() -> None:
    """S4A-D21: el contacto descifra solo por `detail._decrypt_fields` (única puerta)."""
    archivo = APP / "modules" / "members" / "contact.py"
    assert archivo.is_file()
    assert importaciones(archivo.read_text(encoding="utf-8")) == {}


# Controles del analizador ------------------------------------------------------------------------

FUENTE_NOTIFICACIONES = """
from app.core.crypto import bus
import app.core.crypto.types as tipos
from app.core.crypto.types import reveal

def abrir():
    import importlib
    return importlib.import_module("app.core.crypto.bus")
"""


def test_control_una_fuente_falsa_en_notifications_falla() -> None:
    vistas = importaciones(FUENTE_NOTIFICACIONES)
    assert vistas == {
        f"{PAQUETE}.bus": {"*"},
        f"{PAQUETE}.types": {"*", "reveal"},
    }
    assert not permitido("modules/notifications/service.py", vistas)


def test_control_el_arranque_con_otro_nombre_falla_y_la_lista_blanca_pasa() -> None:
    con_bus = importaciones("from app.core.crypto import bus\n")
    assert not permitido("main.py", con_bus)
    otro = importaciones("from app.core.crypto.types import reveal\n")
    assert not permitido("worker/runtime.py", otro)
    instalador = importaciones(f"from app.core.crypto.types import {INSTALADOR}\n")
    assert permitido("cli_base.py", instalador)
    assert permitido("modules/attachments/service.py", con_bus)
    assert permitido("modules/athletes/service.py", con_bus)
    assert not permitido("modules/payments/service.py", con_bus)
    assert importaciones("from app.core.crypto.secret import Secret\n") == {}


FUENTE_RELATIVA = """
from ...core.crypto import bus
from ...core.crypto.types import reveal
from ... import core
"""

FUENTE_POR_ATRIBUTO = """
import app.core.crypto as c
from app.core import crypto as cripto
import app.core.crypto

def abrir(blob):
    c.bus.decrypt(blob)
    app.core.crypto.types.reveal
    return cripto.types
"""

FUENTE_POR_ATRIBUTO_LIMPIA = """
import app.core.crypto as c
from app.core import crypto

def f(blob):
    return c.digest(blob), crypto.digest
"""


def test_control_los_imports_relativos_se_resuelven_contra_el_paquete() -> None:
    """Revisión de B6 (`security-reviewer` LOW): `from ...core.crypto import bus` desde
    `modules/notifications/` es `app.core.crypto.bus`."""
    paquete = _paquete_de("modules/notifications/service.py")
    assert paquete == "app.modules.notifications"
    vistas = importaciones(FUENTE_RELATIVA, paquete)
    assert vistas == {f"{PAQUETE}.bus": {"*"}, f"{PAQUETE}.types": {"reveal"}}
    assert not permitido("modules/notifications/service.py", vistas)
    assert importaciones("from .detail import _decrypt_fields", "app.modules.members") == {}


def test_control_el_acceso_por_atributo_al_paquete_cuenta_como_import() -> None:
    """Revisión de B6 (`security-reviewer` LOW): `c.bus`, `cripto.types` y
    `app.core.crypto.types` sobre el paquete importado como módulo."""
    vistas = importaciones(FUENTE_POR_ATRIBUTO)
    assert vistas == {f"{PAQUETE}.bus": {"*"}, f"{PAQUETE}.types": {"*"}}
    assert not permitido("modules/notifications/service.py", vistas)
    assert importaciones(FUENTE_POR_ATRIBUTO_LIMPIA) == {}


def test_control_una_fuente_falsa_en_imports_o_seed_que_importe_el_bus_falla() -> None:
    """S4B-B1: ningún archivo nuevo importa el bus (la lista de importadores no cambia)."""
    for relativo in ("imports/members_xlsx.py", "imports/report.py", "seed/apply.py"):
        con_bus = importaciones("from app.core.crypto import bus\n", _paquete_de(relativo))
        assert con_bus and not permitido(relativo, con_bus), relativo
        con_types = importaciones("from app.core.crypto.types import reveal\n")
        assert not permitido(relativo, con_types), relativo
    assert not any(r.startswith(("imports/", "seed/")) for r in IMPORTADORES_REALES)


def test_control_backup_check_importando_el_bus_falla_y_archive_no_es_el_bus() -> None:
    """S4B-B2: el job de respaldos no entra a la lista blanca; `archive` no es el bus."""
    con_bus = importaciones("from app.core.crypto import bus\n")
    assert not permitido("worker/jobs/backup_check.py", con_bus)
    con_types = importaciones("from app.core.crypto.types import reveal\n")
    assert not permitido("worker/jobs/backup_check.py", con_types)
    assert importaciones("from app.core.crypto.archive import digest_file\n") == {}


def test_backup_status_no_importa_el_bus() -> None:
    fuente = (APP / "core/backup_status.py").read_text(encoding="utf-8")
    assert importaciones(fuente) == {}


def test_backup_check_y_cli_manifest_importan_del_bus_solo_verified_manifest_bytes() -> None:
    """S5-B13 (S5-D72): la firma se verifica por el bus, la única puerta; ni `types` ni otro
    nombre del bus. Cambia el Sprint 4B: `backup_check` ya no queda fuera del todo."""
    for relativo in sorted(SOLO_FIRMA):
        fuente = (APP / relativo).read_text(encoding="utf-8")
        assert importaciones(fuente, _paquete_de(relativo)) == {
            f"{PAQUETE}.bus": {PUERTA_DE_FIRMA}
        }, relativo


def test_control_la_firma_solo_admite_verified_manifest_bytes() -> None:
    bien = importaciones("from app.core.crypto.bus import verified_manifest_bytes\n")
    assert permitido("cli_manifest.py", bien)
    assert permitido("worker/jobs/backup_check.py", bien)
    for fuente in (
        "from app.core.crypto import bus\n",
        "from app.core.crypto.bus import digest\n",
        "from app.core.crypto.bus import verified_manifest_bytes, decrypt\n",
        "from app.core.crypto.types import reveal\n",
    ):
        assert not permitido("cli_manifest.py", importaciones(fuente)), fuente
        assert not permitido("worker/jobs/backup_check.py", importaciones(fuente)), fuente
    assert not permitido("cli_ops/retire_key.py", bien)


def _importa_minisign(fuente: str, paquete: str) -> bool:
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.ImportFrom):
            modulo = _absoluto(nodo, paquete)
            if modulo == f"{PAQUETE}.minisign" or (
                modulo == PAQUETE and any(a.name == "minisign" for a in nodo.names)
            ):
                return True
        elif isinstance(nodo, ast.Import) and any(
            a.name == f"{PAQUETE}.minisign" for a in nodo.names
        ):
            return True
    return False


def test_minisign_solo_lo_importa_el_bus() -> None:
    """`core/crypto/minisign.py` es detalle del bus (S5-D72): ningún otro archivo del api lo
    importa, ni siquiera dentro de `core/`."""
    importadores = {
        archivo.relative_to(APP).as_posix()
        for archivo in sorted(APP.rglob("*.py"))
        if _importa_minisign(
            archivo.read_text(encoding="utf-8"), _paquete_de(archivo.relative_to(APP).as_posix())
        )
    }
    assert importadores == {"core/crypto/bus.py"}


def test_control_importar_minisign_se_detecta() -> None:
    assert _importa_minisign("from app.core.crypto.minisign import verify_minisign\n", "app")
    assert _importa_minisign("from app.core.crypto import minisign\n", "app")
    assert _importa_minisign("from .minisign import x\n", "app.core.crypto")
    assert not _importa_minisign("from app.core.crypto import bus\n", "app")


# S5-B1: `openbao_provider` solo lo importan los archivos de `core/crypto/` ----------------------

PROVEEDOR: Final = f"{PAQUETE}.openbao_provider"


def importa_el_proveedor(fuente: str, paquete: str = "app") -> bool:
    """Import directo, relativo, `from app.core.crypto import openbao_provider`, acceso por
    atributo sobre el paquete o `import_module` con cadena literal."""
    arbol = ast.parse(fuente)
    alias = _alias_del_paquete(arbol, paquete)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom):
            modulo = _absoluto(nodo, paquete)
            if modulo == PROVEEDOR or (
                modulo == PAQUETE and any(a.name == "openbao_provider" for a in nodo.names)
            ):
                return True
        elif isinstance(nodo, ast.Import):
            if any(a.name == PROVEEDOR for a in nodo.names):
                return True
        elif isinstance(nodo, ast.Call) and nodo.args and isinstance(nodo.args[0], ast.Constant):
            if nodo.args[0].value == PROVEEDOR:
                return True
        elif isinstance(nodo, ast.Attribute) and nodo.attr == "openbao_provider":
            if _dotted(nodo.value) in alias:
                return True
    return False


def _importadores_del_proveedor() -> set[str]:
    return {
        archivo.relative_to(APP).as_posix()
        for archivo in sorted(APP.rglob("*.py"))
        if importa_el_proveedor(
            archivo.read_text(encoding="utf-8"), _paquete_de(archivo.relative_to(APP).as_posix())
        )
    }


def test_openbao_provider_solo_lo_importan_archivos_de_core_crypto() -> None:
    fuera = sorted(r for r in _importadores_del_proveedor() if not r.startswith("core/crypto/"))
    assert fuera == [], fuera


def test_openbao_provider_tiene_al_menos_un_importador_en_core_crypto() -> None:
    """Sin esto la regla anterior no vigilaría nada: `provider.get_provider_named` lo construye
    (import perezoso) y el Verde lo cablea."""
    assert _importadores_del_proveedor(), "nadie importa openbao_provider todavía"


@pytest.mark.parametrize(
    "fuente",
    [
        "from app.core.crypto.openbao_provider import OpenBaoProvider\n",
        "from app.core.crypto import openbao_provider\n",
        "import app.core.crypto.openbao_provider\n",
        "import importlib\nimportlib.import_module('app.core.crypto.openbao_provider')\n",
        "import app.core.crypto as c\nc.openbao_provider.OpenBaoProvider\n",
    ],
)
def test_control_importar_el_proveedor_desde_un_modulo_se_detecta(fuente: str) -> None:
    assert importa_el_proveedor(fuente)


def test_control_importes_relativos_y_ajenos() -> None:
    assert importa_el_proveedor("from ...core.crypto import openbao_provider\n", "app.modules.x")
    assert importa_el_proveedor("from .openbao_provider import KEK_KEY\n", "app.core.crypto")
    assert not importa_el_proveedor("from app.core.crypto.provider import KeyProvider\n")
    assert not importa_el_proveedor("from app.core.crypto import digest\n")


# S5-B3: el arranque suma `core.crypto.recovery` (S5-D16, S5-D20) -------------------------------


def test_s5_b3_el_arranque_del_api_y_del_worker_importan_recovery() -> None:
    """`main.py` lanza el sondeo (`poll_forever`) y `worker/runtime.py` carga con `try_load`
    (`with_crypto`); `cli_base.py` no importa `recovery`."""
    importadores = _importadores()
    assert RECOVERY in importadores["main.py"], "main.py no importa core.crypto.recovery"
    assert RECOVERY in importadores["worker/runtime.py"], "runtime.py no importa recovery"
    assert RECOVERY not in importadores["cli_base.py"]


def test_s5_b3_nadie_mas_importa_recovery() -> None:
    otros = {
        r: v[RECOVERY]
        for r, v in _importadores().items()
        if RECOVERY in v and r not in ARRANQUE_CON_RECOVERY | SOLO_RECOVERY
    }
    assert otros == {}


def test_control_recovery_en_otro_archivo_o_con_otro_nombre_falla() -> None:
    con_recovery = importaciones("from app.core.crypto.recovery import try_load, poll_forever\n")
    tipos = {f"{PAQUETE}.types": {INSTALADOR}}
    assert permitido("main.py", {**con_recovery, **tipos})
    assert not permitido("cli_base.py", {**con_recovery, **tipos})
    assert not permitido("modules/notifications/service.py", con_recovery)
    otro_nombre = importaciones("from app.core.crypto.recovery import current_state\n")
    assert not permitido("worker/runtime.py", {**otro_nombre, **tipos})


def test_s5_b8_el_job_notify_importa_recovery_y_nada_mas_del_bus() -> None:
    """# Rojo B8: la enmienda es de UN archivo; el job no cifra ni descifra por su cuenta."""
    importadores = _importadores()
    assert set(importadores["worker/jobs/notify.py"]) == {RECOVERY}
    assert permitido("worker/jobs/notify.py", importadores["worker/jobs/notify.py"])
    con_bus = importaciones(
        "from app.core.crypto import bus\nfrom app.core.crypto import recovery\n"
    )
    assert not permitido("worker/jobs/notify.py", con_bus)
    assert not permitido(
        "worker/jobs/expirations.py", importaciones("from app.core.crypto import recovery\n")
    )
