"""Revisiones de S9-B1 (seguridad L1, L3, L4/L5 y base de datos M1, L4/L5). Pruebas del Rojo de la
ronda de corrección.

- M1: las comparaciones contra las columnas de predicado de un índice parcial (`kind`) van con
  LITERAL en el SQL (S8-D50): con un parámetro el plan genérico no casa con el índice parcial.
- L1: el duplicado exacto vivo (mismo socio, objetivo, marca y fecha) da 409 `record_duplicate`.
- L3: un error de `validate_score` sale como el error propio de récords, con un `field` de
  `RecordIn` y sin el texto «WOD».
- L4/L5: el desempate final es el id (pura) y la lista se ordena también por id descendente.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.modules.athletes import queries, records
from app.modules.athletes.exceptions import RecordValidationError
from app.modules.athletes.rules import RecordRow, pick_current
from app.modules.results.exceptions import ResultValidationError
from tests.athletes._apoyo import alta_record, cuerpo_benchmark, cuerpo_rm, filas_de_records
from tests.conftest import CrearUsuario, UsuarioPrueba
from tests.factories.wods import make_benchmark, make_movement
from tests.notifications._apoyo_avisos import socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

INSTANTE = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)


@pytest.fixture
async def coach(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("coach")


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


# M1 ------------------------


def test_la_consulta_de_vigentes_lleva_kind_como_literal_y_la_columna_desnuda() -> None:
    sql = _sql(queries.current_query(uuid4(), {uuid4()}, {uuid4()}))
    assert "kind = 'rm'" in sql and "kind = 'benchmark'" in sql
    assert "invalidated_at IS NULL" in sql
    assert "= 'rm'" in sql and "%(kind" not in sql and "kind = %(" not in sql


def test_la_lista_filtrada_por_kind_lleva_el_literal() -> None:
    sql = _sql(records.list_query(uuid4(), kind="rm", include_invalidated=False))
    assert "kind = 'rm'" in sql and "kind = %(" not in sql
    assert "invalidated_at IS NULL" in sql


def test_la_lista_ordena_por_fecha_alta_e_id_descendentes() -> None:
    sql = _sql(records.list_query(uuid4(), kind=None, include_invalidated=True))
    orden = sql.split("ORDER BY", 1)[1]
    assert orden.index("achieved_on DESC") < orden.index("created_at DESC") < orden.index("id DESC")


# L4/L5: desempate final por id ------------------------


def _rm(n: int) -> RecordRow:
    return RecordRow(
        id=UUID(int=n), kind="rm", movement_id=UUID(int=9), benchmark_id=None, value_g=100_000,
        level=None, seconds=None, rounds=None, reps=None, load_g=None, capped=False,
        achieved_on=date(2026, 5, 1), created_at=INSTANTE,
    )  # fmt: skip


def test_con_todo_igual_gana_el_id_menor_sin_importar_el_orden_de_entrada() -> None:
    a, b, c = _rm(5), _rm(2), _rm(8)
    for orden in ([a, b, c], [c, b, a], [b, c, a]):
        elegido = pick_current(orden)
        assert elegido is not None and elegido.id == UUID(int=2)


# L1: duplicado exacto vivo ------------------------


async def test_el_rm_identico_vivo_da_409_record_duplicate_y_no_guarda_otra_fila(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Duplicado", "kg")
    await alta_record(session, coach.id, miembro.id, cuerpo_rm(mov.id))

    with pytest.raises(DomainError) as info:
        await alta_record(session, coach.id, miembro.id, cuerpo_rm(mov.id))

    assert (info.value.status, info.value.code) == (409, "record_duplicate")
    assert len(await filas_de_records(session, miembro.id)) == 1


async def test_el_benchmark_identico_vivo_da_409_y_otra_marca_o_fecha_no(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    bm = await make_benchmark(session, coach.id, "Dup Bm", "time")
    await alta_record(session, coach.id, miembro.id, cuerpo_benchmark(bm.id))

    with pytest.raises(DomainError) as info:
        await alta_record(session, coach.id, miembro.id, cuerpo_benchmark(bm.id))
    assert info.value.code == "record_duplicate"
    # otra marca, otra fecha u otro nivel NO son duplicado
    await alta_record(session, coach.id, miembro.id, cuerpo_benchmark(bm.id, seconds=301))
    await alta_record(
        session, coach.id, miembro.id, cuerpo_benchmark(bm.id, achieved_on="2026-10-19")
    )
    await alta_record(session, coach.id, miembro.id, cuerpo_benchmark(bm.id, level="rx_plus"))
    assert len(await filas_de_records(session, miembro.id)) == 4


async def test_el_duplicado_se_mide_por_socio_y_por_objetivo(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    uno, otro = await socio(session), await socio(session)
    mov_a = await make_movement(session, coach.id, "Dup A", "kg")
    mov_b = await make_movement(session, coach.id, "Dup B", "kg")
    await alta_record(session, coach.id, uno.id, cuerpo_rm(mov_a.id))

    await alta_record(session, coach.id, otro.id, cuerpo_rm(mov_a.id))  # otro socio
    await alta_record(session, coach.id, uno.id, cuerpo_rm(mov_b.id))  # otro movimiento


# L3: errores de la marca con los campos de RecordIn ------------------------


@pytest.mark.parametrize(
    ("campo_de_results", "campo_esperado"),
    [("wod_id", "benchmark_id"), ("capped", "level"), ("scaled_movement_ids", "level"),
     ("seconds", "seconds"), ("load_g", "load_g")],
)  # fmt: skip
async def test_un_error_de_validate_score_sale_como_error_de_records_sin_la_palabra_wod(
    campo_de_results: str,
    campo_esperado: str,
    session: AsyncSession,
    coach: UsuarioPrueba,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    miembro = await socio(session)
    bm = await make_benchmark(session, coach.id, "Mapeo", "time")

    def falla(**_: Any) -> None:
        raise ResultValidationError(
            message="Este WOD no registra resultados.", field=campo_de_results
        )

    monkeypatch.setattr(records.results_service, "validate_score", falla)

    with pytest.raises(RecordValidationError) as info:
        await alta_record(session, coach.id, miembro.id, cuerpo_benchmark(bm.id))

    assert (info.value.status, info.value.code, info.value.field) == (
        422,
        "validation_error",
        campo_esperado,
    )
    assert "WOD" not in str(info.value.message) and "wod" not in str(info.value.message).lower()
    assert await filas_de_records(session, miembro.id) == []
