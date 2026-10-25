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
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import chunked
from app.modules.payments.models import Payment
from app.modules.payments.rules import PaymentFingerprint


async def sum_not_voided(session: AsyncSession, membership_id: UUID) -> int:
    consulta = select(func.coalesce(func.sum(Payment.amount_cop), 0)).where(
        Payment.membership_id == membership_id, Payment.voided.is_(False)
    )
    return int(await session.scalar(consulta) or 0)


async def sums_not_voided(session: AsyncSession, membership_ids: Iterable[UUID]) -> dict[UUID, int]:
    buscados = list(dict.fromkeys(membership_ids))
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
) -> list[PaymentFingerprint]:
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
