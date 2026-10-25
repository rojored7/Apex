"""Vender una membresía (S3-B1, US-084; D3, D8, D15, D16, N-24, M-4). Privado (D7).

`sell` orquesta (menos de 50 líneas, E11) y todo su cuerpo corre dentro de
`session.begin_nested()` (D3): si un paso o un handler de `MembershipSold` falla, no queda ni
membresía ni auditoría, también dentro de la sesión con savepoint de las pruebas.

Pasos, en el orden único de candados de D3:
1. `renew=True` (S3-B6, US-088; Q1, D8): el `start_date` recibido se descarta. Bajo el candado
   del socio y con las mismas validaciones del paso 2, una futura (D8) da
   `FutureMembershipExists` (409 `future_membership_exists`, `existing_id`); si no,
   `rules.plan_renewal(vigente_o_None, plan, price_cop, hoy)` fija inicio, fin y precio. No aplica
   `validate_start_date` (ni `start_date_too_far` ni el límite retroactivo); `find_overlap` y la
   `EXCLUDE` siguen siendo la red; el primer pago es el mismo del paso 6 y el evento es
   `MembershipSold(renewal=True)` (`_renewal_for`; la vista previa usa la misma función).
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
   sin rol (`None` no es `admin`: tope retroactivo de `paid_at`, falla cerrado; S3-D81, y desde
   PM5 de la revisión de Fase 4 del Sprint 3 sin el centinela `LIMITED_ROLE = ""`).

`renewal_preview(session, *, member_id, plan_id) -> RenewalPreviewOut` (S3-B6, US-088): lo que
crearía `sell(..., renew=True)` (inicio, fin, precio y `current_end_date`, el fin de la vigente o
nulo) con las mismas validaciones y errores (`MemberNotFound`, `MemberInactive`, `PlanInvalid`,
`PlanInactive`, `FutureMembershipExists`), sin escribir y sin candados: ni el del socio, ni
`FOR SHARE` del plan, ni `FOR UPDATE` (es una lectura; la ruta no consume cupo).

`lock_membership` es la única puerta de `with_for_update` sobre `Membership` (D-3, S3-D59;
`test_guarded_calls.py`): `FOR UPDATE` con `populate_existing=True`. `membership_payability`
(S3-B4, D1) la adapta al puerto `MembershipGate` de `payments` (`MembershipPayability` con
`agreed_price_cop`, S3-D41); `memberships/service.py` la registra. (`get_payment_target`, el
contrato de B1 que B4 reemplazó, se quitó en la revisión de Fase 4 del Sprint 3, PL2.)

`open_memberships(session, member_id, today, expiring_days)`: las no canceladas del socio con su
estado efectivo (D5); la usan la venta, la renovación y, desde PM4, la revisión de fechas de
`lifecycle.freeze`.

`reraise_with_prefix(error, prefix)` (E5, S3-D75): vuelve a lanzar una copia de `error` (misma
clase, `code`, `message`, `existing_id`, `status` y `headers`) con `field =
rules.prefix_field(prefix, error.field)`; sirve para toda subclase de `DomainError`, también las
de `__init__` propio (PM3, S3-D94).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import NoReturn
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.db import violated_constraint
from app.core.errors import DomainError
from app.core.events import emit
from app.core.locks import lock_member
from app.core.security import Role
from app.modules.members import service as members_service
from app.modules.members.schemas import MemberRef
from app.modules.memberships.events import MembershipSold
from app.modules.memberships.exceptions import (
    FutureMembershipExists,
    MemberInactive,
    MembershipConflict,
    MembershipOverlap,
    PlanInactive,
    PlanInvalid,
)
from app.modules.memberships.models import EXCLUDE_NAME, Membership
from app.modules.memberships.queries import _load_freezes_for, out_fields
from app.modules.memberships.rules import (
    MembershipSnapshot,
    MembershipStatus,
    PlanTerms,
    RenewalPlan,
    classify_open,
    compute_end_date,
    effective,
    find_overlap,
    plan_renewal,
    prefix_field,
    snapshot,
    validate_start_date,
)
from app.modules.memberships.schemas import RenewalPreviewOut, SellMembershipOut
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
    role: Role | None = None,
) -> SellMembershipOut:
    """Vende el plan al socio; actor de `get_actor()`, hora de `current_clock()` (D3).

    `first_payment` (D4) se registra en la misma unidad con el `role` del llamador (el router pasa
    `principal.role`; decide la retroactividad de `paid_at`, M-8).
    `enforce_retroactive_limit=False` solo lo pasa la importación del CLI (N-24, L-6).
    """
    pago_id: UUID | None = None
    pagado = 0
    async with session.begin_nested():
        ctx = await _sale_context(session, member_id, plan_id)
        if renew:
            renovacion, _ = await _renewal_for(session, ctx)
            inicio, fin = renovacion.start_date, renovacion.end_date
        else:
            inicio = start_date or ctx.today
            tope = ctx.policy.max_retroactive_days if enforce_retroactive_limit else None
            validate_start_date(inicio, ctx.today, max_retroactive_days=tope)
            fin = compute_end_date(inicio, _terms(ctx.plan))
        await _check_open_memberships(session, ctx, inicio, fin, renew=renew)
        membresia = await _insert_membership(session, ctx, inicio, fin, renewal=renew)
        if first_payment is not None:
            pago_id = await _register_first_payment(session, membresia, first_payment, role=role)
            pagado = await payments_service.sum_not_voided(session, membresia.id)
    return _sell_out(membresia, ctx, paid_cop=pagado, first_payment_id=pago_id)


async def renewal_preview(
    session: AsyncSession, *, member_id: UUID, plan_id: UUID
) -> RenewalPreviewOut:
    """Vista previa de la renovación, sin escribir y sin candados (docstring del módulo)."""
    ctx = await _sale_context(session, member_id, plan_id, lock=False)
    renovacion, vigente = await _renewal_for(session, ctx)
    return RenewalPreviewOut(
        start_date=renovacion.start_date,
        end_date=renovacion.end_date,
        agreed_price_cop=renovacion.agreed_price_cop,
        current_end_date=None if vigente is None else vigente.end_date,
    )


def _terms(plan: PlanSnapshot) -> PlanTerms:
    return PlanTerms(kind=plan.kind, duration_days=plan.duration_days, class_count=plan.class_count)


async def _sale_context(
    session: AsyncSession, member_id: UUID, plan_id: UUID, *, lock: bool = True
) -> _SaleContext:
    """Candados en el orden de D3 (socio y después `FOR SHARE` del plan) y lecturas de la venta.

    `MemberNotFound` (404) si el socio no existe; `MemberInactive` si está dado de baja o no
    activo; `PlanInvalid` si el plan no existe o está dado de baja; `PlanInactive` si no está
    activo. Con `lock=False` (la vista previa de la renovación) hace las mismas lecturas sin
    ningún candado.
    """
    if lock:
        await lock_member(session, member_id)
    socio = await members_service.get_ref(session, member_id)
    if socio.is_deleted or socio.status != MEMBER_ACTIVE:
        raise MemberInactive()
    try:
        plan = await plans_service.get(session, plan_id, for_share=lock)
    except PlanNotFound as error:
        raise PlanInvalid() from error
    if not plan.is_active:
        raise PlanInactive()
    politica = await settings_service.memberships_policy(session)
    return _SaleContext(
        member=socio, plan=plan, policy=politica, today=current_clock().today_bogota()
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
    abiertas = await _open_of(session, ctx)
    if not renew:
        clasificadas = classify_open(abiertas, ctx.today)
        existente = clasificadas.current or clasificadas.future
        if existente is not None:
            raise MembershipConflict(existing_id=existente.id)
    choque = find_overlap(start_date, end_date, abiertas)
    if choque is not None:
        raise MembershipOverlap(existing_id=choque)


async def open_memberships(
    session: AsyncSession, member_id: UUID, today: date, expiring_days: int
) -> list[MembershipSnapshot]:
    """Las no canceladas del socio con su estado efectivo (D5) a `today`."""
    consulta = select(
        Membership.id,
        Membership.status,
        Membership.start_date,
        Membership.end_date,
        Membership.classes_remaining,
    ).where(
        Membership.member_id == member_id,
        Membership.status != MembershipStatus.cancelled.value,
    )
    filas = (await session.execute(consulta)).all()
    congelaciones = await _load_freezes_for(session, [fila.id for fila in filas])
    return [
        effective(snapshot(fila), today, expiring_days, congelaciones.get(fila.id, []))
        for fila in filas
    ]


async def _open_of(session: AsyncSession, ctx: _SaleContext) -> list[MembershipSnapshot]:
    """`open_memberships` del socio de la venta, a la fecha y con la política de `ctx`."""
    return await open_memberships(session, ctx.member.id, ctx.today, ctx.policy.expiring_days)


async def _renewal_for(
    session: AsyncSession, ctx: _SaleContext
) -> tuple[RenewalPlan, MembershipSnapshot | None]:
    """Fechas y precio de la renovación (Q1, D8) y la vigente, si hay.

    Una futura (D8, sobre el estado efectivo) da `FutureMembershipExists` con su `existing_id`;
    si no, `plan_renewal` desde el fin de la vigente (ya extendido por sus congelaciones) o desde
    hoy. Un rango que se cruza con otra no cancelada da `MembershipOverlap` (la misma revisión de
    la venta: así la vista previa responde lo mismo que la renovación).
    """
    abiertas = await _open_of(session, ctx)
    clasificadas = classify_open(abiertas, ctx.today)
    if clasificadas.future is not None:
        raise FutureMembershipExists(existing_id=clasificadas.future.id)
    renovacion = plan_renewal(clasificadas.current, _terms(ctx.plan), ctx.plan.price_cop, ctx.today)
    choque = find_overlap(renovacion.start_date, renovacion.end_date, abiertas)
    if choque is not None:
        raise MembershipOverlap(existing_id=choque)
    return renovacion, clasificadas.current


async def _insert_membership(
    session: AsyncSession, ctx: _SaleContext, start_date: date, end_date: date, *, renewal: bool
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
        renewal=renewal,
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
    de identidad: `lock_membership` la relee con `populate_existing`). El estado guardado es el
    efectivo de hoy (la venta lo fija en `pending_payment` y la activación con `compute_status`
    del mismo día), sin congelaciones ni anulación; los campos salen de `queries.out_fields`
    (PM4)."""
    campos = out_fields(
        membresia,
        member_name=f"{ctx.member.first_name} {ctx.member.last_name}",
        plan_name=ctx.plan.name,
        paid_cop=paid_cop,
        status=MembershipStatus(membresia.status),
        freezes=[],
    )
    return SellMembershipOut(**campos, first_payment_id=first_payment_id)


