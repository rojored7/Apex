"""Vender una membresía (S3-B1, US-084; D3, D8, D15, D16, N-24, M-4). Privado (D7).

`sell` orquesta (menos de 50 líneas, E11) y todo su cuerpo corre dentro de
`session.begin_nested()` (D3): si un paso o un handler de `MembershipSold` falla, no queda ni
membresía ni auditoría, también dentro de la sesión con savepoint de las pruebas.

Pasos, en el orden único de candados de D3:
1. `renew=True`: `NotImplementedError` hasta B6.
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
6. (S3-B4, D4, S3-D41) `_register_first_payment`: si hay `first_payment`, dentro del mismo
   `begin_nested()` y después del paso 5, `payments.service.register(...)` con el monto, medio,
   referencia, `paid_at` y `confirm_overpayment` del cuerpo, `confirm_duplicate=False` (la
   membresía es nueva) y el `role` del llamador (M-8); el gate real (`membership_payability`)
   toma `FOR UPDATE` de la fila recién insertada y el handler `on_payment_registered` la activa
   si el pago la cubre. Un `DomainError` del pago sale con `reraise_with_prefix(error,
   "first_payment")` (E5). La respuesta se arma con la fila que dejó el handler, `paid_cop`
   (`payments.service.sum_not_voided`) y `first_payment_id`. Con `role=None` el pago se registra
   con `LIMITED_ROLE` (no `admin`: tope retroactivo de `paid_at`, falla cerrado).

`lock_membership` es la única puerta de `with_for_update` sobre `Membership` (D-3, S3-D59;
`test_guarded_calls.py`): `FOR UPDATE` con `populate_existing=True`. `get_payment_target` la usa
y `membership_payability` (S3-B4, D1) la adapta al puerto `MembershipGate` de `payments`
(`MembershipPayability` con `agreed_price_cop`, S3-D41); `memberships/service.py` la registra.

`reraise_with_prefix(error, prefix)` (E5, S3-D75): vuelve a lanzar una copia de `error` (misma
clase, `code`, `message`, `existing_id`, `status` y `headers`) con `field =
rules.prefix_field(prefix, error.field)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Final, NoReturn
from uuid import UUID

from sqlalchemy import Row, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.db import violated_constraint
from app.core.errors import DomainError
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
    prefix_field,
    validate_start_date,
)
from app.modules.memberships.schemas import PaymentTarget, SellMembershipOut
from app.modules.payments import service as payments_service
from app.modules.payments.schemas import PaymentIn
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
    first_payment: PaymentIn | None = None,
    enforce_retroactive_limit: bool = True,
    role: str | None = None,
) -> SellMembershipOut:
    """Vende el plan al socio; actor de `get_actor()`, hora de `current_clock()` (D3).

    `first_payment` (D4) se registra en la misma unidad con el `role` del llamador (el router pasa
    `principal.role`; decide la retroactividad de `paid_at`, M-8).
    `enforce_retroactive_limit=False` solo lo pasa la importación del CLI (N-24, L-6).
    """
    if renew:
        raise NotImplementedError("S3-B6: renovar una membresía")
    pago_id: UUID | None = None
    pagado = 0
    async with session.begin_nested():
        ctx = await _sale_context(session, member_id, plan_id)
        inicio = start_date or ctx.today
        tope = ctx.policy.max_retroactive_days if enforce_retroactive_limit else None
        validate_start_date(inicio, ctx.today, max_retroactive_days=tope)
        fin = compute_end_date(inicio, _terms(ctx.plan))
        await _check_open_memberships(session, ctx, inicio, fin, renew=renew)
        membresia = await _insert_membership(session, ctx, inicio, fin)
        if first_payment is not None:
            pago_id = await _register_first_payment(session, membresia, first_payment, role=role)
            pagado = await payments_service.sum_not_voided(session, membresia.id)
    return _sell_out(membresia, ctx, paid_cop=pagado, first_payment_id=pago_id)


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


def _sell_out(
    membresia: Membership,
    ctx: _SaleContext,
    *,
    paid_cop: int,
    first_payment_id: UUID | None,
) -> SellMembershipOut:
    """La salida con la fila tal como la dejó el handler de activación (misma instancia del mapa
    de identidad: `lock_membership` la relee con `populate_existing`)."""
    return SellMembershipOut(
        id=membresia.id,
        member_id=membresia.member_id,
        member_name=f"{ctx.member.first_name} {ctx.member.last_name}",
        plan_id=membresia.plan_id,
        plan_name=ctx.plan.name,
        agreed_price_cop=membresia.agreed_price_cop,
        paid_cop=paid_cop,
        start_date=membresia.start_date,
        end_date=membresia.end_date,
        classes_total=membresia.classes_total,
        classes_remaining=membresia.classes_remaining,
        status=membresia.status,
        freezes=[],
        cancel_reason=None,
        cancelled_at=None,
        created_at=membresia.created_at,
        first_payment_id=first_payment_id,
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
    estado = await membership_payability(session, membership_id)
    return PaymentTarget(
        exists=estado.exists, cancelled=estado.cancelled, member_id=estado.member_id
    )


async def membership_payability(
    session: AsyncSession, membership_id: UUID
) -> payments_service.MembershipPayability:
    """Gate de pagos (D1, S3-D41): existe, está anulada, de qué socio es y el precio pactado de la
    fila (no el del plan), leídos con la fila bloqueada por `lock_membership`."""
    membresia = await lock_membership(session, membership_id)
    if membresia is None:
        return payments_service.MembershipPayability(
            exists=False, cancelled=False, member_id=None, agreed_price_cop=None
        )
    return payments_service.MembershipPayability(
        exists=True,
        cancelled=membresia.status == MembershipStatus.cancelled.value,
        member_id=membresia.member_id,
        agreed_price_cop=membresia.agreed_price_cop,
    )


LIMITED_ROLE: Final = ""
"""Rol con que se registra el primer pago si el llamador no da uno (`role=None`): no es `admin`,
así que `paid_at` queda con el tope retroactivo (M-8). Falla cerrado; el router siempre pasa
`principal.role`."""


async def _register_first_payment(
    session: AsyncSession,
    membership: Membership,
    first_payment: PaymentIn,
    *,
    role: str | None,
) -> UUID:
    """Registra el primer pago de la venta (paso 6) y devuelve su id; errores con prefijo (E5).

    `confirm_duplicate=False` siempre (la membresía es nueva: no hay pagos previos con que
    chocar); `confirm_overpayment` viene del cuerpo y el saldo es el precio pactado (H-1)."""
    try:
        pago = await payments_service.register(
            session,
            membership_id=membership.id,
            amount_cop=first_payment.amount_cop,
            method=first_payment.method,
            reference=first_payment.reference,
            paid_at=first_payment.paid_at,
            confirm_overpayment=first_payment.confirm_overpayment,
            confirm_duplicate=False,
            role=LIMITED_ROLE if role is None else role,
        )
    except DomainError as error:
        reraise_with_prefix(error, "first_payment")
    return pago.id


def reraise_with_prefix(error: DomainError, prefix: str) -> NoReturn:
    """Copia de `error` con `field = prefix_field(prefix, error.field)` (E5, S3-D75): misma
    clase, `code`, `message`, `existing_id`, `status` y una copia de `headers`. El original no
    cambia y queda como causa (`from error`)."""
    copia = type(error)(
        error.code,
        error.message,
        field=prefix_field(prefix, error.field),
        existing_id=error.existing_id,
        status=error.status,
    )
    copia.headers = dict(error.headers)
    raise copia from error
