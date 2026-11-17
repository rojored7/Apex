"""Lecturas del catálogo para los récords (S9-B1, US-180; S9-D6, S9-D9). Rojo B1.

- `movement_for_record` y `benchmark_for_record` (envolturas públicas de `wods.service`): devuelven
  dataclasses planas (`MovementRef`, `BenchmarkRef`), NO ORM; `None` si no existe; leen con
  `FOR SHARE` (un `PATCH` concurrente espera) y con datos frescos.
- `movement_refs` y `benchmark_refs`: por lote, en UNA consulta, SIN candados; solo devuelven los
  ids que existen; con una colección vacía no consultan.
"""

from __future__ import annotations

from dataclasses import is_dataclass
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.wods import service
from app.modules.wods.catalog import BenchmarkRef, MovementRef
from app.modules.wods.models import Benchmark, Movement
from tests.conftest import CrearUsuario, UsuarioPrueba
from tests.factories.explain import capturar_sql
from tests.factories.wods import make_benchmark, make_movement

pytestmark = pytest.mark.usefixtures("reloj")


@pytest.fixture
async def staff(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


async def test_movement_for_record_devuelve_una_dataclass_plana(
    session: AsyncSession, staff: UsuarioPrueba
) -> None:
    actor = staff.id
    mov = await make_movement(session, actor, "Back Squat", "kg")

    ref = await service.movement_for_record(session, mov.id)

    assert isinstance(ref, MovementRef) and is_dataclass(ref)
    assert not isinstance(ref, Movement)
    assert (ref.id, ref.name, ref.unit, ref.is_active) == (mov.id, "Back Squat", "kg", True)


async def test_benchmark_for_record_devuelve_una_dataclass_plana(
    session: AsyncSession, staff: UsuarioPrueba
) -> None:
    actor = staff.id
    bm = await make_benchmark(session, actor, "Fran", "time")

    ref = await service.benchmark_for_record(session, bm.id)

    assert isinstance(ref, BenchmarkRef) and is_dataclass(ref)
    assert not isinstance(ref, Benchmark)
    assert (ref.id, ref.name, ref.score_type) == (bm.id, "Fran", "time")


async def test_for_record_devuelve_none_si_no_existe(session: AsyncSession) -> None:
    assert await service.movement_for_record(session, uuid4()) is None
    assert await service.benchmark_for_record(session, uuid4()) is None


async def test_un_movimiento_inactivo_se_devuelve_con_is_active_false(
    session: AsyncSession, staff: UsuarioPrueba
) -> None:
    actor = staff.id
    mov = await make_movement(session, actor, "Viejo", "kg")
    await session.execute(
        Movement.__table__.update().where(Movement.id == mov.id).values(is_active=False)
    )
    session.expunge_all()

    ref = await service.movement_for_record(session, mov.id)

    assert ref is not None and ref.is_active is False


async def test_movement_for_record_toma_for_share(
    session: AsyncSession, staff: UsuarioPrueba
) -> None:
    actor = staff.id
    mov = await make_movement(session, actor, "Clean", "kg")
    session.expunge_all()

    with capturar_sql(session, "wods.movements") as sentencias:
        await service.movement_for_record(session, mov.id)

    assert len(sentencias) == 1
    assert "FOR SHARE" in sentencias[0][0].upper()


async def test_benchmark_for_record_toma_for_share(
    session: AsyncSession, staff: UsuarioPrueba
) -> None:
    actor = staff.id
    bm = await make_benchmark(session, actor, "Grace", "time")
    session.expunge_all()

    with capturar_sql(session, "wods.benchmarks") as sentencias:
        await service.benchmark_for_record(session, bm.id)

    assert len(sentencias) == 1
    assert "FOR SHARE" in sentencias[0][0].upper()


async def test_for_record_lee_datos_frescos_y_no_el_objeto_en_cache(
    session: AsyncSession, staff: UsuarioPrueba
) -> None:
    """Un `PATCH` confirmado después de que el ORM cacheó el objeto: la lectura ve lo confirmado."""
    actor = staff.id
    mov = await make_movement(session, actor, "Press", "kg")
    objeto = await session.get(Movement, mov.id)
    assert objeto is not None
    await session.execute(
        Movement.__table__.update().where(Movement.id == mov.id).values(unit="reps")
    )

    ref = await service.movement_for_record(session, mov.id)

    assert ref is not None and ref.unit == "reps"


# Lecturas por lote -----------------------------------------------------------------------------


async def test_movement_refs_una_consulta_sin_candados_y_solo_los_existentes(
    session: AsyncSession, staff: UsuarioPrueba
) -> None:
    actor = staff.id
    a = await make_movement(session, actor, "Snatch", "kg")
    b = await make_movement(session, actor, "Run", "m")
    ausente = uuid4()
    session.expunge_all()

    with capturar_sql(session, "wods.movements") as sentencias:
        refs = await service.movement_refs(session, [a.id, b.id, ausente])

    assert len(sentencias) == 1
    assert " FOR " not in sentencias[0][0].upper()
    assert set(refs) == {a.id, b.id}
    assert all(isinstance(r, MovementRef) for r in refs.values())
    assert (refs[a.id].name, refs[a.id].unit, refs[a.id].is_active) == ("Snatch", "kg", True)
    assert (refs[b.id].name, refs[b.id].unit) == ("Run", "m")


async def test_benchmark_refs_una_consulta_sin_candados_y_solo_los_existentes(
    session: AsyncSession, staff: UsuarioPrueba
) -> None:
    actor = staff.id
    a = await make_benchmark(session, actor, "Cindy", "rounds_reps")
    b = await make_benchmark(session, actor, "Helen", "time")
    session.expunge_all()

    with capturar_sql(session, "wods.benchmarks") as sentencias:
        refs = await service.benchmark_refs(session, {a.id, b.id, uuid4()})

    assert len(sentencias) == 1
    assert " FOR " not in sentencias[0][0].upper()
    assert set(refs) == {a.id, b.id}
    assert all(isinstance(r, BenchmarkRef) for r in refs.values())
    assert (refs[a.id].name, refs[a.id].score_type) == ("Cindy", "rounds_reps")
    assert (refs[b.id].name, refs[b.id].score_type) == ("Helen", "time")


async def test_refs_con_coleccion_vacia_no_consultan(session: AsyncSession) -> None:
    with capturar_sql(session, "wods.") as sentencias:
        assert await service.movement_refs(session, []) == {}
        assert await service.benchmark_refs(session, set()) == {}
    assert sentencias == []


async def test_benchmark_refs_viaja_como_un_solo_parametro_de_arreglo(
    session: AsyncSession, staff: UsuarioPrueba
) -> None:
    """S9-C1 (base de datos LOW-4, como S9-D60): los ids son UN parámetro `= ANY(:ids)`."""
    a = await make_benchmark(session, staff.id, "Barbara", "rounds_reps")
    pocos = {a.id}
    muchos = {uuid4() for _ in range(80)} | pocos
    session.expunge_all()

    with capturar_sql(session, "wods.benchmarks") as vistas:
        r1 = await service.benchmark_refs(session, pocos)
        r2 = await service.benchmark_refs(session, muchos)

    (sql_a, par_a), (sql_b, par_b) = vistas
    assert "ANY" in sql_a.upper() and "ANY" in sql_b.upper()
    assert len(tuple(par_a)) == len(tuple(par_b)), "los parámetros no crecen con los ids"
    assert any(isinstance(p, list | tuple) and len(p) == len(muchos) for p in tuple(par_b))
    assert set(r1) == set(r2) == {a.id}
