"""Quién importa la capa de aplicación del CLI (S4B-B0; S4B-D28, D30, D62, D76).

La capa de aplicación (`cli.py`, `cli_base.py`, `cli_ops/`, `seed/`, `imports/`) cuelga de
`cli.py`; nada de lo demás depende de ella. Por AST sobre `src/app` (también imports dentro de
funciones, relativos resueltos y `from app import cli_ops`):

- `app.cli_ops`, `app.seed` y `app.imports` solo los importan `cli.py` y los propios paquetes
  (`cli_ops/**`, `seed/**`, `imports/**`); nunca `main.py`, un `router.py`, `core/`, `worker/`
  ni un módulo de negocio;
- `app.cli` y `app.cli_base` solo los importan `cli.py` y los propios paquetes; `cli_ops/**`
  nunca importa `app.cli` (ciclo: S4B-D29);
- los archivos de `cli_ops/` no se importan entre sí: la base común es `cli_base` (solo
  `cli_ops/__init__.py` importa a sus hermanos para `register_ops`);
- `cli_ops/**`, `seed/**` e `imports/**` no importan `core.crypto.bus` ni `core.crypto.types`
  (el único arranque del cifrado es `cli_base.py`, S4B-D30);
- `cli_base.py` no importa `app.modules.<x>.models` ni `router` (C4);
- `cli_ops/kek.py` (B3a) no usa `crypto_runtime` ni `ensure_keys` (S4B-D62: restaurar es la
  operación para cuando la KEK no está; `ensure_keys` crearía llaves con una KEK equivocada).
  La regla tolera la ausencia del archivo.
- S5-B13 (S5-D72): `app/cli_manifest.py` (firma del manifiesto) solo lo importan archivos de
  `cli_ops/`, nunca `cli.py`, `worker/`, `core/` ni un módulo; y él mismo no importa la capa
  (`app.cli`, `app.cli_base`, `app.cli_ops`).
Controles con fuentes falsas: cada regla debe fallar ante su violación.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from tests.architecture.test_crypto_bus_importers import importaciones as importa_el_bus

SRC: Final = Path(__file__).resolve().parents[2] / "src" / "app"
PAQUETES_PROPIOS: Final = ("cli_ops", "seed", "imports")
RAIZ_DE_LA_CAPA: Final = ("app.cli_ops", "app.seed", "app.imports", "app.cli_base", "app.cli")
USOS_PROHIBIDOS_EN_KEK: Final = ("crypto_runtime", "ensure_keys")


def _paquete_de(relativo: str) -> str:
    """`cli_ops/keys.py` -> `app.cli_ops`; `cli.py` -> `app`."""
    return ".".join(["app", *Path(relativo).parent.parts])


def modulos_importados(fuente: str, relativo: str) -> set[str]:
    """Nombres de módulo importados (relativos resueltos). `from app import cli_ops` aporta
    `app.cli_ops`."""
    paquete = _paquete_de(relativo).split(".")
    salida: set[str] = set()
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Import):
            salida.update(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            base = paquete[: len(paquete) - (nodo.level - 1)] if nodo.level else []
            modulo = ".".join([*base, nodo.module] if nodo.module else base)
            salida.add(modulo)
            salida.update(f"{modulo}.{a.name}" for a in nodo.names)
    return salida


def _es_o_cuelga_de(modulo: str, raiz: str) -> bool:
    return modulo == raiz or modulo.startswith(f"{raiz}.")


def importadores_de(fuente: str, relativo: str, raices: tuple[str, ...]) -> set[str]:
    """Las `raices` (p. ej. `app.cli_ops`) que `fuente` importa, directa o por submódulo."""
    vistos = modulos_importados(fuente, relativo)
    return {r for r in raices if any(_es_o_cuelga_de(m, r) for m in vistos)}


def es_de_la_capa(relativo: str) -> bool:
    """`cli.py`, `cli_base.py` o un archivo bajo `cli_ops/`, `seed/` o `imports/`."""
    return relativo in {"cli.py", "cli_base.py"} or relativo.split("/")[0] in PAQUETES_PROPIOS


def violaciones_de_alcance(fuente: str, relativo: str) -> list[str]:
    """Quien no es de la capa e importa algo de ella (S4B-D76)."""
    if es_de_la_capa(relativo):
        return []
    return sorted(importadores_de(fuente, relativo, RAIZ_DE_LA_CAPA))


def violaciones_entre_hermanos(fuente: str, relativo: str) -> list[str]:
    """Un archivo de `cli_ops/` (salvo `__init__.py`) que importa a un hermano o a `app.cli`."""
    if not relativo.startswith("cli_ops/") or relativo == "cli_ops/__init__.py":
        return []
    return sorted(importadores_de(fuente, relativo, ("app.cli_ops", "app.cli")))


def violaciones_del_bus(fuente: str, relativo: str) -> list[str]:
    """`cli_ops/**`, `seed/**` e `imports/**` no importan `core.crypto.bus` ni `types`."""
    if relativo.split("/")[0] not in PAQUETES_PROPIOS:
        return []
    return sorted(importa_el_bus(fuente, _paquete_de(relativo)))


def importa_models_o_router(fuente: str, relativo: str) -> list[str]:
    encontrados = {
        ".".join(m.split(".")[:4])
        for m in modulos_importados(fuente, relativo)
        if m.startswith("app.modules.") and m.split(".")[3:4] in (["models"], ["router"])
    }
    return sorted(encontrados)


def usos_prohibidos_en_kek(fuente: str) -> list[str]:
    nombres = {n.id for n in ast.walk(ast.parse(fuente)) if isinstance(n, ast.Name)}
    nombres |= {n.attr for n in ast.walk(ast.parse(fuente)) if isinstance(n, ast.Attribute)}
    nombres |= {
        a.name
        for n in ast.walk(ast.parse(fuente))
        if isinstance(n, ast.ImportFrom)
        for a in n.names
    }
    return sorted(n for n in USOS_PROHIBIDOS_EN_KEK if n in nombres)


def violaciones_de_cli_manifest(fuente: str, relativo: str) -> list[str]:
    """Quien no es de `cli_ops/` e importa `app.cli_manifest` (S5-D72)."""
    if relativo.startswith("cli_ops/") or relativo == "cli_manifest.py":
        return []
    return sorted(importadores_de(fuente, relativo, ("app.cli_manifest",)))


def _archivos() -> list[tuple[str, str]]:
    return [
        (p.relative_to(SRC).as_posix(), p.read_text(encoding="utf-8"))
        for p in sorted(SRC.rglob("*.py"))
    ]


# Reglas sobre el árbol real -------------------------------------------------------------------


def test_la_capa_de_aplicacion_existe() -> None:
    relativos = {r for r, _ in _archivos()}
    assert {"cli.py", "cli_base.py", "cli_ops/__init__.py"} <= relativos


def test_nadie_fuera_de_la_capa_la_importa() -> None:
    malos = {r: v for r, f in _archivos() if (v := violaciones_de_alcance(f, r))}
    assert malos == {}, malos


def test_cli_py_importa_cli_base_y_cli_ops() -> None:
    fuente = (SRC / "cli.py").read_text(encoding="utf-8")
    assert importadores_de(fuente, "cli.py", RAIZ_DE_LA_CAPA) >= {"app.cli_base", "app.cli_ops"}


def test_seed_e_imports_existen_y_solo_los_importa_su_comando_de_cli_ops() -> None:
    """S4B-B1 (S4B-D76): `app.seed` solo lo importa `cli_ops/seed_demo.py` y `app.imports` solo
    `cli_ops/import_members.py` (más los propios paquetes); ni `cli.py` ni nadie más."""
    archivos = _archivos()
    relativos = {r for r, _ in archivos}
    assert {
        "seed/apply.py",
        "seed/dataset.py",
        "imports/members_xlsx.py",
        "imports/report.py",
        "cli_ops/seed_demo.py",
        "cli_ops/import_members.py",
    } <= relativos
    de_seed = {
        r for r, f in archivos if not r.startswith("seed/") and importadores_de(f, r, ("app.seed",))
    }
    de_imports = {
        r
        for r, f in archivos
        if not r.startswith("imports/") and importadores_de(f, r, ("app.imports",))
    }
    assert de_seed == {"cli_ops/seed_demo.py"}, de_seed
    assert de_imports == {"cli_ops/import_members.py"}, de_imports


def test_seed_e_imports_no_importan_cli_ni_cli_ops() -> None:
    """La capa cuelga de `cli.py`: sus paquetes de lógica nunca la importan de vuelta (ciclo)."""
    malos = {
        r: v
        for r, f in _archivos()
        if r.split("/")[0] in ("seed", "imports")
        and (v := importadores_de(f, r, ("app.cli", "app.cli_ops")))
    }
    assert malos == {}, malos


def test_los_archivos_de_cli_ops_no_se_importan_entre_si_ni_importan_cli() -> None:
    malos = {r: v for r, f in _archivos() if (v := violaciones_entre_hermanos(f, r))}
    assert malos == {}, malos


def test_la_capa_no_importa_el_bus_de_cifrado_salvo_cli_base() -> None:
    malos = {r: v for r, f in _archivos() if (v := violaciones_del_bus(f, r))}
    assert malos == {}, malos
    base = (SRC / "cli_base.py").read_text(encoding="utf-8")
    assert set(importa_el_bus(base, "app")) == {"app.core.crypto.types"}


def test_cli_base_no_importa_models_ni_router_de_los_modulos() -> None:
    fuente = (SRC / "cli_base.py").read_text(encoding="utf-8")
    assert importa_models_o_router(fuente, "cli_base.py") == []


def test_los_comandos_de_kek_no_usan_crypto_runtime_ni_ensure_keys() -> None:
    kek = SRC / "cli_ops" / "kek.py"
    if kek.is_file():
        assert usos_prohibidos_en_kek(kek.read_text(encoding="utf-8")) == []


def test_cli_manifest_existe_y_solo_lo_importan_archivos_de_cli_ops() -> None:
    archivos = _archivos()
    assert "cli_manifest.py" in {r for r, _ in archivos}
    malos = {r: v for r, f in archivos if (v := violaciones_de_cli_manifest(f, r))}
    assert malos == {}, malos
    importadores = {
        r
        for r, f in archivos
        if importadores_de(f, r, ("app.cli_manifest",)) and r != "cli_manifest.py"
    }
    assert importadores == {
        "cli_ops/retire_key.py",
        "cli_ops/migrate_provider.py",
        "cli_ops/rotate_kek.py",
        "cli_ops/retire_local_kek.py",
    }, importadores


def test_cli_manifest_no_importa_la_capa_de_aplicacion() -> None:
    fuente = (SRC / "cli_manifest.py").read_text(encoding="utf-8")
    assert importadores_de(fuente, "cli_manifest.py", RAIZ_DE_LA_CAPA) == set()


# Controles con fuentes falsas ------------------------------------------------------------------


def test_control_main_router_core_y_worker_importando_la_capa_fallan() -> None:
    for relativo in ("main.py", "modules/members/router.py", "core/jobs.py", "worker/main.py"):
        for fuente in (
            "from app.cli_ops import register_ops\n",
            "import app.seed\n",
            "from app import imports\n",
            "def f():\n    from app.cli_base import cli_runtime\n",
            "from app.cli import app\n",
        ):
            assert violaciones_de_alcance(fuente, relativo), (relativo, fuente)


def test_control_la_capa_misma_puede_importarse() -> None:
    assert violaciones_de_alcance("from app.cli_ops import register_ops\n", "cli.py") == []
    assert violaciones_de_alcance("from app.seed import apply\n", "cli_ops/seed_demo.py") == []
    assert violaciones_de_alcance("from app.cli_base import cli_runtime\n", "seed/apply.py") == []


def test_control_imports_relativos_se_resuelven() -> None:
    assert violaciones_de_alcance("from ..cli_ops import x\n", "worker/main.py") == ["app.cli_ops"]
    assert violaciones_de_alcance("from . import cli_ops\n", "main.py") == ["app.cli_ops"]
    assert violaciones_de_alcance("from .cli_base import x\n", "main.py") == ["app.cli_base"]


def test_control_un_hermano_de_cli_ops_o_cli_fallan() -> None:
    assert violaciones_entre_hermanos("from app.cli_ops import keys\n", "cli_ops/otro.py")
    assert violaciones_entre_hermanos("from app.cli_ops.keys import x\n", "cli_ops/otro.py")
    assert violaciones_entre_hermanos("from . import keys\n", "cli_ops/otro.py") == ["app.cli_ops"]
    assert violaciones_entre_hermanos("from app.cli import app\n", "cli_ops/otro.py")
    assert violaciones_entre_hermanos("from app.cli_base import x\n", "cli_ops/otro.py") == []
    assert violaciones_entre_hermanos("from app.cli_ops import keys\n", "cli_ops/__init__.py") == []


def test_control_el_bus_en_cli_ops_seed_o_imports_falla() -> None:
    for relativo in ("cli_ops/kek.py", "seed/apply.py", "imports/members_xlsx.py"):
        assert violaciones_del_bus("from app.core.crypto import bus\n", relativo)
        assert violaciones_del_bus("from app.core.crypto.types import reveal\n", relativo)
    assert violaciones_del_bus("from app.core.crypto.types import x\n", "cli_base.py") == []
    assert violaciones_del_bus("from app.core.crypto.secret import Secret\n", "seed/a.py") == []


def test_control_models_y_router_en_cli_base_fallan() -> None:
    falsa = "from app.modules.members.models import Member\nfrom app.modules.plans import router\n"
    assert importa_models_o_router(falsa, "cli_base.py") == [
        "app.modules.members.models",
        "app.modules.plans.router",
    ]
    assert importa_models_o_router("from app.modules.auth.service import x\n", "cli_base.py") == []


def test_control_kek_con_crypto_runtime_o_ensure_keys_falla() -> None:
    assert usos_prohibidos_en_kek("from app.cli_base import crypto_runtime\n") == ["crypto_runtime"]
    assert usos_prohibidos_en_kek("async def f(s, p):\n    await ensure_keys(s, p)\n") == [
        "ensure_keys"
    ]
    assert usos_prohibidos_en_kek("import app.cli_base as b\nb.crypto_runtime(s)\n") == [
        "crypto_runtime"
    ]
    fuente = "async def f(s):\n    async with cli_runtime(s) as sesion:\n        pass\n"
    assert usos_prohibidos_en_kek(fuente) == []


def test_control_cli_manifest_fuera_de_cli_ops_falla() -> None:
    for relativo in ("cli.py", "main.py", "worker/jobs/backup_check.py", "core/jobs.py"):
        for fuente in (
            "from app.cli_manifest import recent_signed_manifest\n",
            "import app.cli_manifest\n",
            "from app import cli_manifest\n",
        ):
            assert violaciones_de_cli_manifest(fuente, relativo) == ["app.cli_manifest"], (
                relativo,
                fuente,
            )
    assert violaciones_de_cli_manifest("from ..cli_manifest import x\n", "worker/main.py")


def test_control_cli_manifest_importado_desde_cli_ops_pasa() -> None:
    fuente = "from app.cli_manifest import recent_signed_manifest\n"
    assert violaciones_de_cli_manifest(fuente, "cli_ops/retire_key.py") == []
    assert violaciones_de_alcance(fuente, "cli_ops/retire_key.py") == []
