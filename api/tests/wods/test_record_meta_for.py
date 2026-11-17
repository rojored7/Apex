"""`record_meta_for` (S9-B3, S9-D6, US-181): lo que el handler de `athletes` pide de los WODs.

Por lote, en UNA consulta y SIN candado (el handler suscrito no pide candados, S9-D7; `scoring_for`
toma `FOR SHARE` y es de un solo WOD). Dato plano (dataclass), no ORM; solo los WODs que existen.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.wods import service
from app.modules.wods.catalog import WodRecordMeta
from app.modules.wods.models import Wod
from tests.conftest import CrearUsuario, UsuarioPrueba
from tests.factories.explain import capturar_sql
from tests.factories.wods import cuerpo_wod, make_benchmark, make_movement, make_wod

pytestmark = pytest.mark.usefixtures("reloj")


@pytest.fixture
async def staff(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


async def test_devuelve_tipo_principal_benchmark_y_fecha_como_dato_plano(
    session: AsyncSession, staff: UsuarioPrueba
) -> None:
    actor = staff.id
    principal = await make_movement(session, actor, "Back Squat meta", "kg")
    otro = await make_movement(session, actor, "Remo meta", "m")
    bench = await make_benchmark(session, actor, "Helen meta", "load")
    wod = await make_wod(
        session,
        actor,
        [principal.id, otro.id],
        date="2026-10-20",
        score_type="load",
        time_cap_s=None,
        benchmark_id=bench.id,
    )
    session.expunge_all()

    metas = await service.record_meta_for(session, [wod.id])

    meta = metas[wod.id]
    assert isinstance(meta, WodRecordMeta) and is_dataclass(meta)
    assert not isinstance(meta, Wod)
    assert {f.name for f in fields(meta)} >= {
        "score_type",
        "primary_movement_id",
        "benchmark_id",
        "date",
    }
    assert meta.score_type == "load"
    assert meta.primary_movement_id == principal.id
    assert meta.benchmark_id == bench.id
    assert meta.date == date(2026, 10, 20)


async def test_un_wod_sin_principal_ni_benchmark_trae_none(
    session: AsyncSession, staff: UsuarioPrueba
) -> None:
    actor = staff.id
    mov = await make_movement(session, actor, "Sin principal meta", "reps")
    movimientos = cuerpo_wod([mov.id], date="2026-10-19")["movements"]
    movimientos[0]["is_primary"] = False
    wod = await make_wod(session, actor, [mov.id], date="2026-10-19", movements=movimientos)
    session.expunge_all()

    meta = (await service.record_meta_for(session, [wod.id]))[wod.id]

    assert meta.score_type == "time"
    assert meta.primary_movement_id is None
    assert meta.benchmark_id is None


async def test_por_lote_en_una_sola_consulta_y_sin_candado(
    session: AsyncSession, staff: UsuarioPrueba
) -> None:
    actor = staff.id
    mov = await make_movement(session, actor, "Lote meta", "kg")
    uno = await make_wod(session, actor, [mov.id], date="2026-10-18", title="Uno")
    dos = await make_wod(
        session, actor, [mov.id], date="2026-10-17", title="Dos", score_type="load", time_cap_s=None
    )
    ausente = uuid4()
    session.expunge_all()

    with capturar_sql(session, "wods.") as sentencias:
        metas = await service.record_meta_for(session, [uno.id, dos.id, ausente])

    assert set(metas) == {uno.id, dos.id}, "solo los WODs que existen"
    assert metas[uno.id].score_type == "time" and metas[dos.id].score_type == "load"
    assert metas[uno.id].date == date(2026, 10, 18)
    assert len(sentencias) == 1, "una sola consulta por lote, principal incluido"
    assert " FOR " not in sentencias[0][0].upper(), "sin candado: lectura pura"


async def test_una_coleccion_vacia_no_consulta(session: AsyncSession) -> None:
    with capturar_sql(session, "wods.") as sentencias:
        metas = await service.record_meta_for(session, [])

    assert metas == {}
    assert sentencias == []


async def test_acepta_cualquier_coleccion_de_ids(
    session: AsyncSession, staff: UsuarioPrueba
) -> None:
    actor = staff.id
    mov = await make_movement(session, actor, "Colección meta", "kg")
    wod = await make_wod(session, actor, [mov.id], date="2026-10-16")

    assert set(await service.record_meta_for(session, {wod.id})) == {wod.id}
    assert set(await service.record_meta_for(session, (wod.id, wod.id))) == {wod.id}
