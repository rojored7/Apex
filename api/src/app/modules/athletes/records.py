"""Récords personales manuales (S9-B1, US-180; S9-D8, S9-D9, S9-D10, S9-D12, S9-D14).

- `add_record`: valida la forma y los rangos (422 con `field`, sin repetir el valor), toma
  `lock_member` ANTES de comprobar que el socio exista y no esté dado de baja (404
  `member_not_found`, S9-D14), lee el movimiento o el benchmark con `FOR SHARE` por
  `wods.service.movement_for_record` / `benchmark_for_record` (un `PATCH` del catálogo concurrente
  espera, S9-D9), valida la marca con `results.service.validate_score` (sin `capped`; arista
  `athletes -> results`, S9-D51) e inserta con `source = "manual"`. Emite `PersonalRecordSet`
  SOLO si el nuevo queda vigente: uno menor o igual se guarda como histórico (RN-12, N-45).
- `list_records`: página por `achieved_on` y `created_at` descendentes; `is_current` por UNA
  consulta de los vigentes de los objetivos presentes; nombres del catálogo por lote.
Un récord no es dato de salud: no pide autorización de datos ni cifra nada.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from typing import Final, Literal
from uuid import UUID

from sqlalchemy import (
    Select,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import current_clock
from app.core.errors import ForbiddenError
from app.core.locks import lock_member
from app.core.pagination import Page, PageParams, paginate, to_page
from app.modules.athletes import derive
from app.modules.athletes.events import PersonalRecordSet
from app.modules.athletes.exceptions import (
    RecordAlreadyInvalidated,
    RecordDuplicate,
    RecordIsDerived,
    RecordNotFound,
    RecordValidationError,
)
from app.modules.athletes.models import PersonalRecord
from app.modules.athletes.queries import KIND_SQL, current_query, row_of
from app.modules.athletes.rules import (
    EARLIEST_MEASURED_ON,
    Objective,
    RecordKind,
    RecordRow,
    as_kind,
    can_void,
    pick_current,
)
from app.modules.athletes.schemas import RecordIn, RecordOut
from app.modules.auth import service as auth_service
from app.modules.members import service as members_service
from app.modules.results import service as results_service
from app.modules.results.exceptions import ResultValidationError
from app.modules.wods import service as wods_service

logger = logging.getLogger("app.athletes")

VALUE_MIN_G: Final = 1
VALUE_MAX_G: Final = 1_000_000
RM_UNIT: Final = "kg"
_MARK_FIELDS: Final[tuple[str, ...]] = ("seconds", "rounds", "reps", "load_g")


# Campo de `validate_score` -> campo de `RecordIn` (L3). Lo desconocido (`wod_id`: el tipo del
# benchmark no registra marcas) apunta al benchmark.
_SCORE_FIELD_MAP: Final[dict[str, str]] = {
    "seconds": "seconds",
    "rounds": "rounds",
    "reps": "reps",
    "load_g": "load_g",
    "level": "level",
    "capped": "level",
    "scaled_movement_ids": "level",
}


def _fail(field: str, message: str) -> RecordValidationError:
    return RecordValidationError(message=message, field=field)


def _check_shape(data: RecordIn, today: date) -> None:
    """Combinación de campos por `kind`, rangos y fecha. Sin tocar la base."""
    if not EARLIEST_MEASURED_ON <= data.achieved_on <= today:
        raise _fail("achieved_on", "La fecha del récord no es válida.")
    if data.kind == "rm":
        if data.movement_id is None:
            raise _fail("movement_id", "Indica el movimiento.")
        if data.value_g is None:
            raise _fail("value_g", "Indica la carga.")
        if not VALUE_MIN_G <= data.value_g <= VALUE_MAX_G:
            raise _fail("value_g", "El valor está fuera del rango permitido.")
        if data.benchmark_id is not None:
            raise _fail("benchmark_id", "Un RM no lleva benchmark.")
        for campo in ("level", *_MARK_FIELDS):
            if getattr(data, campo) is not None:
                raise _fail(campo, "Este campo no corresponde a un RM.")
        return
    if data.benchmark_id is None:
        raise _fail("benchmark_id", "Indica el benchmark.")
    if data.level is None:
        raise _fail("level", "Indica el nivel.")
    if data.movement_id is not None:
        raise _fail("movement_id", "Un récord de benchmark no lleva movimiento.")
    if data.value_g is not None:
        raise _fail("value_g", "Un récord de benchmark no lleva carga de RM.")


def _objective_of(record: PersonalRecord) -> Objective:
    destino = record.movement_id if record.kind == "rm" else record.benchmark_id
    if destino is None:  # la forma de la tabla (CHECK) lo impide
        raise ValueError("récord sin objetivo")
    return Objective(as_kind(record.kind), destino)


def list_query(
    member_id: UUID, *, kind: RecordKind | None, include_invalidated: bool
) -> Select[PersonalRecord]:
    """La lista del socio con orden total: fecha, alta e id descendentes."""
    consulta = select(PersonalRecord).where(PersonalRecord.member_id == member_id)
    if kind is not None:
        consulta = consulta.where(PersonalRecord.kind == KIND_SQL[kind])
    if not include_invalidated:
        consulta = consulta.where(PersonalRecord.invalidated_at.is_(None))
    return consulta.order_by(
        PersonalRecord.achieved_on.desc(),
        PersonalRecord.created_at.desc(),
        PersonalRecord.id.desc(),
    )


async def _current_ids(
    session: AsyncSession,
    member_id: UUID,
    objectives: set[Objective],
    score_types: dict[UUID, str],
) -> set[UUID]:
    """Ids de los récords vigentes de esos objetivos, con UNA consulta."""
    movimientos = {o.target_id for o in objectives if o.kind == "rm"}
    benchmarks = {o.target_id for o in objectives if o.kind == "benchmark"}
    if not movimientos and not benchmarks:
        return set()
    filas = await session.scalars(current_query(member_id, movimientos, benchmarks))
    grupos: dict[Objective, list[RecordRow]] = defaultdict(list)
    for fila in filas:
        grupos[_objective_of(fila)].append(row_of(fila))
    vigentes: set[UUID] = set()
    for objetivo, registros in grupos.items():
        tipo = score_types.get(objetivo.target_id) if objetivo.kind == "benchmark" else None
        if objetivo.kind == "benchmark" and tipo is None:
            continue
        elegido = pick_current(registros, score_type=tipo)
        if elegido is not None:
            vigentes.add(elegido.id)
    return vigentes


def _to_out(
    record: PersonalRecord,
    *,
    is_current: bool,
    movement_name: str | None,
    benchmark_name: str | None,
    score_type: str | None,
    names: dict[UUID, str],
    result_source: str | None = None,
) -> RecordOut:
    return RecordOut(
        id=record.id,
        kind=record.kind,
        movement_id=record.movement_id,
        movement_name=movement_name,
        benchmark_id=record.benchmark_id,
        benchmark_name=benchmark_name,
        score_type=score_type,
        value_g=record.value_g,
        level=record.level,
        seconds=record.seconds,
        rounds=record.rounds,
        reps=record.reps,
        load_g=record.load_g,
        capped=record.capped,
        achieved_on=record.achieved_on,
        source=record.source,
        result_id=record.result_id,
        result_source=result_source,
        wod_id=record.wod_id,
        is_current=is_current and record.invalidated_at is None,
        invalidated_at=record.invalidated_at,
        invalidated_reason=record.invalidated_reason,
        recorded_by=record.created_by,
        recorded_by_name=names.get(record.created_by),
        created_at=record.created_at,
    )


async def _resolve_target(
    session: AsyncSession, data: RecordIn
) -> tuple[str | None, str | None, str | None]:
    """Lee el objetivo con `FOR SHARE` y valida la marca. Devuelve (nombre del movimiento, nombre
    del benchmark, tipo de marca)."""
    if data.kind == "rm":
        assert data.movement_id is not None and data.value_g is not None  # noqa: S101
        movimiento = await wods_service.movement_for_record(session, data.movement_id)
        if movimiento is None or not movimiento.is_active or movimiento.unit != RM_UNIT:
            raise _fail("movement_id", "El movimiento no existe, está inactivo o no se mide en kg.")
        return movimiento.name, None, None
    assert data.benchmark_id is not None and data.level is not None  # noqa: S101
    benchmark = await wods_service.benchmark_for_record(session, data.benchmark_id)
    if benchmark is None:
        raise _fail("benchmark_id", "El benchmark no existe.")
    try:
        results_service.validate_score(
            score_type=benchmark.score_type,
            time_cap_s=None,
            level=data.level,
            seconds=data.seconds,
            rounds=data.rounds,
            reps=data.reps,
            load_g=data.load_g,
            capped=False,
            scaled_movement_ids=(),
            wod_movement_ids=frozenset(),
        )
    except ResultValidationError as error:
        # L3: el cliente no ve «WOD» ni campos que `RecordIn` no tiene.
        campo = _SCORE_FIELD_MAP.get(error.field or "", "benchmark_id")
        raise _fail(campo, "La marca no corresponde al tipo de marca del benchmark.") from None
    return None, benchmark.name, benchmark.score_type


async def _reject_duplicate(session: AsyncSession, member_id: UUID, data: RecordIn) -> None:
    """L1: sin tope de manuales, el mismo récord vivo (socio, objetivo, marca y fecha) dos veces es
    un doble envío: 409. Bajo `lock_member` no hay carrera. Compara con `IS NOT DISTINCT FROM`."""
    consulta = select(PersonalRecord.id).where(
        PersonalRecord.member_id == member_id,
        PersonalRecord.invalidated_at.is_(None),
        PersonalRecord.kind == KIND_SQL[data.kind],
        PersonalRecord.achieved_on == data.achieved_on,
        PersonalRecord.movement_id.is_not_distinct_from(data.movement_id),
        PersonalRecord.benchmark_id.is_not_distinct_from(data.benchmark_id),
        PersonalRecord.value_g.is_not_distinct_from(data.value_g),
        PersonalRecord.level.is_not_distinct_from(data.level),
        PersonalRecord.seconds.is_not_distinct_from(data.seconds),
        PersonalRecord.rounds.is_not_distinct_from(data.rounds),
        PersonalRecord.reps.is_not_distinct_from(data.reps),
        PersonalRecord.load_g.is_not_distinct_from(data.load_g),
    )
    if await session.scalar(consulta.limit(1)) is not None:
        raise RecordDuplicate()


def _new_record(member_id: UUID, data: RecordIn, by: UUID) -> PersonalRecord:
    return PersonalRecord(
        created_by=by,
        member_id=member_id,
        kind=data.kind,
        movement_id=data.movement_id,
        benchmark_id=data.benchmark_id,
        value_g=data.value_g,
        level=data.level,
        seconds=data.seconds,
        rounds=data.rounds,
        reps=data.reps,
        load_g=data.load_g,
        capped=False,
        achieved_on=data.achieved_on,
        source="manual",
    )


async def add_record(
    session: AsyncSession, member_id: UUID, data: RecordIn, *, by: UUID
) -> RecordOut:
    """Alta de un récord manual (201). Orden de candados: socio, catálogo `FOR SHARE`, cadena."""
    _check_shape(data, current_clock().today_bogota())
    await lock_member(session, member_id)
    await members_service.ensure_exists(session, member_id)
    movement_name, benchmark_name, score_type = await _resolve_target(session, data)
    await _reject_duplicate(session, member_id, data)
    record = _new_record(member_id, data, by)
    session.add(record)
    await session.flush()
    types = {data.benchmark_id: score_type} if data.benchmark_id and score_type else {}
    vigentes = await _current_ids(session, member_id, {_objective_of(record)}, types)
    es_vigente = record.id in vigentes
    if es_vigente:  # un menor o igual queda como histórico y no emite (RN-12, N-45)
        await events.emit(
            PersonalRecordSet(
                record_id=record.id,
                member_id=member_id,
                kind=data.kind,
                movement_id=data.movement_id,
                benchmark_id=data.benchmark_id,
                source="manual",
                achieved_on=data.achieved_on,
            ),
            session,
        )
    names = await auth_service.user_names_for(session, [by])
    return _to_out(
        record,
        is_current=es_vigente,
        movement_name=movement_name,
        benchmark_name=benchmark_name,
        score_type=score_type,
        names=names,
    )


async def list_records(
    session: AsyncSession,
    member_id: UUID,
    page: PageParams,
    *,
    kind: Literal["rm", "benchmark"] | None = None,
    include_invalidated: bool = False,
) -> Page[RecordOut]:
    """Récords del socio (también dado de baja), por fecha y alta descendentes."""
    await members_service.ensure_exists(session, member_id, include_deleted=True)
    filas, total = await paginate(
        session,
        list_query(member_id, kind=kind, include_invalidated=include_invalidated),
        page,
    )
    return to_page(await _present(session, member_id, filas), total, page)


async def _present(
    session: AsyncSession, member_id: UUID, filas: Sequence[PersonalRecord]
) -> list[RecordOut]:
    """Nombres del catálogo y de quien registró por lote, y `is_current` con UNA consulta."""
    if not filas:
        return []
    movimientos = await wods_service.movement_refs(
        session, {f.movement_id for f in filas if f.movement_id}
    )
    benchmarks = await wods_service.benchmark_refs(
        session, {f.benchmark_id for f in filas if f.benchmark_id}
    )
    tipos = {b.id: b.score_type for b in benchmarks.values()}
    vigentes = await _current_ids(session, member_id, {_objective_of(f) for f in filas}, tipos)
    names = await auth_service.user_names_for(session, list({f.created_by for f in filas}))
    # L-4: el origen del resultado (escritorio o tablet), por lote y solo de los derivados.
    origenes = await results_service.result_sources(
        session, {f.result_id for f in filas if f.result_id}
    )
    salida: list[RecordOut] = []
    for fila in filas:
        movimiento = movimientos.get(fila.movement_id) if fila.movement_id else None
        benchmark = benchmarks.get(fila.benchmark_id) if fila.benchmark_id else None
        salida.append(
            _to_out(
                fila,
                is_current=fila.id in vigentes,
                movement_name=movimiento.name if movimiento else None,
                benchmark_name=benchmark.name if benchmark else None,
                score_type=benchmark.score_type if benchmark else None,
                names=names,
                result_source=origenes.get(fila.result_id) if fila.result_id else None,
            )
        )
    return salida


async def _manual_to_invalidate(
    session: AsyncSession, member_id: UUID, record_id: UUID, *, by: UUID, role: str
) -> PersonalRecord:
    """Candado del socio, socio vivo y el récord `FOR UPDATE`, con las reglas M-3, derivado y ya
    invalidado en ese orden (S9-D13)."""
    await lock_member(session, member_id)
    await members_service.ensure_exists(session, member_id)
    record = await session.scalar(
        select(PersonalRecord)
        .where(PersonalRecord.id == record_id, PersonalRecord.member_id == member_id)
        .with_for_update(of=PersonalRecord)
        .execution_options(populate_existing=True)
    )
    if record is None:
        raise RecordNotFound()
    permitido = can_void(
        role=role,
        caller=by,
        recorded_by=record.created_by,
        created_at=record.created_at,
        now=current_clock().now_utc(),
    )
    if not permitido:
        # M-3: el 403 no deja fila de auditoría; el aviso lleva usuario y récord, sin socio.
        logger.warning(
            "athletes: invalidación denegada",
            extra={"user_id": str(by), "record_id": str(record.id)},
        )
        raise ForbiddenError()
    if record.source != "manual":
        raise RecordIsDerived()
    if record.invalidated_at is not None:
        raise RecordAlreadyInvalidated()
    return record


async def invalidate_manual_record(
    session: AsyncSession, member_id: UUID, record_id: UUID, *, by: UUID, role: str
) -> RecordOut:
    """Invalida un récord MANUAL vivo (S9-B5, US-181; S9-D13, S9-D33; M-3, L-3). Sin cuerpo.

    Orden: `lock_member`, socio vivo (404 `member_not_found`, S9-D14), el récord `FOR UPDATE`
    releído con datos frescos y de ESE socio (404 `record_not_found`), la regla M-3 (`can_void` con
    `created_by` y `created_at`: el coach solo lo suyo y en 24 h, 403 `forbidden`; el admin todo),
    409 `record_is_derived` (un derivado se corrige corrigiendo o anulando el resultado) y 409
    `record_already_invalidated`. Luego, por ORM (auditoría `update` con el actor), pone
    `invalidated_reason = manual_error`, `invalidated_at` y `updated_at` con `clock_timestamp()`
    (S9-D52) e `invalidated_by`, y repone el mejor con la misma regla que la derivación (S9-D11).
    Devuelve el `RecordOut` invalidado. Sin evento nuevo ni texto libre."""
    record = await _manual_to_invalidate(session, member_id, record_id, by=by, role=role)
    ahora = (await session.execute(select(func.clock_timestamp()))).scalar_one()
    record.invalidated_at = ahora
    record.updated_at = ahora
    record.invalidated_reason = "manual_error"
    record.invalidated_by = by
    await session.flush()
    objetivo = _objective_of(record)
    await derive.restore_after_manual(
        session, member_id, kind=objetivo.kind, target_id=objetivo.target_id
    )
    logger.info("athletes: récord manual invalidado", extra={"record_id": str(record.id)})
    return await _invalidated_out(session, record)


async def _invalidated_out(session: AsyncSession, record: PersonalRecord) -> RecordOut:
    """El `RecordOut` de un récord recién invalidado, con los nombres del catálogo y del autor."""
    movimientos = await wods_service.movement_refs(
        session, {record.movement_id} if record.movement_id else set()
    )
    benchmarks = await wods_service.benchmark_refs(
        session, {record.benchmark_id} if record.benchmark_id else set()
    )
    movimiento = movimientos.get(record.movement_id) if record.movement_id else None
    benchmark = benchmarks.get(record.benchmark_id) if record.benchmark_id else None
    names = await auth_service.user_names_for(session, [record.created_by])
    return _to_out(
        record,
        is_current=False,
        movement_name=movimiento.name if movimiento else None,
        benchmark_name=benchmark.name if benchmark else None,
        score_type=benchmark.score_type if benchmark else None,
        names=names,
    )
