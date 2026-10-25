"""Lecturas de pagos (S3-B3: sumas, conteo y huellas recientes; B8 agrega listas, detalle y
resumen). Privado (D7).

- `sum_not_voided(session, membership_id) -> int`: suma de `amount_cop` de los pagos no anulados
  de la membresía (0 si no tiene). La usa `register` (saldo, H-1) y, desde B4, el handler de
  activación de `memberships` (D11): corre tras el `flush`, así ve el pago recién insertado.
- `sums_not_voided(session, membership_ids) -> dict[UUID, int]`: la misma suma por lote de
  `core.pagination.ID_BATCH` (`chunked`, S3-D59); todo id pedido aparece (0 si no tiene pagos) y
  sin ids no consulta la base.
- `count_not_voided(session, membership_id) -> int`: pagos no anulados de la membresía (H-2).
- `_recent_fingerprints(session, membership_id, since)`: las huellas (`rules.PaymentFingerprint`)
  de los pagos de la membresía con `created_at >= since` (H-1).

S3-B8 (US-098, US-099, US-100; D23, D26, M-4, M-8, L-2, S3-D47, S3-D51, S3-D57, S3-D80). `list`
sombrea al `list` de Python en este archivo: las anotaciones y llamadas usan `builtins.list`.
- `list(session, filters, page) -> Page[PaymentRow]`: valida el rango con
  `rules.check_date_range` y el "hoy" de Bogotá del reloj; `q` con
  `members.service.search_ids(include_deleted=True)` solo cuando hay `q`; pagina
  `select(Payment)` con `rules.build_filters` y `ORDER BY paid_at DESC, id DESC`; completa la
  página con `_enrich`. Nunca descifra.
- `get(session, payment_id) -> PaymentDetail`: 404 `payment_not_found` (`PaymentNotFound`).
- `summary(session, month=None) -> PaymentsSummary`: el mes de Bogotá (`rules.month_bounds_utc`;
  sin `month`, el de `current_clock().today_bogota()`), en una consulta con `SUM ... FILTER` y
  `COUNT ... FILTER` sobre `paid_at` en `[inicio, fin)`.
- `_enrich(session, pagos)`: nombres, plan y fechas de la membresía por
  `memberships.service.refs_for` (import perezoso, par G-03 `payments -> memberships`) y el
  correo parcial de quien registró y de quien anuló por `auth.service.names_for` y
  `rules.partial_email`; una consulta por servicio vecino por página.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.pagination import Page, PageParams, chunked, paginate, to_page
from app.modules.auth import service as auth_service
from app.modules.members import service as members_service
from app.modules.memberships.schemas import MembershipRef
from app.modules.payments.exceptions import PaymentNotFound
from app.modules.payments.models import Payment
from app.modules.payments.rules import (
    PaymentFilters,
    PaymentFingerprint,
    build_filters,
    check_date_range,
    is_backdated,
    month_bounds_utc,
    parse_month,
    partial_email,
)
from app.modules.payments.schemas import (
    PaymentDetail,
    PaymentListQuery,
    PaymentRow,
    PaymentsByMethod,
    PaymentsSummary,
)

logger = logging.getLogger("app.payments")


async def sum_not_voided(session: AsyncSession, membership_id: UUID) -> int:
    consulta = select(func.coalesce(func.sum(Payment.amount_cop), 0)).where(
        Payment.membership_id == membership_id, Payment.voided.is_(False)
    )
    return int(await session.scalar(consulta) or 0)


async def sums_not_voided(session: AsyncSession, membership_ids: Iterable[UUID]) -> dict[UUID, int]:
    buscados = builtins.list(dict.fromkeys(membership_ids))
    salida: dict[UUID, int] = dict.fromkeys(buscados, 0)
    for lote in chunked(buscados):
        consulta = (
            select(Payment.membership_id, func.sum(Payment.amount_cop))
            .where(Payment.membership_id.in_(lote), Payment.voided.is_(False))
            .group_by(Payment.membership_id)
        )
        for membership_id, total in (await session.execute(consulta)).all():
            salida[membership_id] = int(total)
    return salida


async def count_not_voided(session: AsyncSession, membership_id: UUID) -> int:
    consulta = select(func.count()).where(
        Payment.membership_id == membership_id, Payment.voided.is_(False)
    )
    return int(await session.scalar(consulta) or 0)


async def _recent_fingerprints(
    session: AsyncSession, membership_id: UUID, since: datetime
) -> builtins.list[PaymentFingerprint]:
    consulta = select(
        Payment.registered_by,
        Payment.amount_cop,
        Payment.method,
        Payment.reference,
        Payment.voided,
        Payment.created_at,
    ).where(Payment.membership_id == membership_id, Payment.created_at >= since)
    return [
        PaymentFingerprint(
            registered_by=fila.registered_by,
            amount_cop=fila.amount_cop,
            method=fila.method,
            reference=fila.reference,
            voided=fila.voided,
            registered_at=fila.created_at,
        )
        for fila in (await session.execute(consulta)).all()
    ]


async def list(  # nombre del contrato del blueprint B8 (las anotaciones usan builtins.list)
    session: AsyncSession, filters: PaymentListQuery, page: PageParams
) -> Page[PaymentRow]:
    """US-098: la página de pagos filtrada (docstring del módulo). Nunca descifra: con `q`, la
    búsqueda de socios va por índice ciego."""
    check_date_range(filters.from_, filters.to, current_clock().today_bogota())
    socios: set[UUID] = set()
    if filters.q is not None and filters.q.strip():
        socios = await members_service.search_ids(session, filters.q, include_deleted=True)
    condiciones = build_filters(_as_filters(filters), socios)
    consulta = (
        select(Payment).where(*condiciones).order_by(Payment.paid_at.desc(), Payment.id.desc())
    )
    pagos, total = await paginate(session, consulta, page)
    filas = [_as_row(detalle) for detalle in await _enrich(session, pagos)]
    return to_page(filas, total, page)


def _as_filters(filters: PaymentListQuery) -> PaymentFilters:
    return PaymentFilters(
        q=filters.q,
        from_=filters.from_,
        to=filters.to,
        method=filters.method,
        registered_by=filters.registered_by,
        voided=filters.voided,
        backdated=filters.backdated,
        member_id=filters.member_id,
        membership_id=filters.membership_id,
    )


def _as_row(detail: PaymentDetail) -> PaymentRow:
    return PaymentRow.model_validate(detail.model_dump(include=set(PaymentRow.model_fields)))


async def get(session: AsyncSession, payment_id: UUID) -> PaymentDetail:
    """US-099: el detalle de un pago; `PaymentNotFound` (404) si no existe."""
    pago = await session.get(Payment, payment_id)
    if pago is None:
        raise PaymentNotFound()
    return (await _enrich(session, [pago]))[0]


_SUMMARY_METHODS: Final = ("cash", "nequi", "breb")


async def summary(session: AsyncSession, month: str | None = None) -> PaymentsSummary:
    """US-100: el resumen del mes civil de Bogotá por `paid_at` (D23, L-13), en una sentencia:
    `SUM ... FILTER` por medio y `COUNT ... FILTER` de vigentes y anulados."""
    if month is None:
        hoy = current_clock().today_bogota()
        anio, mes = hoy.year, hoy.month
    else:
        anio, mes = parse_month(month)
    etiqueta = f"{anio:04d}-{mes:02d}"
    inicio, fin = month_bounds_utc(etiqueta)
    vigente = Payment.voided.is_(False)
    consulta = select(
        *(
            func.coalesce(
                func.sum(Payment.amount_cop).filter(vigente, Payment.method == medio), 0
            ).label(medio)
            for medio in _SUMMARY_METHODS
        ),
        func.count().filter(vigente).label("vigentes"),
        func.count().filter(Payment.voided.is_(True)).label("anulados"),
    ).where(Payment.paid_at >= inicio, Payment.paid_at < fin)
    fila = (await session.execute(consulta)).one()
    por_medio = {medio: int(getattr(fila, medio)) for medio in _SUMMARY_METHODS}
    return PaymentsSummary(
        month=etiqueta,
        total_cop=sum(por_medio.values()),
        by_method=PaymentsByMethod(**por_medio),
        voided_count=int(fila.anulados),
        payments_count=int(fila.vigentes),
    )


async def _enrich(session: AsyncSession, pagos: Sequence[Payment]) -> builtins.list[PaymentDetail]:
    """Completa los pagos con los services vecinos, por lote: una llamada a
    `memberships.refs_for` (socio, plan y fechas) y una a `auth.names_for` con quien registró y
    quien anuló a la vez (correo parcial, L-2). Sin pagos no consulta nada."""
    if not pagos:
        return []
    # lazy: G-03 (payments -> memberships)
    from app.modules.memberships import service as memberships_service

    refs = await memberships_service.refs_for(session, (p.membership_id for p in pagos))
    usuarios = {p.registered_by for p in pagos} | {p.voided_by for p in pagos if p.voided_by}
    correos = await auth_service.names_for(session, sorted(usuarios))
    return [_detail(pago, refs, correos) for pago in pagos]


def _partial_name(user_id: UUID | None, emails: dict[UUID, str]) -> str | None:
    if user_id is None or user_id not in emails:
        return None
    return partial_email(emails[user_id])


def _detail(
    pago: Payment, refs: dict[UUID, MembershipRef], emails: dict[UUID, str]
) -> PaymentDetail:
    """El detalle de un pago con su referencia de membresía. Un pago sin referencia rompería la
    integridad (las membresías, socios y planes nunca se borran físicamente): falla cerrado."""
    ref = refs.get(pago.membership_id)
    if ref is None:
        logger.error("payment without membership reference", extra={"payment_id": str(pago.id)})
        raise LookupError("payment without membership reference")
    return PaymentDetail(
        id=pago.id,
        paid_at=pago.paid_at,
        amount_cop=pago.amount_cop,
        method=pago.method,
        reference=pago.reference,
        voided=pago.voided,
        void_reason=pago.void_reason,
        registered_by=pago.registered_by,
        registered_by_name=_partial_name(pago.registered_by, emails),
        membership_id=pago.membership_id,
        member_id=pago.member_id,
        member_first_name=ref.member_first_name,
        member_last_name=ref.member_last_name,
        plan_name=ref.plan_name,
        membership_start_date=ref.start_date,
        membership_end_date=ref.end_date,
        backdated=is_backdated(pago.paid_at, pago.created_at),
        voided_by=pago.voided_by,
        voided_by_name=_partial_name(pago.voided_by, emails),
        voided_at=pago.voided_at,
        created_at=pago.created_at,
    )
