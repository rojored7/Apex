"""S9-V8 (revisión): la lista «Entidad» de la pantalla Auditoría es la de `AUDITABLE_TABLES`.

`AUDIT_TABLES` de `web/src/features/system/auditFilters.ts` se quedó en la lista de v0.1 cinco
versiones: `?table=athletes.body_metrics` se descartaba de la URL y la Auditoría no podía filtrar
las tablas nuevas. Esta prueba lee el archivo del front y falla si una tabla auditada falta en la
lista o si la lista trae una que el api no audita (el api daría 422)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from app.modules.audit.queries import AUDITABLE_TABLES

REPO_ROOT: Final = Path(__file__).resolve().parents[3]
AUDIT_FILTERS_TS: Final = REPO_ROOT / "web" / "src" / "features" / "system" / "auditFilters.ts"
BLOQUE: Final = re.compile(r"export const AUDIT_TABLES[^=]*=\s*\[(?P<cuerpo>.*?)\];", re.DOTALL)
VALOR: Final = re.compile(r'value:\s*"(?P<tabla>[a-z_]+\.[a-z_]+)"')


def tablas_del_front(texto: str) -> set[str]:
    bloque = BLOQUE.search(texto)
    assert bloque is not None, "no encontré `export const AUDIT_TABLES = [...]` en auditFilters.ts"
    return {m["tabla"] for m in VALOR.finditer(bloque["cuerpo"])}


def test_la_lista_del_front_es_la_de_auditable_tables() -> None:
    front = tablas_del_front(AUDIT_FILTERS_TS.read_text(encoding="utf-8"))
    assert sorted(AUDITABLE_TABLES - front) == [], "tablas auditadas que la pantalla no ofrece"
    assert sorted(front - AUDITABLE_TABLES) == [], "tablas de la pantalla que el api no audita"


def test_el_lector_encuentra_las_tablas_y_solo_las_del_bloque() -> None:
    texto = (
        'const OTRA = [{ value: "x.y" }];\n'
        "export const AUDIT_TABLES: readonly { value: string }[] = [\n"
        '  { value: "members.members", label: "Socio" },\n'
        '  { value: "plans.plans", label: "Plan" },\n'
        "];\n"
    )
    assert tablas_del_front(texto) == {"members.members", "plans.plans"}
