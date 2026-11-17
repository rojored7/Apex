"""Récords vivos bloquean la unidad del movimiento y el tipo de marca del benchmark (S9-B2, S9-D9).

Con un doble del puerto `RecordsProbe` (la consulta real se prueba en
`tests/athletes/test_records_probe.py`): con récords vivos, `PATCH /movements/{id}` no cambia
`unit` y `PATCH /benchmarks/{id}` no cambia `score_type` (422 `locked_by_records` con `field`);
con solo invalidados quedan libres; sin puerto falla cerrado (`RecordsProbeNotRegistered`).
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.wods import service
from app.modules.wods.exceptions import LockedByRecords, RecordsProbeNotRegistered, WodsError
from app.modules.wods.schemas import BenchmarkPatch, MovementPatch
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.users import make_user
from tests.factories.wods import make_benchmark, make_movement

MOVS = "/api/v1/movements"
BENCHS = "/api/v1/benchmarks"


class _Doble:
    """Puerto de prueba: `vivos` = ids con récords NO invalidados."""

    def __init__(self, vivos: set[UUID]) -> None:
        self.vivos = vivos
        self.llamadas = 0

    async def movement_has_records(self, session: AsyncSession, movement_id: UUID) -> bool:
        self.llamadas += 1
        return movement_id in self.vivos

    async def benchmark_has_records(self, session: AsyncSession, benchmark_id: UUID) -> bool:
        self.llamadas += 1
        return benchmark_id in self.vivos


@pytest.fixture
def puerto_doble() -> Iterator[_Doble]:
    anterior = service.current_records_probe()
    doble = _Doble(set())
    service.set_records_probe(doble)
    try:
        yield doble
    finally:
        service.set_records_probe(anterior)


async def test_la_unidad_con_records_vivos_no_cambia_422_con_field(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    puerto_doble: _Doble,
) -> None:
    admin = await usuario_real("admin")
    mov = await make_movement(session, admin.id, name="Récord unidad", unit="kg")
    puerto_doble.vivos.add(mov.id)
    h = cabeceras(admin)
    r = await app_http.patch(f"{MOVS}/{mov.id}", json={"unit": "reps"}, headers=h)
    assert r.status_code == 422, r.text
    assert (r.json()["error"]["code"], r.json()["error"]["field"]) == ("locked_by_records", "unit")
    # Lo que no es la unidad sigue editable, y la misma unidad no es un cambio.
    renombrar = await app_http.patch(f"{MOVS}/{mov.id}", json={"name": "Otro"}, headers=h)
    assert renombrar.status_code == 200
    igual = await app_http.patch(f"{MOVS}/{mov.id}", json={"unit": "kg"}, headers=h)
    assert igual.status_code == 200


async def test_la_unidad_con_solo_invalidados_cambia(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    puerto_doble: _Doble,
) -> None:
    admin = await usuario_real("admin")
    mov = await make_movement(session, admin.id, name="Libre unidad", unit="kg")
    r = await app_http.patch(f"{MOVS}/{mov.id}", json={"unit": "reps"}, headers=cabeceras(admin))
    assert r.status_code == 200 and r.json()["unit"] == "reps"
    assert puerto_doble.llamadas == 1


async def test_el_tipo_de_marca_con_records_vivos_no_cambia_422_con_field(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    puerto_doble: _Doble,
) -> None:
    admin = await usuario_real("admin")
    bm = await make_benchmark(session, admin.id, name="Récord tipo", score_type="time")
    libre = await make_benchmark(session, admin.id, name="Libre tipo", score_type="time")
    puerto_doble.vivos.add(bm.id)
    h = cabeceras(admin)
    r = await app_http.patch(f"{BENCHS}/{bm.id}", json={"score_type": "reps"}, headers=h)
    assert r.status_code == 422, r.text
    assert (r.json()["error"]["code"], r.json()["error"]["field"]) == (
        "locked_by_records",
        "score_type",
    )
    renombrar = await app_http.patch(f"{BENCHS}/{bm.id}", json={"name": "Otro"}, headers=h)
    assert renombrar.status_code == 200
    ok = await app_http.patch(f"{BENCHS}/{libre.id}", json={"score_type": "reps"}, headers=h)
    assert ok.status_code == 200 and ok.json()["score_type"] == "reps"


async def test_sin_puerto_falla_cerrado_en_ambos_catalogos(session: AsyncSession) -> None:
    admin = await make_user(session, role="admin")
    mov = await make_movement(session, admin.id, name="Sin puerto mov", unit="kg")
    bm = await make_benchmark(session, admin.id, name="Sin puerto bm", score_type="time")
    admin_id, mov_id, bm_id = admin.id, mov.id, bm.id  # el rollback expira los ORM
    anterior = service.current_records_probe()
    service.set_records_probe(None)
    try:
        with actor_scope(admin_id):
            with pytest.raises(RecordsProbeNotRegistered):
                await service.update_movement(
                    session, mov_id, MovementPatch.model_validate({"unit": "reps"}), admin_id
                )
            await session.rollback()
            with pytest.raises(RecordsProbeNotRegistered):
                await service.update_benchmark(
                    session, bm_id, BenchmarkPatch.model_validate({"score_type": "reps"}), admin_id
                )
            await session.rollback()
    finally:
        service.set_records_probe(anterior)
    assert issubclass(RecordsProbeNotRegistered, RuntimeError)


def test_locked_by_records_es_un_error_de_dominio_422_con_field() -> None:
    error = LockedByRecords("unit")
    assert isinstance(error, WodsError)
    assert (error.status, error.code, error.field) == (422, "locked_by_records", "unit")
