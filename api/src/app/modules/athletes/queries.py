"""Consultas compartidas de los récords (S9-V7b, M3: rompe el ciclo `records` <-> `derive`).

Privado del módulo. Lo usan `records.py` (altas, listas, invalidación manual), `derive.py` (los
handlers de `results`, que corren bajo el `lock_member` del emisor) y `reads.py`. Sin candados.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, any_, bindparam, literal_column, or_, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.athletes.models import PersonalRecord
from app.modules.athletes.rules import RecordKind, RecordRow, as_kind, pick_current


def row_of(record: PersonalRecord) -> RecordRow:
    return RecordRow(
        id=record.id,
        kind=as_kind(record.kind),
        movement_id=record.movement_id,
        benchmark_id=record.benchmark_id,
        value_g=record.value_g,
        level=record.level,
        seconds=record.seconds,
        rounds=record.rounds,
        reps=record.reps,
        load_g=record.load_g,
        capped=record.capped,
        achieved_on=record.achieved_on,
        created_at=record.created_at,
        invalidated_at=record.invalidated_at,
        source=record.source,
    )


# Literales SQL (S8-D50): con `kind = $1` el plan genérico no casa con los índices parciales
# `ix_personal_records_rm` / `_bench` (cuyo predicado lleva `kind = 'rm'`). Solo estos dos textos
# constantes; nunca un valor del cliente.
KIND_SQL: Final[dict[RecordKind, ColumnElement[Any]]] = {
    "rm": literal_column("'rm'"),
    "benchmark": literal_column("'benchmark'"),
}


def current_query(
    member_id: UUID, movimientos: set[UUID], benchmarks: set[UUID]
) -> Select[PersonalRecord]:
    """Los récords NO invalidados de esos objetivos: `kind` literal y `invalidated_at IS NULL` con
    la columna desnuda, el predicado de `ix_personal_records_rm` y `_bench` (S8-D50)."""
    condiciones = []
    if movimientos:
        condiciones.append(
            and_(PersonalRecord.kind == KIND_SQL["rm"], PersonalRecord.movement_id.in_(movimientos))
        )
    if benchmarks:
        condiciones.append(
            and_(
                PersonalRecord.kind == KIND_SQL["benchmark"],
                PersonalRecord.benchmark_id.in_(benchmarks),
            )
        )
    return select(PersonalRecord).where(
        PersonalRecord.member_id == member_id,
        PersonalRecord.invalidated_at.is_(None),
        or_(*condiciones),
    )


async def current_rm(session: AsyncSession, member_id: UUID, movement_id: UUID) -> RecordRow | None:
    """El RM vigente del socio para un movimiento (UNA consulta, sin candados; N-45). Lo usa el
    handler de derivación (`derive.py`), que corre bajo el `lock_member` del emisor."""
    filas = await session.scalars(current_query(member_id, {movement_id}, set()))
    return pick_current([row_of(f) for f in filas])


async def current_benchmark(
    session: AsyncSession, member_id: UUID, benchmark_id: UUID, score_type: str
) -> RecordRow | None:
    """El récord de benchmark vigente del socio (UNA consulta, sin candados; N-45): el de menor
    `score_key` del tipo de marca. Lo usa el handler de derivación (B4)."""
    filas = await session.scalars(current_query(member_id, set(), {benchmark_id}))
    return pick_current([row_of(f) for f in filas], score_type=score_type)


async def result_ids_with_record(
    session: AsyncSession, member_id: UUID, kind: RecordKind, result_ids: Sequence[UUID]
) -> set[UUID]:
    """Los resultados de esa lista que ya tienen un récord de ese `kind`, vivo o no (UNA consulta
    por índice, sin `Seq Scan`: con el plan genérico el planificador elige
    `ix_personal_records_member_date` por el filtro de socio, medido en
    `test_v7b_revision_back.py`; `uq_personal_records_result_kind` cubre `(result_id, kind)` si el
    filtro de socio deja de ser selectivo; sin candados): la reposición no los toca (un segundo
    récord del mismo `(result_id, kind)` lo rechaza la base)."""
    if not result_ids:
        return set()
    filas = await session.scalars(
        select(PersonalRecord.result_id).where(
            PersonalRecord.member_id == member_id,
            PersonalRecord.kind == KIND_SQL[kind],
            PersonalRecord.result_id
            == any_(bindparam("ids", list(set(result_ids)), type_=ARRAY(PG_UUID(as_uuid=True)))),
        )
    )
    return {f for f in filas if f is not None}
