"""El puerto real `RecordsProbe` de `athletes` (S9-B2, S9-D9, S9-D54).

- Solo cuentan los récords NO invalidados (de un movimiento o de un benchmark).
- Una sola consulta `EXISTS` por llamada, con la columna desnuda (S8-D50).
- Carrera real: el alta manual toma el movimiento `FOR SHARE`; el `PATCH` (`FOR UPDATE`) espera a
  que confirme y entonces ve el récord (422 `locked_by_records`).
"""

from __future__ import annotations

import asyncio
import time
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.errors import DomainError
from app.modules.athletes import service as athletes_service
from app.modules.athletes.schemas import RecordIn
from app.modules.wods import service as wods_service
from app.modules.wods.schemas import BenchmarkPatch, MovementPatch
from tests.athletes._apoyo import cuerpo_rm
from tests.factories.athletes import make_record
from tests.factories.explain import capturar_sql
from tests.factories.wods import make_benchmark, make_movement
from tests.notifications._apoyo_avisos import socio

ESPERA_MAX_S = 10.0


def test_el_puerto_registrado_es_el_de_athletes() -> None:
    assert wods_service.current_records_probe() is athletes_service.records_probe


@pytest.mark.usefixtures("bus_listo")
async def test_solo_cuentan_los_records_vivos_del_movimiento(session: AsyncSession) -> None:
    sonda = athletes_service.records_probe
    solo_invalidado, vivo, vacio = uuid4(), uuid4(), uuid4()
    await make_record(session, kind="rm", movement_id=solo_invalidado, invalidated=True)
    await make_record(session, kind="rm", movement_id=vivo)
    await make_record(session, kind="rm", movement_id=vivo, invalidated=True)
    assert await sonda.movement_has_records(session, solo_invalidado) is False
    assert await sonda.movement_has_records(session, vivo) is True
    assert await sonda.movement_has_records(session, vacio) is False


@pytest.mark.usefixtures("bus_listo")
async def test_solo_cuentan_los_records_vivos_del_benchmark(session: AsyncSession) -> None:
    sonda = athletes_service.records_probe
    solo_invalidado, vivo = uuid4(), uuid4()
    await make_record(session, kind="benchmark", benchmark_id=solo_invalidado, invalidated=True)
    await make_record(session, kind="benchmark", benchmark_id=vivo)
    assert await sonda.benchmark_has_records(session, solo_invalidado) is False
    assert await sonda.benchmark_has_records(session, vivo) is True
    assert await sonda.benchmark_has_records(session, uuid4()) is False


@pytest.mark.usefixtures("bus_listo")
async def test_una_sola_consulta_exists_con_limit_1_y_columna_desnuda(
    session: AsyncSession,
) -> None:
    sonda = athletes_service.records_probe
    mov, bm = uuid4(), uuid4()
    await make_record(session, kind="rm", movement_id=mov)
    await make_record(session, kind="benchmark", benchmark_id=bm)
    with capturar_sql(session, "personal_records") as vistas:
        await sonda.movement_has_records(session, mov)
    assert len(vistas) == 1
    sql = vistas[0][0].lower()
    assert "exists" in sql  # EXISTS corta en la primera fila (S9-D54)
    assert "movement_id = " in sql and "invalidated_at is null" in sql
    with capturar_sql(session, "personal_records") as vistas:
        await sonda.benchmark_has_records(session, bm)
    assert len(vistas) == 1
    assert "benchmark_id = " in vistas[0][0].lower()


async def _esperando_candado(engine: AsyncEngine, pid: int) -> None:
    limite = time.monotonic() + ESPERA_MAX_S
    consulta = text("SELECT count(*) FROM pg_locks WHERE pid = :p AND NOT granted")
    while time.monotonic() < limite:
        async with engine.connect() as conexion:
            if await conexion.scalar(consulta, {"p": pid}):
                return
        await asyncio.sleep(0.05)
    raise AssertionError("el PATCH nunca quedó esperando el candado del alta")


