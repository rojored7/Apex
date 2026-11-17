"""`wods.service.wod_ids_with_primary` (S9-B5, S9-D11, S9-D30): el filtro en SQL de la reposición.

Los ids de los WODs de tipo `load` que tienen ese movimiento como PRINCIPAL (`is_primary`). Un
movimiento que solo aparece como secundario, un WOD de otro tipo de marca o un movimiento sin WODs
no cuentan. Una consulta, sin candados, por `uq_wod_movements_primary`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.wods import service
from tests.factories.explain import capturar_sql
from tests.factories.users import make_user
from tests.factories.wods import make_movement, make_wod

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


@pytest.fixture
async def escena(session: AsyncSession) -> dict[str, UUID]:
    coach = (await make_user(session, role="coach")).id
    sentadilla = (await make_movement(session, coach, name="Sentadilla", unit="kg")).id
    remo = (await make_movement(session, coach, name="Remo", unit="kg")).id
    saltos = (await make_movement(session, coach, name="Saltos", unit="reps")).id
    wods = {
        # Principal = sentadilla (primer id de la lista), tipo load.
        "carga_a": (
            await make_wod(
                session,
                coach,
                [sentadilla, saltos],
                title="A",
                score_type="load",
                time_cap_s=None,
                date="2026-10-10",
            )
        ).id,
        "carga_b": (
            await make_wod(
                session,
                coach,
                [sentadilla],
                title="B",
                score_type="load",
                time_cap_s=None,
                date="2026-10-11",
            )
        ).id,
        # Sentadilla solo como secundario: el principal es el remo.
        "secundario": (
            await make_wod(
                session,
                coach,
                [remo, sentadilla],
                title="C",
                score_type="load",
                time_cap_s=None,
                date="2026-10-12",
            )
        ).id,
        # Sentadilla principal pero tipo `time`.
        "tiempo": (
            await make_wod(
                session,
                coach,
                [sentadilla, saltos],
                title="D",
                score_type="time",
                time_cap_s=600,
                date="2026-10-13",
            )
        ).id,
        "wod_remo": (
            await make_wod(
                session,
                coach,
                [remo],
                title="E",
                score_type="load",
                time_cap_s=None,
                date="2026-10-14",
            )
        ).id,
    }
    return {"sentadilla": sentadilla, "remo": remo, "saltos": saltos, **wods}


async def test_devuelve_solo_los_wods_load_con_ese_movimiento_como_principal(
    session: AsyncSession, escena: dict[str, UUID]
) -> None:
    ids = await service.wod_ids_with_primary(session, escena["sentadilla"])

    assert ids == {escena["carga_a"], escena["carga_b"]}


async def test_un_movimiento_principal_en_otro_wod_load(
    session: AsyncSession, escena: dict[str, UUID]
) -> None:
    ids = await service.wod_ids_with_primary(session, escena["remo"])

    assert ids == {escena["secundario"], escena["wod_remo"]}


async def test_un_movimiento_que_nunca_es_principal_o_sin_wods_da_vacio(
    session: AsyncSession, escena: dict[str, UUID]
) -> None:
    assert await service.wod_ids_with_primary(session, escena["saltos"]) == frozenset()
    assert await service.wod_ids_with_primary(session, uuid4()) == frozenset()


async def test_el_resultado_es_un_conjunto_inmutable_de_uuid(
    session: AsyncSession, escena: dict[str, UUID]
) -> None:
    ids = await service.wod_ids_with_primary(session, escena["sentadilla"])

    assert isinstance(ids, frozenset)
    assert all(isinstance(i, UUID) for i in ids)


async def test_una_sola_consulta_sin_candados(
    session: AsyncSession, escena: dict[str, UUID]
) -> None:
    with capturar_sql(session, "wods.") as vistas:
        await service.wod_ids_with_primary(session, escena["sentadilla"])

    assert len(vistas) == 1
    sql = vistas[0][0]
    assert "FOR UPDATE" not in sql and "FOR SHARE" not in sql


async def test_el_plan_generico_usa_el_indice_del_principal(
    session: AsyncSession, escena: dict[str, UUID]
) -> None:
    with capturar_sql(session, "wods.") as vistas:
        await service.wod_ids_with_primary(session, escena["sentadilla"])
    sql, parametros = vistas[0]
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    await session.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
    conexion = await session.connection()
    nombre = f"p_{uuid4().hex[:8]}"
    await conexion.exec_driver_sql(f"PREPARE {nombre} AS {sql}")
    argumentos: Any = ", ".join(f"'{p}'" for p in parametros)

    filas = await conexion.exec_driver_sql(f"EXPLAIN EXECUTE {nombre}({argumentos})")
    plan = "\n".join(str(f[0]) for f in filas.all())

    assert "uq_wod_movements_primary" in plan or "ix_wod_movements" in plan, plan
    assert "Seq Scan" not in plan, plan


async def test_la_consulta_lleva_tope(session: AsyncSession, escena: dict[str, UUID]) -> None:
    """Revisión de S9-B5 (seguridad L3): sin tope un movimiento muy usado traería miles de ids."""
    assert service.WOD_IDS_MAX == 2_000
    with capturar_sql(session, "wods.") as vistas:
        await service.wod_ids_with_primary(session, escena["sentadilla"])
    sql, parametros = vistas[0]
    assert service.WOD_IDS_MAX in tuple(parametros) or f"LIMIT {service.WOD_IDS_MAX}" in sql.upper()
