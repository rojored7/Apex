"""Programación de WODs (S8-A3, US-166, US-167; S8-D7, S8-D8). Privado: lo usa `service.py`.

- `create_wod(session, data, by)`: valida (`validate_wod`), exige movimientos activos del catálogo y
  el `score_type` del benchmark (leído `FOR SHARE`: un `PATCH /benchmarks` concurrente espera a que
  el WOD confirme), copia el nombre de cada movimiento, guarda el WOD y su lista, y emite
  `WodPublished`. La carrera de dos altas con la misma fecha la decide `uq_wods_date` dentro de un
  savepoint (`_guardar_unico`: el cambio se aplica DENTRO del savepoint, S8-A1b) y sale como 409
  `wod_date_taken` con la sesión usable.
- `update_wod(session, wod_id, patch, by)`: `FOR UPDATE` del WOD, el puerto `ResultsProbe` bajo ese
  candado (con resultados no cambian `score_type`, `date`, `time_cap_s` ni `benchmark_id`) y, si
  llega `movements`, REEMPLAZA la lista completa (borrado e inserción auditados fila a fila).
  Solo acepta movimientos activos salvo los que el WOD ya tenía, que además conservan su nombre
  copiado. Sin cambios no hay `flush` ni auditoría.
- `get_wod` y `list_wods`: `GET /wods?week=` (7 días sin paginar) o `?q&benchmark` (paginado); los
  dos modos se excluyen (422 `field = "week"`). Los resultados se piden al puerto UNA vez por página
  y los movimientos y los benchmarks, en una consulta cada uno.
No hay borrado (RN-14; los triggers de la base también lo prohíben).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import date
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Text, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core import events
from app.core.db import violated_constraint
from app.core.pagination import Page, PageParams, paginate, to_page
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern, sql_fold
from app.modules.wods.catalog import benchmark_for_share, movements_by_id
from app.modules.wods.events import WodPublished
from app.modules.wods.exceptions import (
    LockedByResults,
    ScoreTypeLocked,
    ScoreTypeMismatch,
    WodDateTaken,
    WodNotFound,
    WodsValidationError,
)
from app.modules.wods.models import Benchmark, Movement, Wod, WodMovement
from app.modules.wods.probe import results_probe
from app.modules.wods.rules import MovementSpec, validate_wod, week_dates
from app.modules.wods.schemas import (
    WodCreate,
    WodListQuery,
    WodMovementIn,
    WodMovementOut,
    WodOut,
    WodPatch,
    WodRowOut,
)

logger = logging.getLogger("app.wods")

UQ_DATE: Final = "uq_wods_date"
WEEK_DAYS: Final = 7
NAMES_IN_ROW: Final = 3
_NO_NULOS: Final[tuple[str, ...]] = ("title", "date", "score_type", "description", "movements")
_BLOQUEADOS: Final[tuple[str, ...]] = ("date", "time_cap_s", "benchmark_id")
_MENSAJE_NULO: Final = "Este campo no puede quedar vacío."
_Aplicar = Callable[[], Awaitable[None]]


async def _id_by_date(session: AsyncSession, dia: date, *, exclude: UUID | None) -> UUID | None:
    consulta = select(Wod.id).where(Wod.date == dia)
    if exclude is not None:
        consulta = consulta.where(Wod.id != exclude)
    return await session.scalar(consulta)


async def _guardar_unico(
    session: AsyncSession, dia: date, exclude: UUID | None, aplicar: _Aplicar
) -> None:
    """Aplica el cambio y hace `flush` DENTRO de un savepoint (`begin_nested()` vacía lo pendiente
    antes de abrirlo). El 23505 de `uq_wods_date` (la carrera de dos altas) es 409 `wod_date_taken`
    y la sesión sigue usable (S8-A1b)."""
    try:
        async with session.begin_nested():
            await aplicar()
            await session.flush()
    except IntegrityError as error:
        if violated_constraint(error) != UQ_DATE:
            raise
        raise WodDateTaken(await _id_by_date(session, dia, exclude=exclude)) from None


# Lecturas ---------------------------------------------------------------------------------------


async def _movement_rows(session: AsyncSession, wod_ids: Sequence[UUID]) -> list[WodMovement]:
    if not wod_ids:
        return []
    filas = await session.scalars(
        select(WodMovement)
        .where(WodMovement.wod_id.in_(list(wod_ids)))
        .order_by(WodMovement.wod_id, WodMovement.position)
        .execution_options(populate_existing=True)
    )
    return list(filas)


async def _benchmark_names(session: AsyncSession, ids: Sequence[UUID | None]) -> dict[UUID, str]:
    reales = {i for i in ids if i is not None}
    if not reales:
        return {}
    filas = await session.execute(
        select(Benchmark.id, Benchmark.name).where(Benchmark.id.in_(reales))
    )
    return {fila[0]: fila[1] for fila in filas}


def _out(
    wod: Wod, movs: Sequence[WodMovement], bench_name: str | None, result_count: int
) -> WodOut:
    return WodOut.model_validate(
        {
            "id": wod.id,
            "date": wod.date,
            "title": wod.title,
            "score_type": wod.score_type,
            "time_cap_s": wod.time_cap_s,
            "benchmark_id": wod.benchmark_id,
            "benchmark_name": bench_name,
            "is_benchmark": wod.benchmark_id is not None,
            "description": wod.description,
            "movements": [WodMovementOut.model_validate(m, from_attributes=True) for m in movs],
            "result_count": result_count,
            "created_at": wod.created_at,
            "updated_at": wod.updated_at,
        }
    )


async def _full_out(session: AsyncSession, wod: Wod, result_count: int) -> WodOut:
    movs = await _movement_rows(session, [wod.id])
    nombres = await _benchmark_names(session, [wod.benchmark_id])
    nombre = nombres.get(wod.benchmark_id) if wod.benchmark_id is not None else None
    return _out(wod, movs, nombre, result_count)


async def _locked(session: AsyncSession, wod_id: UUID) -> Wod:
    wod = await session.scalar(
        select(Wod)
        .where(Wod.id == wod_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if wod is None:
        raise WodNotFound()
    return wod


# Validación del cuerpo --------------------------------------------------------------------------


async def _specs_and_catalog(
    session: AsyncSession, movements: Sequence[WodMovementIn], *, ya_tenia: frozenset[UUID]
) -> tuple[list[MovementSpec], dict[UUID, Movement]]:
    """Los movimientos del cuerpo contra el catálogo: existen y están activos (salvo los que el
    WOD ya tenía). 422 con `field = movements.<i>.movement_id`."""
    catalogo = await movements_by_id(session, [m.movement_id for m in movements])
    specs: list[MovementSpec] = []
    for indice, mov in enumerate(movements):
        fila = catalogo.get(mov.movement_id)
        if fila is None or not (fila.is_active or mov.movement_id in ya_tenia):
            raise WodsValidationError(
                message="El movimiento no existe o está inactivo.",
                field=f"movements.{indice}.movement_id",
            )
        specs.append(
            MovementSpec(
                position=mov.position,
                is_primary=mov.is_primary,
                unit=fila.unit,
                load_rx_m_g=mov.load_rx_m_g,
                load_rx_f_g=mov.load_rx_f_g,
            )
        )
    return specs, catalogo


async def _check_benchmark(
    session: AsyncSession, benchmark_id: UUID | None, score_type: str
) -> None:
    """El benchmark existe y su `score_type` es el del WOD. Se lee `FOR SHARE`."""
    if benchmark_id is None:
        return
    bench = await benchmark_for_share(session, benchmark_id)
    if bench is None:
        raise WodsValidationError(message="El benchmark no existe.", field="benchmark_id")
    if bench.score_type != score_type:
        raise ScoreTypeMismatch()


def _new_rows(
    wod_id: UUID,
    movements: Sequence[WodMovementIn],
    catalogo: dict[UUID, Movement],
    nombres_previos: dict[UUID, str],
    by: UUID,
) -> list[WodMovement]:
    """Filas nuevas por posición. El nombre se COPIA del catálogo, salvo el de un movimiento que el
    WOD ya tenía: conserva su copia (renombrar el catálogo no cambia un WOD pasado)."""
    return [
        WodMovement(
            wod_id=wod_id,
            movement_id=m.movement_id,
            movement_name=nombres_previos.get(m.movement_id, catalogo[m.movement_id].name),
            position=m.position,
            reps=m.reps,
            load_rx_m_g=m.load_rx_m_g,
            load_rx_f_g=m.load_rx_f_g,
            notes=m.notes,
            is_primary=m.is_primary,
            created_by=by,
        )
        for m in sorted(movements, key=lambda x: x.position)
    ]


# Casos de uso -----------------------------------------------------------------------------------


async def create_wod(session: AsyncSession, data: WodCreate, by: UUID) -> WodOut:
    """Alta de un WOD con su lista de movimientos (US-166)."""
    specs, catalogo = await _specs_and_catalog(session, data.movements, ya_tenia=frozenset())
    validate_wod(data.score_type, data.time_cap_s, specs)
    await _check_benchmark(session, data.benchmark_id, data.score_type)
    existente = await _id_by_date(session, data.date, exclude=None)
    if existente is not None:
        raise WodDateTaken(existente)
    wod = Wod(
        date=data.date,
        title=data.title,
        score_type=data.score_type,
        time_cap_s=data.time_cap_s,
        benchmark_id=data.benchmark_id,
        description=data.description,
        created_by=by,
    )
    filas = _new_rows(wod.id, data.movements, catalogo, {}, by)

    async def aplicar() -> None:
        session.add(wod)
        await session.flush()  # el WOD antes que sus movimientos (FK)
        session.add_all(filas)

    await _guardar_unico(session, data.date, None, aplicar)
    await events.emit(WodPublished(wod_id=wod.id, wod_date=wod.date), session)
    logger.info("wods: wod creado", extra={"wod_id": str(wod.id), "movements": len(filas)})
    return await _full_out(session, wod, 0)


def _changes(wod: Wod, patch: WodPatch) -> dict[str, Any]:
    """Lo enviado que difiere de lo guardado. `time_cap_s` y `benchmark_id` admiten `null`."""
    for campo in _NO_NULOS:
        if campo in patch.model_fields_set and getattr(patch, campo) is None:
            raise WodsValidationError(message=_MENSAJE_NULO, field=campo)
    campos = ("date", "title", "score_type", "time_cap_s", "benchmark_id", "description")
    return {
        c: getattr(patch, c)
        for c in campos
        if c in patch.model_fields_set and getattr(patch, c) != getattr(wod, c)
    }


def _same_list(actuales: Sequence[WodMovement], nuevos: Sequence[WodMovementIn]) -> bool:
    def clave_actual(m: WodMovement) -> tuple[Any, ...]:
        return (
            m.movement_id,
            m.position,
            m.reps,
            m.load_rx_m_g,
            m.load_rx_f_g,
            m.notes,
            m.is_primary,
        )

    def clave_nueva(m: WodMovementIn) -> tuple[Any, ...]:
        return (
            m.movement_id,
            m.position,
            m.reps,
            m.load_rx_m_g,
            m.load_rx_f_g,
            m.notes,
            m.is_primary,
        )

    return [clave_actual(m) for m in actuales] == [
        clave_nueva(m) for m in sorted(nuevos, key=lambda x: x.position)
    ]


async def _specs_of_current(
    session: AsyncSession, actuales: Sequence[WodMovement]
) -> list[MovementSpec]:
    catalogo = await movements_by_id(session, [m.movement_id for m in actuales])
    return [
        MovementSpec(
            position=m.position,
            is_primary=m.is_primary,
            unit=catalogo[m.movement_id].unit,
            load_rx_m_g=m.load_rx_m_g,
            load_rx_f_g=m.load_rx_f_g,
        )
        for m in actuales
    ]


async def _check_locks(session: AsyncSession, wod: Wod, cambios: dict[str, Any]) -> int:
    """Resultados del WOD (puerto, con el candado del WOD ya tomado: nadie registra otros a la
    vez). Con resultados, `score_type`, `date`, `time_cap_s` y `benchmark_id` no cambian."""
    resultados = (await results_probe().result_counts(session, [wod.id])).get(wod.id, 0)
    if resultados > 0:
        if "score_type" in cambios:
            raise ScoreTypeLocked()
        for campo in _BLOQUEADOS:
            if campo in cambios:
                raise LockedByResults(campo)
    return resultados


async def _validate_update(
    session: AsyncSession,
    wod: Wod,
    cambios: dict[str, Any],
    patch: WodPatch,
    actuales: Sequence[WodMovement],
) -> dict[UUID, Movement]:
    """Valida el estado final del WOD (forma, benchmark y fecha) y devuelve el catálogo."""
    final_tipo = cambios.get("score_type", wod.score_type)
    final_cap = cambios["time_cap_s"] if "time_cap_s" in cambios else wod.time_cap_s
    final_bench = cambios["benchmark_id"] if "benchmark_id" in cambios else wod.benchmark_id
    catalogo: dict[UUID, Movement] = {}
    if patch.movements is not None:
        ya_tenia = frozenset(m.movement_id for m in actuales)
        specs, catalogo = await _specs_and_catalog(session, patch.movements, ya_tenia=ya_tenia)
    else:
        specs = await _specs_of_current(session, actuales)
    validate_wod(final_tipo, final_cap, specs)
    await _check_benchmark(session, final_bench, final_tipo)
    if "date" in cambios:
        otro = await _id_by_date(session, cambios["date"], exclude=wod.id)
        if otro is not None:
            raise WodDateTaken(otro)
    return catalogo


async def update_wod(session: AsyncSession, wod_id: UUID, patch: WodPatch, by: UUID) -> WodOut:
    """`PATCH` de un WOD: solo lo enviado; `movements` reemplaza la lista completa."""
    wod = await _locked(session, wod_id)
    cambios = _changes(wod, patch)
    resultados = await _check_locks(session, wod, cambios)
    actuales = await _movement_rows(session, [wod.id])
    catalogo = await _validate_update(session, wod, cambios, patch, actuales)
    nueva_lista = patch.movements if patch.movements is not None else None
    reemplaza = nueva_lista is not None and not _same_list(actuales, nueva_lista)
    if not cambios and not reemplaza:
        return await _full_out(session, wod, resultados)
    nombres_previos = {m.movement_id: m.movement_name for m in reversed(actuales)}
    nuevas = (
        _new_rows(wod.id, nueva_lista, catalogo, nombres_previos, by)
        if reemplaza and nueva_lista is not None
        else []
    )

    async def aplicar() -> None:
        for campo, valor in cambios.items():
            setattr(wod, campo, valor)
        if not cambios:
            flag_modified(wod, "title")  # solo cambia la lista: `onupdate` mueve `updated_at`
        await session.flush()
        if reemplaza:
            for vieja in actuales:
                await session.delete(vieja)
            await session.flush()  # borrar antes de insertar: posición y principal son únicos
            session.add_all(nuevas)

    await _guardar_unico(session, cambios.get("date", wod.date), wod.id, aplicar)
    logger.info(
        "wods: wod editado",
        extra={
            "wod_id": str(wod.id),
            "changed_fields": sorted(cambios) + (["movements"] if reemplaza else []),
            "actor": str(by),
        },
    )
    return await _full_out(session, wod, resultados)


async def get_wod(session: AsyncSession, wod_id: UUID) -> WodOut:
    probe = results_probe()
    wod = await session.get(Wod, wod_id)
    if wod is None:
        raise WodNotFound()
    cuentas = await probe.result_counts(session, [wod.id])
    return await _full_out(session, wod, cuentas.get(wod.id, 0))


async def _rows(session: AsyncSession, wods: Sequence[Wod]) -> list[WodRowOut]:
    probe = results_probe()  # falla cerrado también con la página vacía
    if not wods:
        return []
    ids = [w.id for w in wods]
    cuentas = await probe.result_counts(session, ids)
    por_wod: dict[UUID, list[str]] = {i: [] for i in ids}
    for mov in await _movement_rows(session, ids):
        por_wod[mov.wod_id].append(mov.movement_name)
    nombres = await _benchmark_names(session, [w.benchmark_id for w in wods])
    return [
        WodRowOut.model_validate(
            {
                "id": w.id,
                "date": w.date,
                "title": w.title,
                "score_type": w.score_type,
                "time_cap_s": w.time_cap_s,
                "benchmark_id": w.benchmark_id,
                "benchmark_name": nombres.get(w.benchmark_id) if w.benchmark_id else None,
                "is_benchmark": w.benchmark_id is not None,
                "movement_count": len(por_wod[w.id]),
                "movement_names": por_wod[w.id][:NAMES_IN_ROW],
                "result_count": cuentas.get(w.id, 0),
            }
        )
        for w in wods
    ]


async def list_wods(
    session: AsyncSession, filters: WodListQuery, page: PageParams, *, q: str | None = None
) -> Page[WodRowOut]:
    """`GET /wods`: `week` (7 días, sin paginar) o `q` (título, sin tildes ni mayúsculas) y
    `benchmark`, paginado. Combinarlos da 422 con `field = "week"`."""
    termino = clean_query(q)
    if filters.week is not None:
        if termino or filters.benchmark is not None:
            raise WodsValidationError(
                message="La semana no se combina con la búsqueda ni con el filtro de benchmarks.",
                field="week",
            )
        lunes, domingo = week_dates(filters.week)
        consulta = select(Wod).where(Wod.date.between(lunes, domingo)).order_by(Wod.date)
        wods = list(await session.scalars(consulta.execution_options(populate_existing=True)))
        return to_page(await _rows(session, wods), len(wods), PageParams(limit=WEEK_DAYS, offset=0))
    consulta = select(Wod)
    if termino:
        patron = sql_fold(literal(contains_pattern(termino), Text))  # valor ligado
        consulta = consulta.where(sql_fold(Wod.title).ilike(patron, escape=LIKE_ESCAPE))
    if filters.benchmark is True:
        consulta = consulta.where(Wod.benchmark_id.is_not(None))
    elif filters.benchmark is False:
        consulta = consulta.where(Wod.benchmark_id.is_(None))
    wods, total = await paginate(session, consulta.order_by(Wod.date.desc(), Wod.id), page)
    return to_page(await _rows(session, wods), total, page)


async def today_card(session: AsyncSession, day: date) -> WodOut | None:
    """El WOD cuya fecha es `day` con sus movimientos, o `None` (S8-D9, US-168 CA1)."""
    probe = results_probe()
    wod = await session.scalar(
        select(Wod).where(Wod.date == day).execution_options(populate_existing=True)
    )
    if wod is None:
        return None
    cuentas = await probe.result_counts(session, [wod.id])
    return await _full_out(session, wod, cuentas.get(wod.id, 0))
