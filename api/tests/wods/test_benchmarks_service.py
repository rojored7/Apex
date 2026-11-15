"""`wods.service` de benchmarks con base real (S8-A2, US-166, N-46; S8-D6). Rojo A2.

`score_type_locked` usa un doble de `wod_counts` (la tabla de WODs llega en A3, que lo reemplaza
por la consulta real sobre `wods.wods`).
"""

from __future__ import annotations

from typing import Any
from unittest import mock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.pagination import PageParams
from app.modules.wods import benchmarks as benchmarks_module
from app.modules.wods import service
from app.modules.wods.exceptions import (
    BenchmarkExists,
    BenchmarkNotFound,
    ScoreTypeLocked,
    WodsValidationError,
)
from app.modules.wods.schemas import (
    BenchmarkCreate,
    BenchmarkListQuery,
    BenchmarkOut,
    BenchmarkPatch,
)
from tests.conftest import CrearUsuario

PAGINA = PageParams(limit=50, offset=0)
SIN_FILTROS = BenchmarkListQuery()


def _crear(**cambios: Any) -> BenchmarkCreate:
    valores: dict[str, Any] = {"name": "Fran", "description": "21-15-9", "score_type": "time"}
    valores.update(cambios)
    return BenchmarkCreate.model_validate(valores)


async def _alta(session: AsyncSession, actor: UUID, **cambios: Any) -> BenchmarkOut:
    with actor_scope(actor):
        salida = await service.create_benchmark(session, _crear(**cambios), actor)
        await session.commit()
    return salida


async def _cambio(session: AsyncSession, actor: UUID, bid: UUID, **cambios: Any) -> BenchmarkOut:
    with actor_scope(actor):
        salida = await service.update_benchmark(
            session, bid, BenchmarkPatch.model_validate(cambios), actor
        )
        await session.commit()
    return salida


