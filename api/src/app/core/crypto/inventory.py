"""Inventario de llaves, bitácora y trabajos, sin material (S6-D13, D14, D16, D54; S6-B1, B2).

Solo lectura: nunca escribe `crypto_ops`. La consulta nombra columnas explícitas (jamás
`wrapped_material`, `public_key` ni la referencia de las filas `sign`). `records_count` sale del
puerto `Reencryptor` si la clase lo registró (gana sobre las columnas) o de las columnas que el
registro declara; es `None` para las clases sin ninguno (`kek.backup`, `audit.signature`).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import BOGOTA, current_clock
from app.core.crypto import recovery
from app.core.crypto.discovery import encrypted_columns
from app.core.crypto.errors import CryptoError
from app.core.crypto.models import CryptoJob, CryptoKey, CryptoOp
from app.core.crypto.reencryptor import get_reencryptor
from app.core.crypto.rotate_screen import (
    ROTATE_CONFIRM_WORD as ROTATE_CONFIRM_WORD,
)
from app.core.crypto.rotate_screen import (
    RotationStarted as RotationStarted,
)
from app.core.crypto.rotate_screen import (
    start_from_screen as start_from_screen,
)
from app.core.crypto.rotate_screen import (
    validate_rotation_request as validate_rotation_request,
)
from app.core.crypto.schemas import (
    CryptoJobOut,
    CryptoKeyOut,
    CryptoOpOut,
    JobsFilters,
    KeysFilters,
    KeysSummary,
    OpsFilters,
    ProviderSummary,
)
from app.core.db import Base
from app.core.errors import ValidationFailed
from app.core.pagination import Page, PageParams
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern
from app.core.validators import check_instant_range

_SECONDS_PER_DAY = 86_400


def age_days(created_at: datetime, rotated_at: datetime | None, now: datetime) -> int:
    """Días completos entre `created_at` y `rotated_at` (o `now` si no rotó), nunca negativos."""
    fin = rotated_at if rotated_at is not None else now
    return max(int((fin - created_at).total_seconds() // _SECONDS_PER_DAY), 0)


async def records_count(session: AsyncSession, data_class: str) -> int | None:
    """Registros de la clase; `None` sin columnas ni puerto."""
    puerto = get_reencryptor(data_class)
    if puerto is not None:
        return await puerto.count_total(session)
    try:
        refs = encrypted_columns(Base.metadata, data_class)
    except CryptoError:  # clase fuera del registro: sin conteo
        return None
    if not refs:
        return None
    total = 0
    for ref in refs:
        cuantas = await session.scalar(
            select(func.count()).select_from(ref.table).where(ref.column.is_not(None))
        )
        total += int(cuantas or 0)
    return total


def _conditions(filters: KeysFilters) -> list[ColumnElement[bool]]:
    condiciones: list[ColumnElement[bool]] = []
    if filters.purpose is not None:
        condiciones.append(CryptoKey.purpose == filters.purpose)
    if filters.state is not None:
        condiciones.append(CryptoKey.state == filters.state)
    if filters.provider is not None:
        condiciones.append(CryptoKey.provider == filters.provider)
    if filters.data_class is not None:
        condiciones.append(CryptoKey.data_class == filters.data_class)
    termino = clean_query(filters.q)
    if termino:
        condiciones.append(
            CryptoKey.data_class.ilike(contains_pattern(termino), escape=LIKE_ESCAPE)
        )
    return condiciones


def _item(fila: Any, ahora: datetime, registros: int | None) -> CryptoKeyOut:
    return CryptoKeyOut(
        id=fila.id,
        purpose=fila.purpose,
        data_class=fila.data_class,
        algorithm=fila.algorithm,
        version=fila.version,
        state=fila.state,
        provider=fila.provider,
        created_at=fila.created_at,
        rotated_at=fila.rotated_at,
        age_days=age_days(fila.created_at, fila.rotated_at, ahora),
        records_count=registros,
    )


async def list_keys(
    session: AsyncSession, filters: KeysFilters, page: PageParams
) -> Page[CryptoKeyOut]:
    """Una página del inventario con orden estable `data_class, purpose, version DESC`."""
    donde = and_(True, *_conditions(filters))
    total = await session.scalar(select(func.count(CryptoKey.id)).where(donde))
    consulta = (
        select(
            CryptoKey.id,
            CryptoKey.purpose,
            CryptoKey.data_class,
            CryptoKey.algorithm,
            CryptoKey.version,
            CryptoKey.state,
            CryptoKey.provider,
            CryptoKey.created_at,
            CryptoKey.rotated_at,
        )
        .where(donde)
        .order_by(CryptoKey.data_class, CryptoKey.purpose, CryptoKey.version.desc(), CryptoKey.id)
        .limit(page.limit)
        .offset(page.offset)
    )
    filas = (await session.execute(consulta)).all()
    ahora = current_clock().now_utc()
    conteos: dict[str, int | None] = {}
    for fila in filas:
        if fila.data_class not in conteos:
            conteos[fila.data_class] = await records_count(session, fila.data_class)
    return Page[CryptoKeyOut](
        items=[_item(f, ahora, conteos[f.data_class]) for f in filas],
        total=int(total or 0),
        limit=page.limit,
        offset=page.offset,
    )


async def all_keys(session: AsyncSession) -> list[CryptoKeyOut]:
    """Todas las llaves (también `decrypt_only` y `retired`), sin paginar y sin conteos, con
    columnas explícitas (CBOM, S6-B3). Orden `data_class, purpose, version, id`."""
    consulta = select(
        CryptoKey.id,
        CryptoKey.purpose,
        CryptoKey.data_class,
        CryptoKey.algorithm,
        CryptoKey.version,
        CryptoKey.state,
        CryptoKey.provider,
        CryptoKey.created_at,
        CryptoKey.rotated_at,
    ).order_by(CryptoKey.data_class, CryptoKey.purpose, CryptoKey.version, CryptoKey.id)
    ahora = current_clock().now_utc()
    return [_item(f, ahora, None) for f in (await session.execute(consulta)).all()]


def _bogota_day_bounds(hoy: date) -> tuple[datetime, datetime]:
    inicio = datetime.combine(hoy, time.min, tzinfo=BOGOTA)
    return inicio, inicio + timedelta(days=1)


async def summary(session: AsyncSession) -> KeysSummary:
    """Bloque `summary` (S6-D13, S6-D54): activas, operaciones de hoy en Bogotá, trabajos y
    proveedores que custodian hoy (filas `active`) con su estado."""
    desde, hasta = _bogota_day_bounds(current_clock().today_bogota())
    activas = await session.scalar(
        select(func.count(CryptoKey.id)).where(CryptoKey.state == "active")
    )
    operaciones = await session.scalar(
        select(func.count(CryptoOp.id)).where(and_(CryptoOp.at >= desde, CryptoOp.at < hasta))
    )
    trabajos = await session.scalar(
        select(func.count(CryptoJob.id)).where(CryptoJob.status == "running")
    )
    nombres = (
        await session.scalars(
            select(CryptoKey.provider)
            .where(CryptoKey.state == "active")
            .distinct()
            .order_by(CryptoKey.provider)
        )
    ).all()
    return KeysSummary(
        active_count=int(activas or 0),
        operations_today=int(operaciones or 0),
        running_jobs=int(trabajos or 0),
        provider=ProviderSummary(names=list(nombres), state=recovery.current_state()),
    )


def job_percent(total: int, done: int) -> int:
    """Avance entero de un trabajo, de 0 a 100 (S6-D16): `total = 0` da 0, `done > total` da 100
    y un negativo es un error de programación (`ValueError`)."""
    if total < 0 or done < 0:
        raise ValueError("total y done no pueden ser negativos")
    if total == 0:
        return 0
    return min(done * 100 // total, 100)


MAX_OPS_RANGE = timedelta(days=366)


def _check_ops_range(filters: OpsFilters, now: datetime) -> None:
    """Rango de `from`/`to` (S6-D16): `check_instant_range` más el tope de 366 días; 422
    `validation_error` con el campo que falla y sin el valor."""
    try:
        check_instant_range(filters.start, filters.end, now=now, field_start="from", field_end="to")
    except ValueError as error:
        raise ValidationFailed(
            message="El rango de fechas no es válido.", field=str(error.args[0])
        ) from None
    if (
        filters.start is not None
        and filters.end is not None
        and filters.end - filters.start > MAX_OPS_RANGE
    ):
        raise ValidationFailed(message="El rango de fechas no puede pasar de 366 días.", field="to")


def _ops_conditions(filters: OpsFilters) -> list[ColumnElement[bool]]:
    condiciones: list[ColumnElement[bool]] = []
    if filters.start is not None:
        condiciones.append(CryptoOp.at >= filters.start)
    if filters.end is not None:
        condiciones.append(CryptoOp.at < filters.end)
    if filters.verb is not None:
        condiciones.append(CryptoOp.verb == filters.verb)
    if filters.data_class is not None:
        condiciones.append(CryptoOp.data_class == filters.data_class)
    if filters.key_id is not None:
        condiciones.append(CryptoOp.key_id == filters.key_id)
    if filters.user_id is not None:
        condiciones.append(CryptoOp.user_id == filters.user_id)
    if filters.result is not None:
        condiciones.append(CryptoOp.result == filters.result)
    if filters.batch_id is not None:
        condiciones.append(CryptoOp.batch_id == filters.batch_id)
    termino = clean_query(filters.q)
    if termino:
        condiciones.append(CryptoOp.data_class.ilike(contains_pattern(termino), escape=LIKE_ESCAPE))
    return condiciones


async def list_ops(
    session: AsyncSession, filters: OpsFilters, page: PageParams
) -> Page[CryptoOpOut]:
    """Una página de la bitácora `crypto_ops`, solo lectura, orden `at DESC, id DESC`."""
    _check_ops_range(filters, current_clock().now_utc())
    donde = and_(True, *_ops_conditions(filters))
    total = await session.scalar(select(func.count(CryptoOp.id)).where(donde))
    consulta = (
        select(
            CryptoOp.id,
            CryptoOp.at,
            CryptoOp.user_id,
            CryptoOp.verb,
            CryptoOp.data_class,
            CryptoOp.key_id,
            CryptoOp.key_version,
            CryptoOp.record_id,
            CryptoOp.purpose,
            CryptoOp.result,
            CryptoOp.batch_id,
            CryptoOp.count,
        )
        .where(donde)
        .order_by(CryptoOp.at.desc(), CryptoOp.id.desc())
        .limit(page.limit)
        .offset(page.offset)
    )
    filas = (await session.execute(consulta)).all()
    return Page[CryptoOpOut](
        items=[CryptoOpOut.model_validate(f, from_attributes=True) for f in filas],
        total=int(total or 0),
        limit=page.limit,
        offset=page.offset,
    )


def _jobs_conditions(filters: JobsFilters) -> list[ColumnElement[bool]]:
    condiciones: list[ColumnElement[bool]] = []
    if filters.status is not None:
        condiciones.append(CryptoJob.status == filters.status)
    if filters.kind is not None:
        condiciones.append(CryptoJob.kind == filters.kind)
    if filters.data_class is not None:
        condiciones.append(CryptoJob.data_class == filters.data_class)
    termino = clean_query(filters.q)
    if termino:
        condiciones.append(
            CryptoJob.data_class.ilike(contains_pattern(termino), escape=LIKE_ESCAPE)
        )
    return condiciones


async def list_jobs(
    session: AsyncSession, filters: JobsFilters, page: PageParams
) -> Page[CryptoJobOut]:
    """Una página de `crypto_jobs` con `percent`, solo lectura, orden `created_at DESC, id DESC`.
    Nunca selecciona `error`."""
    donde = and_(True, *_jobs_conditions(filters))
    total = await session.scalar(select(func.count(CryptoJob.id)).where(donde))
    consulta = (
        select(
            CryptoJob.id,
            CryptoJob.kind,
            CryptoJob.data_class,
            CryptoJob.status,
            CryptoJob.total,
            CryptoJob.done,
            CryptoJob.started_at,
            CryptoJob.finished_at,
            CryptoJob.created_at,
        )
        .where(donde)
        .order_by(CryptoJob.created_at.desc(), CryptoJob.id.desc())
        .limit(page.limit)
        .offset(page.offset)
    )
    filas = (await session.execute(consulta)).all()
    items = [
        CryptoJobOut(
            id=f.id,
            kind=f.kind,
            data_class=f.data_class,
            status=f.status,
            total=f.total,
            done=f.done,
            percent=job_percent(f.total, f.done),
            started_at=f.started_at,
            finished_at=f.finished_at,
            created_at=f.created_at,
        )
        for f in filas
    ]
    return Page[CryptoJobOut](
        items=items, total=int(total or 0), limit=page.limit, offset=page.offset
    )
