"""`wods.service` de WODs con base real (S8-A3, US-166, US-167; S8-D7, S8-D8, S8-D41). Rojo A3.

`ResultsProbe` (S8-D4): las pruebas registran un doble y restauran el puerto al salir.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Sequence
from datetime import date
from typing import Any
from unittest import mock
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.db import DatabaseBusy
from app.core.pagination import PageParams
from app.modules.wods import programming as programming_module
from app.modules.wods import service
from app.modules.wods.exceptions import (
    LockedByResults,
    ResultsProbeNotRegistered,
    ScoreTypeLocked,
    ScoreTypeMismatch,
    WodDateTaken,
    WodNotFound,
    WodsValidationError,
)
from app.modules.wods.probe import current_results_probe
from app.modules.wods.schemas import (
    BenchmarkCreate,
    BenchmarkPatch,
    MovementCreate,
    MovementPatch,
    WodCreate,
    WodListQuery,
    WodMovementIn,
    WodOut,
    WodPatch,
)
from tests.conftest import CrearUsuario
from tests.factories.wods import cuerpo_wod, make_benchmark, make_movement, make_wod

PAGINA = PageParams(limit=50, offset=0)
SIN_FILTROS = WodListQuery()


class _Sonda:
    """Doble de `ResultsProbe`: cuántos resultados tiene cada WOD."""

    def __init__(self) -> None:
        self.cuentas: dict[UUID, int] = {}
        self.llamadas: list[list[UUID]] = []

    async def result_counts(
        self, session: AsyncSession, wod_ids: Sequence[UUID]
    ) -> dict[UUID, int]:
        self.llamadas.append(list(wod_ids))
        return {w: self.cuentas.get(w, 0) for w in wod_ids}

    async def referenced_scaled_movements(
        self, session: AsyncSession, wod_id: UUID
    ) -> frozenset[UUID]:
        return frozenset()


@pytest.fixture
def sonda() -> Iterator[_Sonda]:
    anterior = current_results_probe()
    doble = _Sonda()
    service.set_results_probe(doble)
    try:
        yield doble
    finally:
        service.set_results_probe(anterior)


async def _patch(session: AsyncSession, actor: UUID, wod_id: UUID, **cambios: Any) -> WodOut:
    with actor_scope(actor):
        salida = await service.update_wod(session, wod_id, WodPatch.model_validate(cambios), actor)
        await session.commit()
    return salida


async def _movs(session: AsyncSession, actor: UUID, *nombres: str) -> list[UUID]:
    return [(await make_movement(session, actor, n)).id for n in nombres]


async def _desactivar(session: AsyncSession, actor: UUID, *ids: UUID) -> None:
    with actor_scope(actor):
        for mid in ids:
            patch = MovementPatch.model_validate({"is_active": False})
            await service.update_movement(session, mid, patch, actor)
        await session.commit()


async def _auditoria(session: AsyncSession, tabla: str, accion: str | None = None) -> list[Any]:
    consulta = "SELECT action, after, before FROM audit.audit_log WHERE table_name = :t"
    if accion:
        consulta += " AND action = :a"
    filas = await session.execute(text(consulta + " ORDER BY seq"), {"t": tabla, "a": accion})
    return list(filas.all())


async def test_el_alta_guarda_el_wod_con_sus_movimientos_y_lo_audita(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    thr, pul = await _movs(session, admin.id, "Thruster", "Pull-up")
    salida = await make_wod(session, admin.id, [thr, pul])
    assert (salida.title, salida.score_type, salida.time_cap_s) == ("Fran", "time", 600)
    assert salida.date == date(2026, 10, 22) and not salida.is_benchmark
    assert [(m.position, m.movement_name, m.is_primary) for m in salida.movements] == [
        (1, "Thruster", True),
        (2, "Pull-up", False),
    ]
    assert salida.result_count == 0
    assert len(await _auditoria(session, "wods.wods", "insert")) == 1
    assert len(await _auditoria(session, "wods.wod_movements", "insert")) == 2


async def test_copia_del_nombre_tras_renombrar(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    (thr,) = await _movs(session, admin.id, "Thruster")
    wod = await make_wod(session, admin.id, [thr])
    with actor_scope(admin.id):
        patch = MovementPatch.model_validate({"name": "Thruster RX"})
        await service.update_movement(session, thr, patch, admin.id)
        await session.commit()
    assert (await service.get_wod(session, wod.id)).movements[0].movement_name == "Thruster"
    # un PATCH que conserva el movimiento tampoco refresca la copia de un WOD ya escrito
    editado = await _patch(session, admin.id, wod.id, title="Fran 2")
    assert editado.movements[0].movement_name == "Thruster"
    cuerpo = cuerpo_wod([thr])["movements"]
    reemplazado = await _patch(session, admin.id, wod.id, movements=cuerpo)
    assert reemplazado.movements[0].movement_name == "Thruster"


async def test_409_wod_date_taken_con_existing_id(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    (thr,) = await _movs(session, admin.id, "Thruster")
    primero = await make_wod(session, admin.id, [thr])
    with pytest.raises(WodDateTaken) as error:
        await make_wod(session, admin.id, [thr], title="Otro")
    assert error.value.existing_id == primero.id and error.value.field == "date"
    segundo = await make_wod(session, admin.id, [thr], date="2026-10-23", title="Otro")
    with pytest.raises(WodDateTaken) as error:
        await _patch(session, admin.id, segundo.id, date="2026-10-22")
    assert error.value.existing_id == primero.id


async def test_carrera_de_dos_altas_con_la_misma_fecha_da_409_y_la_sesion_sigue_usable(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """La comprobación previa no ve a nadie (el otro alta aún no confirmó): decide el índice."""
    admin = await usuario_real("admin")
    (thr,) = await _movs(session, admin.id, "Thruster")
    primero = await make_wod(session, admin.id, [thr])
    original = programming_module._id_by_date
    llamadas: list[int] = []

    async def parcheada(s: AsyncSession, dia: date, *, exclude: UUID | None) -> UUID | None:
        llamadas.append(1)
        return None if len(llamadas) == 1 else await original(s, dia, exclude=exclude)

    with mock.patch.object(programming_module, "_id_by_date", parcheada):
        with pytest.raises(WodDateTaken) as error:
            await make_wod(session, admin.id, [thr], title="Carrera")
    assert error.value.existing_id == primero.id
    assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    assert len(await _auditoria(session, "wods.wods", "insert")) == 1


async def test_score_type_del_benchmark_o_422_score_type_mismatch(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    (thr,) = await _movs(session, admin.id, "Thruster")
    fran = await make_benchmark(session, admin.id, "Fran", "time")
    with pytest.raises(ScoreTypeMismatch) as error:
        await make_wod(
            session, admin.id, [thr], benchmark_id=str(fran.id), score_type="reps", time_cap_s=None
        )
    assert error.value.field == "score_type"
    ok = await make_wod(session, admin.id, [thr], benchmark_id=str(fran.id))
    assert ok.is_benchmark and ok.benchmark_name == "Fran" and ok.benchmark_id == fran.id
    with pytest.raises(WodsValidationError) as inexistente:
        await make_wod(session, admin.id, [thr], date="2026-10-23", benchmark_id=str(UUID(int=7)))
    assert inexistente.value.field == "benchmark_id"
    with pytest.raises(ScoreTypeMismatch):
        await _patch(session, admin.id, ok.id, score_type="load", time_cap_s=None)
    quitado = await _patch(session, admin.id, ok.id, benchmark_id=None, score_type="rounds_reps")
    assert not quitado.is_benchmark and quitado.benchmark_id is None


async def test_un_benchmark_con_wods_bloquea_su_score_type_con_wods_reales(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """Reemplaza el doble de A2: `wod_count` sale de la consulta sobre `wods.wods`."""
    admin = await usuario_real("admin")
    (thr,) = await _movs(session, admin.id, "Thruster")
    fran = await make_benchmark(session, admin.id, "Fran", "time")
    sin_uso = await make_benchmark(session, admin.id, "Grace", "reps")
    await make_wod(session, admin.id, [thr], benchmark_id=str(fran.id))
    with actor_scope(admin.id):
        with pytest.raises(ScoreTypeLocked):
            await service.update_benchmark(
                session, fran.id, BenchmarkPatch(score_type="load"), admin.id
            )
        libre = await service.update_benchmark(
            session, sin_uso.id, BenchmarkPatch(score_type="load"), admin.id
        )
    assert libre.score_type == "load"
    assert (await service.get_benchmark(session, fran.id)).wod_count == 1
    assert (await service.get_benchmark(session, sin_uso.id)).wod_count == 0


async def test_wod_count_del_movimiento_cuenta_wods_distintos(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    thr, pul = await _movs(session, admin.id, "Thruster", "Pull-up")
    await make_wod(session, admin.id, [thr, pul])
    await make_wod(session, admin.id, [thr], date="2026-10-23")
    assert (await service.get_movement(session, thr)).wod_count == 2
    assert (await service.get_movement(session, pul)).wod_count == 1
    await _desactivar(session, admin.id, pul)
    assert (await service.get_movement(session, pul)).wod_count == 1  # desactivar no cambia WODs


async def test_con_resultados_bloquea_score_type_date_cap_y_benchmark(
    session: AsyncSession, usuario_real: CrearUsuario, sonda: _Sonda
) -> None:
    admin = await usuario_real("admin")
    (thr,) = await _movs(session, admin.id, "Thruster")
    fran = await make_benchmark(session, admin.id, "Fran", "time")
    wod = await make_wod(session, admin.id, [thr])
    sonda.cuentas[wod.id] = 3
    with pytest.raises(ScoreTypeLocked):
        await _patch(session, admin.id, wod.id, score_type="rounds_reps")
    cambios = (("date", "2026-10-30"), ("time_cap_s", 900), ("benchmark_id", str(fran.id)))
    for campo, valor in cambios:
        with pytest.raises(LockedByResults) as error:
            await _patch(session, admin.id, wod.id, **{campo: valor})
        assert error.value.field == campo
    with pytest.raises(LockedByResults) as quitar:
        await _patch(session, admin.id, wod.id, time_cap_s=None)
    assert quitar.value.field == "time_cap_s"
    # lo que no cambia el orden de las marcas sí se edita; los mismos valores no son un cambio
    ok = await _patch(
        session, admin.id, wod.id, title="Fran RX", description="nota", date="2026-10-22"
    )
    assert ok.title == "Fran RX" and ok.result_count == 3
    assert [wod.id] in sonda.llamadas


async def test_sin_puerto_registrado_falla_cerrado(
    session: AsyncSession, usuario_real: CrearUsuario, sonda: _Sonda
) -> None:
    admin = await usuario_real("admin")
    (thr,) = await _movs(session, admin.id, "Thruster")
    wod = await make_wod(session, admin.id, [thr])
    service.set_results_probe(None)
    with pytest.raises(ResultsProbeNotRegistered):
        service.results_probe()
    with pytest.raises(ResultsProbeNotRegistered):
        await _patch(session, admin.id, wod.id, title="X")
    with pytest.raises(ResultsProbeNotRegistered):
        await service.get_wod(session, wod.id)
    with pytest.raises(ResultsProbeNotRegistered):
        await service.list_wods(session, SIN_FILTROS, PAGINA)
    # la alta no necesita el puerto: un WOD nuevo no tiene resultados
    nuevo = await make_wod(session, admin.id, [thr], date="2026-10-24")
    assert nuevo.result_count == 0


async def test_solo_movimientos_activos_salvo_los_que_ya_tenia(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    thr, pul, snc = await _movs(session, admin.id, "Thruster", "Pull-up", "Snatch")
    wod = await make_wod(session, admin.id, [thr, pul])
    await _desactivar(session, admin.id, pul, snc)
    cuerpo = cuerpo_wod([thr, pul, snc])["movements"]
    with pytest.raises(WodsValidationError) as error:
        await _patch(session, admin.id, wod.id, movements=cuerpo)
    assert error.value.field == "movements.2.movement_id"
    ok = await _patch(session, admin.id, wod.id, movements=cuerpo[:2])  # `pul` ya estaba
    assert [m.movement_name for m in ok.movements] == ["Thruster", "Pull-up"]
    with pytest.raises(WodsValidationError) as nuevo:
        await make_wod(session, admin.id, [thr, snc], date="2026-10-25")
    assert nuevo.value.field == "movements.1.movement_id"
    with pytest.raises(WodsValidationError) as falta:
        await make_wod(session, admin.id, [UUID(int=9)], date="2026-10-26")
    assert falta.value.field == "movements.0.movement_id"


async def test_reemplazo_de_lista_auditado(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    thr, pul, snc = await _movs(session, admin.id, "Thruster", "Pull-up", "Snatch")
    wod = await make_wod(session, admin.id, [thr, pul])
    nuevos = cuerpo_wod([snc, thr, pul])["movements"]
    nuevos[0]["is_primary"] = False
    nuevos[2]["is_primary"] = True  # el principal cambia de lugar en el mismo reemplazo
    editado = await _patch(session, admin.id, wod.id, movements=nuevos)
    assert [m.movement_name for m in editado.movements] == ["Snatch", "Thruster", "Pull-up"]
    assert [m.is_primary for m in editado.movements] == [False, False, True]
    borradas = await _auditoria(session, "wods.wod_movements", "delete")
    assert len(borradas) == 2 and all(b.before["movement_name"] for b in borradas)
    assert len(await _auditoria(session, "wods.wod_movements", "insert")) == 2 + 3
    filas = await session.execute(
        text("SELECT count(*) FROM wods.wod_movements WHERE wod_id = :w"), {"w": wod.id}
    )
    assert filas.scalar_one() == 3


async def test_patch_sin_cambios_no_audita_y_los_nulos_invalidos_dan_422(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    (thr,) = await _movs(session, admin.id, "Thruster")
    wod = await make_wod(session, admin.id, [thr])
    antes = len(await _auditoria(session, "wods.wods"))
    igual = await _patch(session, admin.id, wod.id, title="Fran", time_cap_s=600)
    assert igual.updated_at == wod.updated_at
    assert len(await _auditoria(session, "wods.wods")) == antes
    with pytest.raises(WodsValidationError) as vacia:
        await _patch(session, admin.id, wod.id, movements=[])
    assert vacia.value.field == "movements"
    for campo in ("title", "date", "score_type", "description", "movements"):
        with pytest.raises(WodsValidationError) as nulo:
            await _patch(session, admin.id, wod.id, **{campo: None})
        assert nulo.value.field == campo
    with pytest.raises(WodNotFound):
        await _patch(session, admin.id, UUID(int=3), title="x")
    with pytest.raises(WodNotFound):
        await service.get_wod(session, UUID(int=3))


async def test_un_patch_solo_de_movimientos_actualiza_updated_at(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    thr, pul = await _movs(session, admin.id, "Thruster", "Pull-up")
    wod = await make_wod(session, admin.id, [thr])
    ok = await _patch(session, admin.id, wod.id, movements=cuerpo_wod([thr, pul])["movements"])
    assert ok.updated_at >= wod.updated_at and len(ok.movements) == 2
    assert (
        len(await _auditoria(session, "wods.wod_movements", "insert")) == 1 + 2
    )  # y no hay otra fila


def test_cargas_en_gramos_enteros_y_negativas_o_mayores_a_un_millon_dan_422() -> None:
    base: dict[str, Any] = {"movement_id": str(UUID(int=1)), "position": 1}
    ok = WodMovementIn.model_validate({**base, "load_rx_m_g": 43_000, "load_rx_f_g": 1_000_000})
    assert (ok.load_rx_m_g, ok.load_rx_f_g) == (43_000, 1_000_000)
    assert WodMovementIn.model_validate({**base, "load_rx_m_g": 0}).load_rx_m_g == 0
    for malo in (-1, 1_000_001, 43.5, "43000", True):
        with pytest.raises(ValidationError):
            WodMovementIn.model_validate({**base, "load_rx_m_g": malo})
    with pytest.raises(ValidationError):
        WodMovementIn.model_validate({**base, "load_rx_f_g": -5})


async def test_auditoria_de_un_wod_con_cargas_serializa_sin_canonical_error(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """S8-D41: `core/audit._normalize` rechaza `Decimal`; las cargas son enteros en gramos."""
    admin = await usuario_real("admin")
    (thr,) = await _movs(session, admin.id, "Thruster")
    cuerpo = cuerpo_wod([thr])
    cuerpo["movements"][0].update(load_rx_m_g=43_000, load_rx_f_g=30_000)
    with actor_scope(admin.id):
        wod = await service.create_wod(session, WodCreate.model_validate(cuerpo), admin.id)
        await session.commit()
    (alta,) = await _auditoria(session, "wods.wod_movements", "insert")
    assert (alta.after["load_rx_m_g"], alta.after["load_rx_f_g"]) == (43_000, 30_000)
    assert wod.movements[0].load_rx_m_g == 43_000 and wod.movements[0].load_rx_f_g == 30_000
    nuevo = {**cuerpo["movements"][0], "load_rx_m_g": 50_000}
    editado = await _patch(session, admin.id, wod.id, movements=[nuevo])
    assert editado.movements[0].load_rx_m_g == 50_000


async def test_lista_de_semana_y_busqueda(
    session: AsyncSession, usuario_real: CrearUsuario, sonda: _Sonda
) -> None:
    admin = await usuario_real("admin")
    thr, pul, snc, wbl, dl = await _movs(
        session, admin.id, "Thruster", "Pull-up", "Snatch", "Wall ball", "Deadlift"
    )
    fran = await make_benchmark(session, admin.id, "Fran", "time")
    await make_wod(session, admin.id, [thr, pul, snc, wbl], benchmark_id=str(fran.id))
    await make_wod(
        session, admin.id, [dl], date="2026-10-19", title="Lunes pesado",
        score_type="load", time_cap_s=None,
    )  # fmt: skip
    await make_wod(
        session, admin.id, [dl], date="2026-11-03", title="Fuera de semana",
        score_type="reps", time_cap_s=None,
    )  # fmt: skip
    semana = await service.list_wods(session, WodListQuery(week="2026-W43"), PAGINA)
    assert [w.date.day for w in semana.items] == [19, 22] and semana.total == 2
    fila = semana.items[1]
    assert (fila.movement_count, fila.is_benchmark, fila.benchmark_name) == (4, True, "Fran")
    assert fila.movement_names == ["Thruster", "Pull-up", "Snatch"]  # los tres primeros
    busqueda = await service.list_wods(session, WodListQuery(), PAGINA, q="FRÁN")
    assert [w.title for w in busqueda.items] == ["Fran"]
    solo = await service.list_wods(session, WodListQuery(benchmark=True), PAGINA)
    assert [w.title for w in solo.items] == ["Fran"]
    sin = await service.list_wods(session, WodListQuery(benchmark=False), PAGINA)
    assert {w.title for w in sin.items} == {"Lunes pesado", "Fuera de semana"}
    pagina = await service.list_wods(session, SIN_FILTROS, PageParams(limit=2, offset=1))
    assert pagina.total == 3 and [w.date.day for w in pagina.items] == [22, 19]  # recientes primero
    with pytest.raises(WodsValidationError) as mezcla:
        await service.list_wods(session, WodListQuery(week="2026-W43", benchmark=True), PAGINA)
    assert mezcla.value.field == "week"
    with pytest.raises(WodsValidationError) as con_q:
        await service.list_wods(session, WodListQuery(week="2026-W43"), PAGINA, q="x")
    assert con_q.value.field == "week"
    with pytest.raises(WodsValidationError):
        await service.list_wods(session, WodListQuery(week="2026-43"), PAGINA)


async def test_la_lista_pide_los_resultados_una_vez_por_pagina(
    session: AsyncSession, usuario_real: CrearUsuario, sonda: _Sonda
) -> None:
    admin = await usuario_real("admin")
    (thr,) = await _movs(session, admin.id, "Thruster")
    ids = [
        (await make_wod(session, admin.id, [thr], date=f"2026-10-{20 + i}")).id for i in range(3)
    ]
    sonda.cuentas[ids[0]] = 5
    sonda.llamadas.clear()
    pagina = await service.list_wods(session, SIN_FILTROS, PAGINA)
    assert len(sonda.llamadas) == 1 and set(sonda.llamadas[0]) == set(ids)
    assert {w.id: w.result_count for w in pagina.items}[ids[0]] == 5


async def test_el_benchmark_inexistente_en_un_patch_da_422(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    (thr,) = await _movs(session, admin.id, "Thruster")
    wod = await make_wod(session, admin.id, [thr])
    with pytest.raises(WodsValidationError) as error:
        await _patch(session, admin.id, wod.id, benchmark_id=str(UUID(int=5)))
    assert error.value.field == "benchmark_id"


async def test_alta_con_benchmark_toma_for_share_y_un_update_concurrente_espera(
    engine: AsyncEngine, dos_sesiones: tuple[AsyncSession, AsyncSession]
) -> None:
    """El alta de un WOD con `benchmark_id` lee el benchmark `FOR SHARE`: un `UPDATE` concurrente
    del `score_type` del benchmark espera a que el WOD confirme (si no, quedaría un WOD con otro
    tipo de marca que su benchmark)."""
    primera, segunda = dos_sesiones
    actor = SYSTEM_USER_ID
    with actor_scope(actor):
        movimiento = await service.create_movement(
            primera, MovementCreate(name="Thruster", category="weightlifting", unit="kg"), actor
        )
        bench = await service.create_benchmark(
            primera, BenchmarkCreate(name="Fran", description="", score_type="time"), actor
        )
        await primera.commit()
        cuerpo = cuerpo_wod([movimiento.id], benchmark_id=str(bench.id))
        await service.create_wod(segunda, WodCreate.model_validate(cuerpo), actor)
    # sin commit: el WOD retiene el `FOR SHARE` del benchmark
    otra = async_sessionmaker(engine)()
    try:
        await otra.execute(text("SET LOCAL lock_timeout = '300ms'"))
        with pytest.raises(DBAPIError) as error:
            await otra.execute(
                text("UPDATE wods.benchmarks SET score_type = 'reps' WHERE id = :i"),
                {"i": bench.id},
            )
        assert getattr(error.value.orig, "sqlstate", None) == "55P03"
    finally:
        await otra.rollback()
        await otra.close()
        await segunda.rollback()


async def test_con_resultados_el_movimiento_principal_no_cambia(
    session: AsyncSession, usuario_real: CrearUsuario, sonda: _Sonda
) -> None:
    """S8-A3b (M-2): reemplazar la lista con resultados no puede mover el principal (los RM de
    Q19 y RN-12 quedarían atribuidos a otro movimiento). Sin resultados, sí se puede."""
    admin = await usuario_real("admin")
    thr, pul = await _movs(session, admin.id, "Thruster", "Pull-up")
    wod = await make_wod(session, admin.id, [thr, pul])  # Thruster es el principal
    cambia = cuerpo_wod([pul, thr])["movements"]  # ahora el principal es Pull-up
    sin_principal = [dict(m, is_primary=False) for m in cuerpo_wod([thr, pul])["movements"]]
    otra_lista = [*cuerpo_wod([thr, pul])["movements"]]
    otra_lista[0] = dict(otra_lista[0], reps="5")
    otra_lista[1] = dict(otra_lista[1], reps="7")
    sonda.cuentas[wod.id] = 2
    for cuerpo in (cambia, sin_principal):
        with pytest.raises(LockedByResults) as error:
            await _patch(session, admin.id, wod.id, movements=cuerpo)
        assert error.value.field == "movements"
    quieto = await service.get_wod(session, wod.id)
    assert [(m.movement_name, m.is_primary) for m in quieto.movements] == [
        ("Thruster", True),
        ("Pull-up", False),
    ]
    # el mismo principal con otras repeticiones sí se edita
    ok = await _patch(session, admin.id, wod.id, movements=otra_lista)
    assert [m.reps for m in ok.movements] == ["5", "7"] and ok.movements[0].is_primary
    # sin resultados el principal se puede mover
    sonda.cuentas[wod.id] = 0
    movido = await _patch(session, admin.id, wod.id, movements=cambia)
    assert [(m.movement_name, m.is_primary) for m in movido.movements] == [
        ("Pull-up", True),
        ("Thruster", False),
    ]


async def test_carrera_real_de_dos_altas_con_la_misma_fecha_en_dos_sesiones(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    """S8-A3b: dos conexiones reales dan de alta el WOD del mismo día a la vez; gana una y la otra
    recibe 409 `wod_date_taken` con el id del ganador. Las dos sesiones siguen usables."""
    una, otra = dos_sesiones
    actor = SYSTEM_USER_ID
    with actor_scope(actor):
        mov = await service.create_movement(
            una, MovementCreate(name="Thruster", category="weightlifting", unit="kg"), actor
        )
        await una.commit()

    async def alta(sesion: AsyncSession, titulo: str) -> WodOut | WodDateTaken:
        with actor_scope(actor):
            try:
                cuerpo = WodCreate.model_validate(cuerpo_wod([mov.id], title=titulo))
                salida = await service.create_wod(sesion, cuerpo, actor)
                await sesion.commit()
                return salida
            except WodDateTaken as error:
                await sesion.rollback()
                return error

    resultados = await asyncio.gather(alta(una, "Uno"), alta(otra, "Dos"))
    ganadores = [r for r in resultados if isinstance(r, WodOut)]
    perdedores = [r for r in resultados if isinstance(r, WodDateTaken)]
    assert len(ganadores) == 1 and len(perdedores) == 1
    assert perdedores[0].existing_id == ganadores[0].id
    for sesion in (una, otra):
        assert (await sesion.execute(text("SELECT count(*) FROM wods.wods"))).scalar_one() == 1


async def test_dos_patch_del_mismo_wod_se_serializan_con_for_update(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    """S8-A3b: dos `PATCH` a la vez del mismo WOD: el segundo espera el `FOR UPDATE` y parte de lo
    que dejó el primero (el `before` del segundo es el `after` del primero)."""
    una, otra = dos_sesiones
    actor = SYSTEM_USER_ID
    with actor_scope(actor):
        mov = await service.create_movement(
            una, MovementCreate(name="Thruster", category="weightlifting", unit="kg"), actor
        )
        wod = await service.create_wod(una, WodCreate.model_validate(cuerpo_wod([mov.id])), actor)
        await una.commit()

    async def parchar(sesion: AsyncSession, titulo: str) -> None:
        with actor_scope(actor):
            await service.update_wod(sesion, wod.id, WodPatch(title=titulo), actor)
            await sesion.commit()

    await asyncio.gather(parchar(una, "Uno"), parchar(otra, "Dos"))
    filas = (
        await una.execute(
            text(
                "SELECT before->>'title', after->>'title' FROM audit.audit_log "
                "WHERE table_name = 'wods.wods' AND action = 'update' AND record_id = :i "
                "ORDER BY seq"
            ),
            {"i": wod.id},
        )
    ).all()
    assert len(filas) == 2
    assert filas[0][0] == "Fran" and filas[1][0] == filas[0][1]
    assert {filas[0][1], filas[1][1]} == {"Uno", "Dos"}


async def test_patch_del_wod_con_benchmark_y_patch_del_score_type_del_benchmark_a_la_vez(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    """S8-A3b: mientras un `PATCH /wods` que fija `benchmark_id` no confirma (retiene el `FOR SHARE`
    del benchmark), el `PATCH /benchmarks` del `score_type` espera y no se cuela; al confirmar el
    WOD, el cambio ya no procede (422 `score_type_locked`)."""
    una, otra = dos_sesiones
    actor = SYSTEM_USER_ID
    with actor_scope(actor):
        mov = await service.create_movement(
            una, MovementCreate(name="Thruster", category="weightlifting", unit="kg"), actor
        )
        bench = await service.create_benchmark(
            una, BenchmarkCreate(name="Fran", description="", score_type="time"), actor
        )
        wod = await service.create_wod(una, WodCreate.model_validate(cuerpo_wod([mov.id])), actor)
        await una.commit()
        await service.update_wod(una, wod.id, WodPatch(benchmark_id=bench.id), actor)
    # `una` no confirma: retiene el FOR SHARE del benchmark
    await otra.execute(text("SET LOCAL lock_timeout = '300ms'"))
    with actor_scope(actor):
        with pytest.raises((DatabaseBusy, DBAPIError)):
            await service.update_benchmark(otra, bench.id, BenchmarkPatch(score_type="reps"), actor)
    await otra.rollback()
    await una.commit()
    with actor_scope(actor):
        with pytest.raises(ScoreTypeLocked):
            await service.update_benchmark(otra, bench.id, BenchmarkPatch(score_type="reps"), actor)
    await otra.rollback()