async def test_el_alta_guarda_nombre_normalizado_y_audita(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    salida = await _alta(session, admin.id, name="  Fran  ")
    assert (salida.name, salida.score_type, salida.wod_count) == ("Fran", "time", 0)
    consulta = text("SELECT * FROM wods.benchmarks WHERE id = :i")
    fila = (await session.execute(consulta, {"i": salida.id})).mappings().one()
    assert fila["name_norm"] == "fran" and fila["created_by"] == admin.id
    acciones = (
        await session.execute(
            text("SELECT action FROM audit.audit_log WHERE record_id = :i"), {"i": salida.id}
        )
    ).all()
    assert [a[0] for a in acciones] == ["insert"]


async def test_409_benchmark_exists(session: AsyncSession, usuario_real: CrearUsuario) -> None:
    admin = await usuario_real("admin")
    primero = await _alta(session, admin.id, name="Fran")
    with pytest.raises(BenchmarkExists) as error:
        await _alta(session, admin.id, name=" FRAN ")
    assert error.value.status == 409 and error.value.code == "benchmark_exists"
    assert error.value.field == "name" and error.value.existing_id == primero.id
    otro = await _alta(session, admin.id, name="Grace")
    with pytest.raises(BenchmarkExists) as patch_error:
        await _cambio(session, admin.id, otro.id, name="fran")
    assert patch_error.value.existing_id == primero.id
    mismo = await _cambio(session, admin.id, primero.id, name="FRAN")  # su propio name_norm
    assert mismo.name == "FRAN"


async def test_description_hasta_2000(session: AsyncSession, usuario_real: CrearUsuario) -> None:
    admin = await usuario_real("admin")
    largo = await _alta(session, admin.id, name="Largo", description="x" * 2000)
    assert len(largo.description) == 2000
    vacio = await _alta(session, admin.id, name="Vacio", description="")
    assert vacio.description == ""
    sin = BenchmarkCreate.model_validate({"name": "Sin", "score_type": "reps"})
    assert sin.description == ""
    with pytest.raises(ValidationError):
        _crear(description="x" * 2001)


async def test_patch_solo_cambia_lo_enviado_y_sin_cambios_no_audita(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    b = await _alta(session, admin.id)
    cambiado = await _cambio(session, admin.id, b.id, description="otra")
    assert (cambiado.name, cambiado.description, cambiado.score_type) == ("Fran", "otra", "time")
    await _cambio(session, admin.id, b.id, name="Fran", score_type="time")
    cuenta = await session.scalar(
        text("SELECT count(*) FROM audit.audit_log WHERE record_id = :i"), {"i": b.id}
    )
    assert cuenta == 2  # alta + un solo cambio real


async def test_patch_con_null_explicito_da_422_con_field(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    b = await _alta(session, admin.id)
    for campo in ("name", "description", "score_type"):
        with pytest.raises(WodsValidationError) as error:
            await _cambio(session, admin.id, b.id, **{campo: None})
        assert error.value.field == campo


async def test_404_de_inexistente(session: AsyncSession, usuario_real: CrearUsuario) -> None:
    admin = await usuario_real("admin")
    with pytest.raises(BenchmarkNotFound):
        await _cambio(session, admin.id, uuid4(), name="X")
    with pytest.raises(BenchmarkNotFound):
        await service.get_benchmark(session, uuid4())


async def test_patch_score_type_con_wods_da_422_score_type_locked(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    b = await _alta(session, admin.id)

    async def con_wods(_s: AsyncSession, ids: list[UUID]) -> dict[UUID, int]:
        return dict.fromkeys(ids, 2)

    with mock.patch.object(benchmarks_module, "wod_counts", con_wods):
        with pytest.raises(ScoreTypeLocked) as error:
            await _cambio(session, admin.id, b.id, score_type="reps")
        assert error.value.status == 422 and error.value.field == "score_type"
        # El mismo valor no es un cambio; y lo demás sí se edita aunque haya WODs.
        igual = await _cambio(session, admin.id, b.id, score_type="time", description="nueva")
        assert igual.description == "nueva" and igual.wod_count == 2
    libre = await _cambio(session, admin.id, b.id, score_type="reps")
    assert libre.score_type == "reps"


async def test_lista_filtra_busca_pagina_y_ordena_por_nombre_normalizado(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    await _alta(session, admin.id, name="Zeta", score_type="reps")
    await _alta(session, admin.id, name="Álamo", score_type="load")
    await _alta(session, admin.id, name="Murph", score_type="time")
    todo = await service.list_benchmarks(session, SIN_FILTROS, PAGINA)
    assert sorted(b.name for b in todo.items) == ["Murph", "Zeta", "Álamo"]
    nombres = [b.name for b in todo.items]
    assert nombres.index("Murph") < nombres.index("Zeta")  # orden por `name_norm`
    carga = await service.list_benchmarks(session, BenchmarkListQuery(score_type="load"), PAGINA)
    assert [b.name for b in carga.items] == ["Álamo"]
    sin_tilde = await service.list_benchmarks(session, SIN_FILTROS, PAGINA, q="alamo")
    assert [b.name for b in sin_tilde.items] == ["Álamo"]
    pag = await service.list_benchmarks(session, SIN_FILTROS, PageParams(limit=1, offset=2))
    assert pag.total == 3 and len(pag.items) == 1
    comodin = await service.list_benchmarks(session, SIN_FILTROS, PAGINA, q="%")
    assert comodin.total == 0


async def test_wod_count_en_una_consulta_por_pagina(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    ids = [(await _alta(session, admin.id, name=f"B {i}")).id for i in range(3)]
    llamadas: list[list[UUID]] = []

    async def espia(_s: AsyncSession, pedidos: list[UUID]) -> dict[UUID, int]:
        llamadas.append(list(pedidos))
        return {ids[0]: 4}

    with mock.patch.object(benchmarks_module, "wod_counts", espia):
        pagina = await service.list_benchmarks(session, SIN_FILTROS, PAGINA)
    assert len(llamadas) == 1 and set(llamadas[0]) == set(ids)
    assert {b.id: b.wod_count for b in pagina.items} == {ids[0]: 4, ids[1]: 0, ids[2]: 0}


async def test_la_carrera_23505_da_409_con_existing_id_y_la_sesion_sigue_viva(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """El índice único decide cuando la comprobación previa no ve al otro alta (S8-A1b)."""
    admin = await usuario_real("admin")
    primero = await _alta(session, admin.id, name="Fran")
    otro = await _alta(session, admin.id, name="Grace")
    original = benchmarks_module._id_by_norm
    llamadas: list[int] = []

    async def parcheada(s: AsyncSession, norm: str, *, exclude: UUID | None) -> UUID | None:
        llamadas.append(1)
        return None if len(llamadas) == 1 else await original(s, norm, exclude=exclude)

    with mock.patch.object(benchmarks_module, "_id_by_norm", parcheada):
        with pytest.raises(BenchmarkExists) as alta:
            await _alta(session, admin.id, name=" FRAN ")
    assert alta.value.existing_id == primero.id
    llamadas.clear()
    with mock.patch.object(benchmarks_module, "_id_by_norm", parcheada):
        with pytest.raises(BenchmarkExists) as cambio:
            await _cambio(session, admin.id, otro.id, name="fran")
    assert cambio.value.existing_id == primero.id
    lista = await service.list_benchmarks(session, SIN_FILTROS, PAGINA)
    assert lista.total == 2
    assert (await _cambio(session, admin.id, otro.id, description="ok")).description == "ok"