@pytest.mark.usefixtures("reloj", "bus_confirmado")
async def test_carrera_el_patch_de_la_unidad_espera_al_alta_manual_y_ve_el_record(
    engine: AsyncEngine, dos_sesiones: tuple[AsyncSession, AsyncSession]
) -> None:
    una, otra = dos_sesiones
    miembro = await socio(una, consentido=True)
    mov: UUID = (await make_movement(una, SYSTEM_USER_ID, "Carrera récord", "kg")).id
    member_id = miembro.id
    una.expunge_all()
    pid = int(await otra.scalar(text("SELECT pg_backend_pid()")) or 0)
    # LOW-1: la ausencia de TOCTOU depende de READ COMMITTED (el PATCH relee tras esperar).
    for conexion in (una, otra):
        assert await conexion.scalar(text("SHOW transaction_isolation")) == "read committed"

    with actor_scope(SYSTEM_USER_ID):
        # El alta toma el movimiento FOR SHARE y deja el récord sin confirmar.
        await athletes_service.add_record(
            una,
            member_id,
            RecordIn.model_validate(cuerpo_rm(mov, value_g=100_000)),
            by=SYSTEM_USER_ID,
        )

        async def cambiar_unidad() -> None:
            try:
                await wods_service.update_movement(
                    otra, mov, MovementPatch.model_validate({"unit": "reps"}), SYSTEM_USER_ID
                )
            finally:
                await otra.rollback()

        tarea = asyncio.create_task(cambiar_unidad())
        try:
            try:
                await _esperando_candado(engine, pid)
                assert not tarea.done(), "el PATCH debe esperar al FOR SHARE del alta"
            finally:
                await una.commit()
            with pytest.raises(DomainError) as info:
                await asyncio.wait_for(tarea, timeout=30)
        finally:
            if not tarea.done():
                tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
    assert (info.value.status, info.value.code, info.value.field) == (
        422,
        "locked_by_records",
        "unit",
    )


@pytest.mark.usefixtures("bus_listo")
async def test_el_benchmark_con_record_vivo_no_cambia_de_tipo_por_el_puerto_real(
    session: AsyncSession,
) -> None:
    bm = await make_benchmark(session, SYSTEM_USER_ID, name="Bm puerto real", score_type="time")
    await make_record(session, kind="benchmark", benchmark_id=bm.id)
    with actor_scope(SYSTEM_USER_ID), pytest.raises(DomainError) as info:
        await wods_service.update_benchmark(
            session, bm.id, BenchmarkPatch.model_validate({"score_type": "reps"}), SYSTEM_USER_ID
        )
    assert (info.value.status, info.value.field) == (422, "score_type")


@pytest.mark.usefixtures("bus_listo")
async def test_los_dos_indices_parciales_sirven_a_la_consulta_del_puerto(
    session: AsyncSession,
) -> None:
    """S9-D54 / LOW-5: con plan GENÉRICO (sentencia preparada) y sin Seq Scan, el `EXISTS` usa
    `ix_personal_records_movement` e `ix_personal_records_benchmark` (columna desnuda)."""
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    await session.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
    conexion = await session.connection()
    for campo, indice in (
        ("movement_id", "ix_personal_records_movement"),
        ("benchmark_id", "ix_personal_records_benchmark"),
    ):
        sentencia = f"p_{campo}"
        await conexion.exec_driver_sql(
            f"PREPARE {sentencia}(uuid) AS SELECT EXISTS (SELECT 1 FROM "  # noqa: S608
            f"athletes.personal_records WHERE {campo} = $1 AND invalidated_at IS NULL)"
        )
        filas = await conexion.exec_driver_sql(f"EXPLAIN EXECUTE {sentencia}('{uuid4()}')")
        plan = "\n".join(str(f[0]) for f in filas.all())
        assert indice in plan, plan
        assert "Seq Scan" not in plan, plan
