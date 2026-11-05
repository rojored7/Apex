"""Exportación de pagos a CSV (S5-B12, US-139; S5-D41, S5-D42, S5-D60, S5-D246 a S5-D250).
Privado de `payments`: solo lo importa `payments/service.py` (`export_payments`).

Mismo flujo que la de socios (`members/exports.py`), sin el bus de cifrado: funciona con el
custodio sellado (salvo `q`, que busca socios por índice ciego). `prepare` valida el rango
(`from` y `to` obligatorios, `[from, to)`, a lo sumo 12 meses: 422 con `field`), cuenta con el
tope (422 `export_too_large`) y audita la apertura; `_cuerpo` abre su PROPIA sesión por lote con
`db.get_sessionmaker()` y recorre por la llave `(paid_at, id)` sin OFFSET.

Cuadre (S5-D42): usa `build_filters` de la lista y el mismo mes civil de Bogotá que `summary`, así
la suma de los no anulados del CSV es `total_cop` del resumen del mismo rango.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Final
from uuid import UUID, uuid4

import anyio
from sqlalchemy import ColumnElement, Select, func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit, db
from app.core.alerts import alert
from app.core.clock import BOGOTA, current_clock
from app.core.export import ExportStream, ExportTooLarge, csv_header, csv_rows, escape_formula
from app.modules.members import service as members_service
from app.modules.payments import queries
from app.modules.payments.exceptions import InvalidDateRange
from app.modules.payments.models import Payment
from app.modules.payments.rules import PaymentFilters, build_filters, check_date_range
from app.modules.payments.schemas import PaymentDetail, PaymentExportQuery
from app.modules.settings import service as settings_service

logger = logging.getLogger("app.payments.export")

BATCH_SIZE: Final = 500
HEADER: Final[tuple[str, ...]] = (
    "fecha",
    "socio",
    "plan",
    "monto",
    "medio",
    "referencia",
    "registrado_por",
    "anulado",
    "motivo_anulacion",
)
TABLE: Final = "payments.payments"
FECHA_HORA: Final = "%Y-%m-%d %H:%M"

Fila = builtins.list[str | int]
Llave = tuple[datetime, UUID]
Condiciones = Sequence[ColumnElement[bool]]


def _check_range(filters: PaymentExportQuery) -> None:
    """Rango válido de la lista y, además, a lo sumo 12 meses de Bogotá (S5-D250): `to`."""
    check_date_range(filters.from_, filters.to, current_clock().today_bogota())
    desde = filters.from_.astimezone(BOGOTA)
    dia = 28 if (desde.month, desde.day) == (2, 29) else desde.day  # 29 de febrero
    limite = desde.replace(year=desde.year + 1, day=dia)
    if filters.to.astimezone(BOGOTA) > limite:
        raise InvalidDateRange(field="to")


def _as_filters(filters: PaymentExportQuery) -> PaymentFilters:
    return PaymentFilters(
        q=filters.q,
        from_=filters.from_,
        to=filters.to,
        method=filters.method,
        registered_by=filters.registered_by,
        voided=filters.voided,
        member_id=filters.member_id,
        membership_id=filters.membership_id,
    )


def _texto(valor: object) -> str:
    return "" if valor is None else escape_formula(str(valor))


def _fila(detalle: PaymentDetail, etiquetas: dict[str, str]) -> Fila:
    """Las nueve columnas de N-29 de un pago; el monto es entero y no se escapa."""
    socio = f"{detalle.member_first_name} {detalle.member_last_name}".strip()
    return [
        detalle.paid_at.astimezone(BOGOTA).strftime(FECHA_HORA),
        _texto(socio),
        _texto(detalle.plan_name),
        detalle.amount_cop,
        _texto(etiquetas.get(detalle.method, detalle.method)),
        _texto(detalle.reference),
        _texto(detalle.registered_by_name),
        "si" if detalle.voided else "no",
        _texto(detalle.void_reason),
    ]


def _siguiente(condiciones: Condiciones, despues_de: Llave | None) -> Select[Payment]:
    """El lote que sigue a `despues_de` por la llave `(paid_at, id)`; sin OFFSET."""
    consulta = select(Payment).where(*condiciones)
    if despues_de is not None:
        pasado = tuple_(
            literal(despues_de[0], Payment.paid_at.type), literal(despues_de[1], Payment.id.type)
        )
        consulta = consulta.where(tuple_(Payment.paid_at, Payment.id) > pasado)
    return consulta.order_by(Payment.paid_at, Payment.id).limit(BATCH_SIZE)


async def _leer_lote(
    condiciones: Condiciones, despues_de: Llave | None, etiquetas: dict[str, str]
) -> tuple[builtins.list[Fila], Llave | None]:
    """Un lote con sesión propia (solo lectura); sin lote devuelve `([], None)`."""
    async with db.get_sessionmaker()() as sesion:
        pagos = builtins.list(await sesion.scalars(_siguiente(condiciones, despues_de)))
        if not pagos:
            return [], None
        detalles = await queries.details_for(sesion, pagos)
        await sesion.commit()
    return [_fila(d, etiquetas) for d in detalles], (pagos[-1].paid_at, pagos[-1].id)


async def _cerrar(export_id: UUID, by: UUID, *, completed: bool, rows_sent: int) -> None:
    """La fila de cierre en sesión propia, blindada contra la cancelación (S5-D248)."""
    with anyio.CancelScope(shield=True):
        try:
            async with db.get_sessionmaker()() as sesion:
                await audit.record(
                    sesion,
                    action="export",
                    table_name=TABLE,
                    record_id=export_id,
                    before=None,
                    after={"completed": completed, "rows_sent": rows_sent},
                    user_id=by,
                )
                await sesion.commit()
        except Exception as error:
            tipo = type(error).__name__
            logger.error("payments export: cierre sin registrar", extra={"error_type": tipo})
            alert("export_close_lost", table=TABLE, error_type=tipo)


async def _cuerpo(
    condiciones: Condiciones,
    etiquetas: dict[str, str],
    export_id: UUID,
    by: UUID,
    max_rows: int,
) -> AsyncIterator[bytes]:
    """El CSV en streaming: cabecera y un fragmento por lote; el cierre en `finally`."""
    enviadas = 0
    completo = False
    try:
        yield csv_header(HEADER)
        despues_de: Llave | None = None
        while True:
            filas, despues_de = await _leer_lote(condiciones, despues_de, etiquetas)
            if not filas:
                completo = True
                break
            sobran = len(filas) > max_rows - enviadas
            if sobran:  # altas concurrentes tras el conteo: el tope también rige aquí (S5-D253)
                filas = filas[: max_rows - enviadas]
            enviadas += len(filas)  # ya en manos del consumidor al suspender en `yield`
            if filas:
                yield csv_rows(filas)
            if sobran:
                break
            if len(filas) < BATCH_SIZE:
                completo = True
                break
    finally:
        await _cerrar(export_id, by, completed=completo, rows_sent=enviadas)


async def prepare(
    session: AsyncSession, filters: PaymentExportQuery, *, by: UUID, ip: str, max_rows: int
) -> ExportStream:
    """Valida el rango y el tope y audita la apertura; ver el docstring del módulo."""
    _check_range(filters)
    socios: set[UUID] = set()
    if filters.q is not None and filters.q.strip():
        socios = await members_service.search_ids(session, filters.q, include_deleted=True)
    condiciones = build_filters(_as_filters(filters), socios)
    total = int(
        await session.scalar(select(func.count()).select_from(Payment).where(*condiciones)) or 0
    )
    if total > max_rows:
        raise ExportTooLarge()
    etiquetas = {m.code: m.label for m in await settings_service.payment_methods(session)}
    export_id = uuid4()
    await audit.record(
        session,
        action="export",
        table_name=TABLE,
        record_id=export_id,
        before=None,
        after={
            "filters": filters.model_dump(mode="json", by_alias=True, exclude={"q"}),
            "has_q": bool(filters.q and filters.q.strip()),
            "rows": total,
            "fields": builtins.list(HEADER),
            "ip": ip,
        },
        user_id=by,
    )
    nombre = f"pagos-{current_clock().today_bogota():%Y%m%d}.csv"
    return ExportStream(
        export_id=export_id,
        rows=total,
        filename=nombre,
        body=lambda: _cuerpo(condiciones, etiquetas, export_id, by, max_rows),
    )


__all__ = ["BATCH_SIZE", "HEADER", "TABLE", "prepare"]