async def lock_membership(session: AsyncSession, membership_id: UUID) -> Membership | None:
    """`SELECT ... FOR UPDATE` de la membresía con `populate_existing=True`; `None` si no existe."""
    consulta = (
        select(Membership)
        .where(Membership.id == membership_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(consulta)).first()


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


async def _register_first_payment(
    session: AsyncSession,
    membership: Membership,
    first_payment: PaymentIn,
    *,
    role: Role | None,
) -> UUID:
    """Registra el primer pago de la venta (paso 6) y devuelve su id; errores con prefijo (E5).

    `confirm_duplicate=False` siempre (la membresía es nueva: no hay pagos previos con que
    chocar); `confirm_overpayment` viene del cuerpo y el saldo es el precio pactado (H-1). Con
    `role=None` (un llamador interno sin rol) el pago tiene el tope retroactivo (S3-D81): el
    router siempre pasa `principal.role`."""
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
            role=role,
        )
    except DomainError as error:
        reraise_with_prefix(error, "first_payment")
    return pago.id


def reraise_with_prefix(error: DomainError, prefix: str) -> NoReturn:
    """Copia de `error` con `field = prefix_field(prefix, error.field)` (E5, S3-D75): misma
    clase, `code`, `message`, `existing_id`, `status` y una copia de `headers`. El original no
    cambia y queda como causa (`from error`).

    PM3 de la revisión de Fase 4 del Sprint 3: la copia no llama al `__init__` de la clase (que
    en `DatabaseBusy` o `TooManyRequestsError` tiene otra firma y daba `TypeError`, un 500): se
    crea con `__new__` y copia los atributos de la instancia (`copy.copy` tampoco sirve: las
    excepciones se copian llamando a la clase con `args`)."""
    copia = type(error).__new__(type(error), *error.args)
    copia.__dict__.update(vars(error))
    copia.headers = dict(error.headers)
    copia.field = prefix_field(prefix, error.field)
    raise copia from error
