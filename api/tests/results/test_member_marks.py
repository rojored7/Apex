"""`results.service.member_marks` (S9-B5, S9-D11, S9-D30): las marcas del socio como dato plano.

Vigentes y VALIDADAS de UN socio, por `wod_date`, `created_at` e `id` ascendentes, con filtros en
SQL (`benchmark_id`, `wod_ids`, `only_benchmarks`, `only_load`) y un tope `limit` que se queda
con las MÁS RECIENTES (devueltas en orden ascendente). Una consulta por
`ix_wod_results_member_date`, sin candados. Valores a mano, en gramos enteros (S8-D41).

Escena (socio S, `reloj` = 2026-10-21; todos los WODs comparten movimientos y principal):
- W1 `load` 2026-10-15: 80.000 g.   - W2 `load` 2026-10-17: 90.000 g.
- W3 benchmark `time` 2026-10-19: 300 s.   - W4 `load` 2026-10-20: 70.000 g corregido a 100.000 g.
- W5 `load` 2026-10-21: 60.000 g, anulado.   - Otro socio: 120.000 g en W1.
Vigentes de S, en orden: W1 80.000, W2 90.000, W3 300 s, W4 100.000.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.results import service
from app.modules.results.schemas import ResultMark, VoidIn
from tests.factories.explain import capturar_sql
from tests.factories.members import make_members
from tests.factories.wods import make_benchmark, make_wod
from tests.results._apoyo import Escena, escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


@dataclass
class Marcas:
    e: Escena
    otro: UUID
    benchmark_id: UUID
    w: dict[int, UUID]


async def _wod(session: AsyncSession, e: Escena, dia: str, titulo: str, **cambios: Any) -> UUID:
    cuerpo: dict[str, Any] = {
        "date": dia,
        "title": titulo,
        "score_type": "load",
        "time_cap_s": None,
    }
    cuerpo.update(cambios)
    return (await make_wod(session, e.coach, list(e.movimientos), **cuerpo)).id


async def _poner(session: AsyncSession, e: Escena, wod_id: UUID, **marca: Any) -> UUID:
    return (await registrar(session, dataclasses.replace(e, wod_id=wod_id), **marca)).id


@pytest.fixture
async def marcas(session: AsyncSession) -> Marcas:
    e = await escena(
        session, score_type="load", time_cap_s=None, fecha="2026-10-15", con_clase=False
    )
    bm = await make_benchmark(session, e.coach, name="Fran", score_type="time")
    w = {
        1: e.wod_id,
        2: await _wod(session, e, "2026-10-17", "W2"),
        3: await _wod(
            session, e, "2026-10-19", "W3", score_type="time", time_cap_s=600, benchmark_id=bm.id
        ),
        4: await _wod(session, e, "2026-10-20", "W4"),
        5: await _wod(session, e, "2026-10-21", "W5"),
    }
    await _poner(session, e, w[1], load_g=80_000, seconds=None)
    await _poner(session, e, w[2], load_g=90_000, seconds=None)
    await _poner(session, e, w[3], seconds=300)
    malo = await _poner(session, e, w[4], load_g=70_000, seconds=None)
    await _poner(session, e, w[4], load_g=100_000, seconds=None, supersedes_id=malo)
    anulado = await _poner(session, e, w[5], load_g=60_000, seconds=None)
    with actor_scope(e.coach):
        await service.void_result(session, anulado, VoidIn(reason="Socio equivocado"), by=e.coach)
    otro = (await make_members(session, 1))[0]
    ajeno = dataclasses.replace(e, socio_id=otro.id, socio=otro)
    await _poner(session, ajeno, w[1], load_g=120_000, seconds=None)
    return Marcas(e, otro.id, bm.id, w)


def _resumen(filas: list[ResultMark]) -> list[tuple[int | None, int | None]]:
    return [(m.load_g, m.seconds) for m in filas]


TODAS = [(80_000, None), (90_000, None), (None, 300), (100_000, None)]


async def test_devuelve_solo_las_vigentes_y_validadas_del_socio_en_orden_ascendente(
    session: AsyncSession, marcas: Marcas
) -> None:
    filas = await service.member_marks(session, marcas.e.socio_id)

    assert _resumen(filas) == TODAS
    assert [m.wod_date for m in filas] == [
        date(2026, 10, 15),
        date(2026, 10, 17),
        date(2026, 10, 19),
        date(2026, 10, 20),
    ]
    assert all(m.status == "validated" and m.is_current for m in filas)
    assert all(m.member_id == marcas.e.socio_id for m in filas)
    assert all(isinstance(m, ResultMark) for m in filas)


async def test_la_marca_corregida_trae_la_nueva_y_apunta_a_la_anterior(
    session: AsyncSession, marcas: Marcas
) -> None:
    filas = await service.member_marks(session, marcas.e.socio_id)

    cuarta = filas[3]
    assert cuarta.wod_id == marcas.w[4] and cuarta.load_g == 100_000
    assert cuarta.supersedes_id is not None
    assert all(m.supersedes_id is None for m in filas[:3])


async def test_el_otro_socio_ve_solo_lo_suyo(session: AsyncSession, marcas: Marcas) -> None:
    filas = await service.member_marks(session, marcas.otro)

    assert _resumen(filas) == [(120_000, None)]


async def test_un_socio_sin_marcas_da_lista_vacia(session: AsyncSession, marcas: Marcas) -> None:
    assert await service.member_marks(session, uuid4()) == []


async def test_only_load_deja_solo_las_marcas_con_carga(
    session: AsyncSession, marcas: Marcas
) -> None:
    filas = await service.member_marks(session, marcas.e.socio_id, only_load=True)

    assert _resumen(filas) == [(80_000, None), (90_000, None), (100_000, None)]


async def test_only_benchmarks_y_benchmark_id_filtran_por_el_benchmark(
    session: AsyncSession, marcas: Marcas
) -> None:
    solo = await service.member_marks(session, marcas.e.socio_id, only_benchmarks=True)
    por_id = await service.member_marks(
        session, marcas.e.socio_id, benchmark_id=marcas.benchmark_id
    )
    otro = await service.member_marks(session, marcas.e.socio_id, benchmark_id=uuid4())

    assert _resumen(solo) == [(None, 300)] == _resumen(por_id)
    assert solo[0].benchmark_id == marcas.benchmark_id
    assert otro == []


async def test_wod_ids_filtra_en_sql_y_la_coleccion_vacia_da_vacio(
    session: AsyncSession, marcas: Marcas
) -> None:
    pedidos: Collection[UUID] = {marcas.w[2], marcas.w[4], uuid4()}

    dos = await service.member_marks(session, marcas.e.socio_id, wod_ids=pedidos)
    vacio = await service.member_marks(session, marcas.e.socio_id, wod_ids=[])
    todos = await service.member_marks(session, marcas.e.socio_id, wod_ids=None)

    assert _resumen(dos) == [(90_000, None), (100_000, None)]
    assert vacio == []
    assert _resumen(todos) == TODAS


async def test_los_filtros_se_combinan(session: AsyncSession, marcas: Marcas) -> None:
    filas = await service.member_marks(
        session,
        marcas.e.socio_id,
        only_load=True,
        wod_ids=[marcas.w[1], marcas.w[3], marcas.w[4]],
    )

    assert _resumen(filas) == [(80_000, None), (100_000, None)]


async def test_el_tope_deja_las_mas_recientes_en_orden_ascendente(
    session: AsyncSession, marcas: Marcas
) -> None:
    dos = await service.member_marks(session, marcas.e.socio_id, limit=2)
    una = await service.member_marks(session, marcas.e.socio_id, limit=1)
    de_sobra = await service.member_marks(session, marcas.e.socio_id, limit=10)

    assert _resumen(dos) == [(None, 300), (100_000, None)]
    assert _resumen(una) == [(100_000, None)]
    assert _resumen(de_sobra) == TODAS


async def test_el_tope_por_omision_es_2000(session: AsyncSession, marcas: Marcas) -> None:
    assert service.MEMBER_MARKS_MAX == 2_000
    with capturar_sql(session, "results.wod_results") as vistas:
        await service.member_marks(session, marcas.e.socio_id)
    sql, parametros = vistas[0]
    assert 2_000 in tuple(parametros) or "LIMIT 2000" in sql.upper()


async def test_un_socio_dado_de_baja_tambien_se_lee(session: AsyncSession, marcas: Marcas) -> None:
    await session.execute(
        text("UPDATE members.members SET deleted_at = now() WHERE id = :i"),
        {"i": marcas.e.socio_id},
    )

    assert _resumen(await service.member_marks(session, marcas.e.socio_id)) == TODAS


async def test_no_pide_candados(session: AsyncSession, marcas: Marcas) -> None:
    with capturar_sql(session, "results.wod_results") as vistas:
        await service.member_marks(session, marcas.e.socio_id)
        await service.member_marks(session, marcas.e.socio_id, benchmark_id=marcas.benchmark_id)
        await service.member_marks(
            session, marcas.e.socio_id, wod_ids=[marcas.w[1]], only_load=True
        )

    assert len(vistas) == 3, "UNA consulta por llamada"
    for sql, _ in vistas:
        assert "FOR UPDATE" not in sql and "FOR SHARE" not in sql


def _literal(valor: Any) -> str:
    if isinstance(valor, bool):
        return "TRUE" if valor else "FALSE"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, (list, tuple, set, frozenset)):
        return "ARRAY[" + ", ".join(_literal(v) for v in valor) + "]::uuid[]"
    return f"'{valor}'"


async def _plan_generico(session: AsyncSession, sql: str, parametros: Any) -> str:
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    await session.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
    conexion = await session.connection()
    nombre = f"p_{uuid4().hex[:8]}"
    await conexion.exec_driver_sql(f"PREPARE {nombre} AS {sql}")
    argumentos = ", ".join(_literal(p) for p in parametros)
    filas = await conexion.exec_driver_sql(f"EXPLAIN EXECUTE {nombre}({argumentos})")
    return "\n".join(str(f[0]) for f in filas.all())


@pytest.mark.parametrize(
    "filtros",
    [{}, {"only_load": True}, {"only_benchmarks": True}, {"benchmark_id": UUID(int=7)}],
    ids=["sin-filtros", "only-load", "only-benchmarks", "benchmark-id"],
)
async def test_usa_ix_wod_results_member_date_con_plan_generico(
    session: AsyncSession, filtros: dict[str, Any]
) -> None:
    with capturar_sql(session, "results.wod_results") as vistas:
        await service.member_marks(session, uuid4(), **filtros)
    sql, parametros = vistas[0]

    plan = await _plan_generico(session, sql, parametros)

    assert "ix_wod_results_member_date" in plan, plan
    assert "Seq Scan" not in plan, plan


# Revisiones de S9-B5 (seguridad L2/L3, base de datos M2) --------------------------------------


async def test_wod_ids_viaja_como_un_solo_parametro_de_arreglo(
    session: AsyncSession, marcas: Marcas
) -> None:
    pocos = {marcas.w[1], marcas.w[2]}
    muchos = {uuid4() for _ in range(80)} | pocos

    with capturar_sql(session, "results.wod_results") as vistas:
        a = await service.member_marks(session, marcas.e.socio_id, wod_ids=pocos)
        b = await service.member_marks(session, marcas.e.socio_id, wod_ids=muchos)

    (sql_a, par_a), (sql_b, par_b) = vistas
    assert "ANY" in sql_a.upper() and "ANY" in sql_b.upper()
    assert len(tuple(par_a)) == len(tuple(par_b)), "los parámetros no crecen con los ids"
    assert any(isinstance(p, list | tuple) and len(p) == len(muchos) for p in tuple(par_b))
    assert _resumen(a) == _resumen(b) == [(80_000, None), (90_000, None)]


async def test_el_plan_generico_con_any_usa_ix_wod_results_member_date(
    session: AsyncSession,
) -> None:
    with capturar_sql(session, "results.wod_results") as vistas:
        await service.member_marks(session, uuid4(), wod_ids=[uuid4(), uuid4()], only_load=True)
    sql, parametros = vistas[0]

    plan = await _plan_generico(session, sql, parametros)

    assert "ix_wod_results_member_date" in plan, plan
    assert "Seq Scan" not in plan, plan


@pytest.mark.parametrize("pedido", [0, -5], ids=["cero", "negativo"])
async def test_un_limite_menor_que_uno_se_trata_como_uno(
    session: AsyncSession, marcas: Marcas, pedido: int
) -> None:
    filas = await service.member_marks(session, marcas.e.socio_id, limit=pedido)

    assert _resumen(filas) == [(100_000, None)], "la más reciente"


async def test_un_limite_mayor_que_el_maximo_se_recorta_al_maximo(
    session: AsyncSession, marcas: Marcas
) -> None:
    with capturar_sql(session, "results.wod_results") as vistas:
        filas = await service.member_marks(
            session, marcas.e.socio_id, limit=service.MEMBER_MARKS_MAX * 10
        )

    assert _resumen(filas) == TODAS
    sql, parametros = vistas[0]
    valores = tuple(parametros)
    assert service.MEMBER_MARKS_MAX in valores or f"LIMIT {service.MEMBER_MARKS_MAX}" in sql.upper()
    assert service.MEMBER_MARKS_MAX * 10 not in valores
