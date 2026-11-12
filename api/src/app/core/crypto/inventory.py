"""Inventario de llaves sin material (S6-D13, S6-D14, S6-D54; S6-B1, US-143).

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
from app.core.crypto.schemas import CryptoKeyOut, KeysFilters, KeysSummary, ProviderSummary
from app.core.db import Base
from app.core.pagination import Page, PageParams
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern

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
