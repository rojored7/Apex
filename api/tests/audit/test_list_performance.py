"""Rendimiento de la lista de auditoría (S4A-B4, US-102; S4A-D16). Marcada `perf`: no es gate (`-m
"not perf"`); se corre aparte con `uv run pytest -m perf tests/audit/test_list_performance.py -q`
y sus tiempos van al cuaderno.

100.000 filas (`make_audit_chain`, dentro de la transacción de la prueba): 50.000 de
`members.members` por `SYSTEM_USER_ID` y 50.000 de `plans.plans` por un usuario real (`ana`).
Tras un calentamiento, `list_entries` con `limit=25` responde en menos de 500 ms sin filtros,
con filtro de tabla, de usuario y de los dos; el `count(*)` con el mismo filtro se mide aparte
(si fallara solo él, S4A-D16 permite `max(seq)` sin filtros). Los índices ya existen
(`ix_audit_log_table_seq`, `ix_audit_log_user_id`, ...): no hay migración.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.dialects import postgresql

from app.core.audit import AuditEntry
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.core.pagination import PageParams
from app.modules.audit.schemas import MAX_AUDIT_OFFSET, AuditListQuery
from tests.audit.conftest import CadenaDePrueba, audit_service
from tests.conftest import UsuarioPrueba

pytestmark = pytest.mark.perf

MITAD = 50_000
TOPE_MS = 500
PAGINA = PageParams(limit=25)
ANALIZAR = text("ANALYZE audit.audit_log")


@pytest.fixture
async def cien_mil(
    audit_chain_factory: CadenaDePrueba, reloj: FrozenClock, ana: UsuarioPrueba
) -> CadenaDePrueba:
    base = await audit_chain_factory.last_seq()
    await audit_chain_factory.make(MITAD, table_name="members.members", user_id=SYSTEM_USER_ID)
    await audit_chain_factory.make(MITAD, table_name="plans.plans", user_id=ana.id)
    assert await audit_chain_factory.last_seq() == base + 2 * MITAD
    return audit_chain_factory


async def _medir_ms(cadena: CadenaDePrueba, datos: dict[str, Any]) -> tuple[float, int]:
    consulta = AuditListQuery(**datos)
    await audit_service.list_entries(cadena.session, consulta, PAGINA)  # calentamiento
    inicio = time.perf_counter()
    pagina = await audit_service.list_entries(cadena.session, consulta, PAGINA)
    return (time.perf_counter() - inicio) * 1000, len(pagina.items)


@pytest.mark.parametrize(
    "filtro",
    ["sin-filtros", "tabla", "usuario", "tabla-y-usuario"],
)
async def test_la_lista_de_25_baja_de_500_ms(
    cien_mil: CadenaDePrueba, ana: UsuarioPrueba, filtro: str
) -> None:
    datos: dict[str, Any] = {
        "sin-filtros": {},
        "tabla": {"table": "members.members"},
        "usuario": {"user_id": ana.id},
        "tabla-y-usuario": {"table": "plans.plans", "user_id": ana.id},
    }[filtro]
    ms, filas = await _medir_ms(cien_mil, datos)
    print(f"lista {filtro}: {ms:.1f} ms")
    assert filas == 25
    assert ms < TOPE_MS, ms


@pytest.mark.parametrize("con_filtro", [False, True], ids=["total", "tabla"])
async def test_el_count_se_mide_aparte(cien_mil: CadenaDePrueba, con_filtro: bool) -> None:
    consulta = select(func.count()).select_from(AuditEntry)
    if con_filtro:
        consulta = consulta.where(AuditEntry.table_name == "members.members")
    await cien_mil.session.scalar(consulta)
    inicio = time.perf_counter()
    total = await cien_mil.session.scalar(consulta)
    ms = (time.perf_counter() - inicio) * 1000
    print(f"count(*) {'con tabla' if con_filtro else 'sin filtros'}: {ms:.1f} ms")
    assert int(total or 0) >= MITAD
    assert ms < TOPE_MS, ms


async def test_el_conteo_de_tabla_y_registro_usa_el_indice_table_record(
    cien_mil: CadenaDePrueba,
) -> None:
    """S4A-D106 a: `record_id` siempre llega con `table`, así el conteo acotado de `paginate`
    (subconsulta con `LIMIT MAX_AUDIT_OFFSET + 1`) usa `ix_audit_log_table_record`."""
    session = cien_mil.session
    registro = await session.scalar(
        select(AuditEntry.record_id).where(AuditEntry.table_name == "plans.plans").limit(1)
    )
    assert registro is not None
    await session.execute(ANALIZAR)
    filtrada = (
        select(AuditEntry)
        .where(AuditEntry.table_name == "plans.plans", AuditEntry.record_id == registro)
        .order_by(None)
        .limit(MAX_AUDIT_OFFSET + 1)
    )
    conteo = select(func.count()).select_from(filtrada.subquery())
    sql = str(conteo.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    plan = "\n".join((await session.execute(text("EXPLAIN " + sql))).scalars().all())
    print(plan)
    assert "ix_audit_log_table_record" in plan, plan
    assert "Seq Scan" not in plan, plan

    pagina = await audit_service.list_entries(
        session, AuditListQuery(table="plans.plans", record_id=registro), PAGINA
    )
    assert (len(pagina.items), pagina.total) == (1, 1)
