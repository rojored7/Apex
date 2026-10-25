"""Vender una membresía (S3-B1, US-084; D3, D8, D15, D16, N-24, M-4). Privado (D7).

`sell` orquesta (menos de 50 líneas, E11) y todo su cuerpo corre dentro de
`session.begin_nested()` (D3): si un paso o un handler de `MembershipSold` falla, no queda ni
membresía ni auditoría, también dentro de la sesión con savepoint de las pruebas.

Pasos, en el orden único de candados de D3:
1. `renew=True` o `first_payment` no nulo: `NotImplementedError` hasta B6 y B4.
2. `_sale_context`: `core.locks.lock_member` (candado del socio, siempre primero);
   `members.service.get_ref` (`MemberNotFound` si no existe; `MemberInactive` si está dado de
   baja o su `status` no es `active`); `plans.service.get(for_share=True)` (`PlanNotFound` pasa a
   `PlanInvalid`; `PlanInactive` si `is_active` es falso); `settings.service.memberships_policy`
   y "hoy" de `current_clock().today_bogota()`.
3. `rules.validate_start_date` (con `max_retroactive_days=None` si
   `enforce_retroactive_limit=False`) y `rules.compute_end_date`.
4. `_check_open_memberships`: las no canceladas del socio con sus congelaciones, `effective`,
   `classify_open` (`MembershipConflict` con `existing_id`) y `find_overlap`
   (`MembershipOverlap` con `existing_id`).
5. `_insert_membership`: `Membership` en `pending_payment` con `agreed_price_cop` copiado del plan
   y `classes_total = classes_remaining = class_count` (D15); `flush` con la `EXCLUDE` traducida a
   `MembershipOverlap` (23P01, `violated_constraint`); `emit(MembershipSold)`.

`lock_membership` es la única puerta de `with_for_update` sobre `Membership` (D-3, S3-D59;
`test_guarded_calls.py`): `FOR UPDATE` con `populate_existing=True`. `get_payment_target` (B4)
la usa para el gate de pagos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Row, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.db import violated_constraint
from app.core.events import emit
from app.core.locks import lock_member
from app.modules.members import service as members_service
from app.modules.members.schemas import MemberRef
from app.modules.memberships.events import MembershipSold
from app.modules.memberships.exceptions import (
    MemberInactive,
    MembershipConflict,
    MembershipOverlap,
    PlanInactive,
    PlanInvalid,
)
from app.modules.memberships.models import EXCLUDE_NAME, Membership
from app.modules.memberships.queries import _load_freezes_for
from app.modules.memberships.rules import (
    MembershipSnapshot,
    MembershipStatus,
    PlanTerms,
    classify_open,
    compute_end_date,
    effective,
    find_overlap,
    validate_start_date,
)
from app.modules.memberships.schemas import PaymentTarget, SellMembershipOut
from app.modules.plans import service as plans_service
from app.modules.plans.exceptions import PlanNotFound
from app.modules.plans.schemas import PlanSnapshot
from app.modules.settings import service as settings_service
from app.modules.settings.schemas import MembershipsPolicy

MEMBER_ACTIVE = "active"
"""`members.status` de un socio al que se le puede vender (D21)."""


@dataclass(frozen=True, slots=True)
class _SaleContext:
    """Lo que la venta leyó con los candados tomados: socio, plan, política y "hoy"."""

    member: MemberRef
    plan: PlanSnapshot
    policy: MembershipsPolicy
    today: date


async def sell(
    session: AsyncSession,
    *,
    member_id: UUID,
    plan_id: UUID,
    start_date: date | None = None,
    renew: bool = False,
    first_payment: object | None = None,
    enforce_retroactive_limit: bool = True,
) -> SellMembershipOut:
    """Vende el plan al socio; actor de `get_actor()`, hora de `current_clock()` (D3).

    `first_payment` es `payments.schemas.PaymentIn | None` desde B4; en B1 solo se acepta nulo.
    `enforce_retroactive_limit=False` solo lo pasa la importación del CLI (N-24, L-6).
    """
    if renew:
        raise NotImplementedError("S3-B6: renovar una membresía")
    if first_payment is not None:
        raise NotImplementedError("S3-B4: vender con primer pago")
    async with session.begin_nested():
        ctx = await _sale_context(session, member_id, plan_id)
        inicio = start_date or ctx.today
        tope = ctx.policy.max_retroactive_days if enforce_retroactive_limit else None
        validate_start_date(inicio, ctx.today, max_retroactive_days=tope)
        fin = compute_end_date(inicio, _terms(ctx.plan))
        await _check_open_memberships(session, ctx, inicio, fin, renew=renew)
        membresia = await _insert_membership(session, ctx, inicio, fin)
    return _sell_out(membresia, ctx)


def _terms(plan: PlanSnapshot) -> PlanTerms:
    return PlanTerms(kind=plan.kind, duration_days=plan.duration_days, class_count=plan.class_count)


async def _sale_context(session: AsyncSession, member_id: UUID, plan_id: UUID) -> _SaleContext:
    """Candados en el orden de D3 (socio y después `FOR SHARE` del plan) y lecturas de la venta.

    `MemberNotFound` (404) si el socio no existe; `MemberInactive` si está dado de baja o no
    activo; `PlanInvalid` si el plan no existe o está dado de baja; `PlanInactive` si no está
    activo.
    """
    await lock_member(session, member_id)
    socio = await members_service.get_ref(session, member_id)
    if socio.is_deleted or socio.status != MEMBER_ACTIVE:
        raise MemberInactive()
    try:
        plan = await plans_service.get(session, plan_id, for_share=True)
    except PlanNotFound as error:
        raise PlanInvalid() from error
    if not plan.is_active:
        raise PlanInactive()
    politica = await settings_service.memberships_policy(session)
    return _SaleContext(
        member=socio, plan=plan, policy=politica, today=current_clock().today_bogota()
    )


def _snapshot(fila: Row[*tuple[Any, ...]]) -> MembershipSnapshot:
    return MembershipSnapshot(
        id=fila.id,
        status=MembershipStatus(fila.status),
        start_date=fila.start_date,
        end_date=fila.end_date,
        classes_remaining=fila.classes_remaining,
    )


async def _check_open_memberships(
    session: AsyncSession,
    ctx: _SaleContext,
    start_date: date,
    end_date: date,
    *,
    renew: bool,
) -> None:
    """Revisión previa de D8 sobre las no canceladas del socio, con su estado efectivo (D5).

    Sin `renew`: una vigente o una futura dan `MembershipConflict` con su `existing_id`. Siempre:
    un rango que se cruza con otra no cancelada (también vencida) da `MembershipOverlap` con su
    `existing_id`. La `EXCLUDE` de la base es la red ante la carrera (`_insert_membership`).
    """
    consulta = select(
        Membership.id,
        Membership.status,
        Membership.start_date,
        Membership.end_date,
        Membership.classes_remaining,
    ).where(
        Membership.member_id == ctx.member.id,
        Membership.status != MembershipStatus.cancelled.value,
    )
    filas = (await session.execute(consulta)).all()
    congelaciones = await _load_freezes_for(session, [fila.id for fila in filas])
    abiertas = [
        effective(
            _snapshot(fila), ctx.today, ctx.policy.expiring_days, congelaciones.get(fila.id, [])
        )
        for fila in filas
    ]
    if not renew:
        clasificadas = classify_open(abiertas, ctx.today)
        existente = clasificadas.current or clasificadas.future
        if existente is not None:
            raise MembershipConflict(existing_id=existente.id)
    choque = find_overlap(start_date, end_date, abiertas)
    if choque is not None:
        raise MembershipOverlap(existing_id=choque)


async def _insert_membership(
    session: AsyncSession, ctx: _SaleContext, start_date: date, end_date: date
) -> Membership:
    """Inserta la venta en `pending_payment` con el precio y las clases copiados del plan (RN-04,
    D15), hace `flush` (el hook escribe la auditoría con el socio como sujeto) y emite
    `MembershipSold`. Una violación de `ex_memberships_member_dates` (23P01) es la carrera que
    la revisión previa no vio: sale como `MembershipOverlap` sin `existing_id`."""
    membresia = Membership(
        member_id=ctx.member.id,
        plan_id=ctx.plan.id,
        agreed_price_cop=ctx.plan.price_cop,
        start_date=start_date,
        end_date=end_date,
        classes_total=ctx.plan.class_count,
        classes_remaining=ctx.plan.class_count,
        status=MembershipStatus.pending_payment.value,
    )
    session.add(membresia)
    try:
        await session.flush()
    except IntegrityError as error:
        if violated_constraint(error) != EXCLUDE_NAME:
            raise
        raise MembershipOverlap() from error
    evento = MembershipSold(
        membership_id=membresia.id,
        member_id=membresia.member_id,
        plan_id=membresia.plan_id,
        agreed_price_cop=membresia.agreed_price_cop,
        start_date=membresia.start_date,
        end_date=membresia.end_date,
        renewal=False,
    )
    await emit(evento, session)
    return membresia


def _sell_out(membresia: Membership, ctx: _SaleContext) -> SellMembershipOut:
    return SellMembershipOut(
        id=membresia.id,
        member_id=membresia.member_id,
        member_name=f"{ctx.member.first_name} {ctx.member.last_name}",
        plan_id=membresia.plan_id,
        plan_name=ctx.plan.name,
        agreed_price_cop=membresia.agreed_price_cop,
        paid_cop=0,
        start_date=membresia.start_date,
        end_date=membresia.end_date,
        classes_total=membresia.classes_total,
        classes_remaining=membresia.classes_remaining,
        status=membresia.status,
        freezes=[],
        cancel_reason=None,
        cancelled_at=None,
        created_at=membresia.created_at,
        first_payment_id=None,
    )


async def lock_membership(session: AsyncSession, membership_id: UUID) -> Membership | None:
    """`SELECT ... FOR UPDATE` de la membresía con `populate_existing=True`; `None` si no existe."""
    consulta = (
        select(Membership)
        .where(Membership.id == membership_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(consulta)).first()


async def get_payment_target(session: AsyncSession, membership_id: UUID) -> PaymentTarget:
    """Lo que el gate de pagos necesita, con la fila bloqueada por `lock_membership` (D1)."""
    membresia = await lock_membership(session, membership_id)
    if membresia is None:
        return PaymentTarget(exists=False, cancelled=False, member_id=None)
    return PaymentTarget(
        exists=True,
        cancelled=membresia.status == MembershipStatus.cancelled.value,
        member_id=membresia.member_id,
    )
