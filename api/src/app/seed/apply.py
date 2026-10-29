"""Aplicación del conjunto de demostración (`seed --demo`, S4B-D32, D33).

Por socio, DOS transacciones: la primera da de alta (`_ensure_member`); la segunda toma
`lock_member` primero (S3-D95), vende con fecha pasada, registra los pagos y aplica anulación,
congelación, anulada y renovación (`_sell_and_pay`). No es atómico: se reanuda por socio, porque
la segunda transacción es todo o nada. `_sell_back_dated` es la única llamada que nombra
`enforce_retroactive_limit` (S4B-D33). Solo llama a `service.py` y `schemas.py` de los módulos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from app.cli_base import unit_of_work
from app.cli_session import read_only_session
from app.core import db
from app.core.clock import BOGOTA, current_clock
from app.core.config import Settings
from app.core.locks import lock_member
from app.core.pagination import PageParams
from app.modules.members import service as members_service
from app.modules.members.schemas import MemberCreate
from app.modules.memberships import service as memberships_service
from app.modules.payments import service as payments_service
from app.modules.payments.schemas import PaymentIn
from app.modules.plans import service as plans_service
from app.modules.plans.schemas import PlanCreate
from app.modules.settings import service as settings_service
from app.seed.dataset import DemoMember, DemoPayment, DemoPlan, DemoSpec, demo_dataset

VOID_REASON = "Pago registrado por error (datos de demostración)"
CANCEL_REASON = "Membresía anulada (datos de demostración)"
PAID_AT_HOUR = 9  # hora de Bogotá a la que se fecha cada pago de la demostración


class NonDemoDataError(Exception):
    """La base ya tiene socios que no son de la demostración y no se pidió forzar."""


@dataclass(frozen=True, slots=True)
class DemoResult:
    """Conteos de lo que ESTA corrida creó (nunca ids, nombres ni documentos)."""

    plans: int
    members: int
    memberships: int
    payments: int
    already_applied: bool


def _paid_at(pago: DemoPayment) -> datetime:
    """El pago a las 09:00 de Bogotá de su día, sin pasar de ahora (hoy a primera hora)."""
    candidato = datetime.combine(pago.paid_on, time(PAID_AT_HOUR), tzinfo=BOGOTA)
    return min(candidato, current_clock().now_utc())


def _payment_in(pago: DemoPayment) -> PaymentIn:
    return PaymentIn(amount_cop=pago.amount_cop, method=pago.method, paid_at=_paid_at(pago))


def _payments_of(member: DemoMember) -> list[DemoPayment]:
    venta = member.sale
    primero = [venta.first_payment] if venta.first_payment is not None else []
    return [*primero, *venta.extra_payments]


async def apply_demo(
    settings: Settings, actor_id: UUID, today: date, *, force_on_non_empty: bool
) -> DemoResult:
    """Siembra el catálogo; repetirla completa lo que falte y no cambia nada si ya está."""
    del settings  # la base ya está configurada por el runtime del comando
    session_factory = db.get_sessionmaker()
    with unit_of_work(actor_id):
        spec = await _plan_the_run(session_factory, today, force_on_non_empty)
        antes = await _existing_plans(session_factory, spec)
        plan_ids = await _ensure_plans(session_factory, spec.plans)
        socios = membresias = pagos = 0
        for member in spec.members:
            member_id, nuevo = await _member_id(session_factory, member)
            socios += int(nuevo)
            creadas = await _sell_and_pay(session_factory, member_id, member, plan_ids)
            membresias += creadas
            pagos += len(_payments_of(member)) if creadas else 0
        await _finish(session_factory, today)
    planes = len(spec.plans) - antes
    hecho = (planes, socios, membresias, pagos)
    return DemoResult(*hecho, already_applied=not any(hecho))


async def _member_id(session_factory: Any, member: DemoMember) -> tuple[UUID, bool]:
    """`(id, creado)`: el id si el socio ya existe; si no, lo da de alta en su transacción."""
    async with read_only_session(session_factory) as session:
        existente = await members_service.id_by_document(session, member.document)
    if existente is not None:
        return existente, False
    return await _ensure_member(session_factory, member), True


async def _plan_the_run(session_factory: Any, today: date, force: bool) -> DemoSpec:
    """El catálogo de hoy; `NonDemoDataError` si hay socios ajenos y no se forzó."""
    async with read_only_session(session_factory) as session:
        politica = await settings_service.memberships_policy(session)
        spec = demo_dataset(today, politica.expiring_days)
        presentes = 0
        for member in spec.members:
            if await members_service.id_by_document(session, member.document) is not None:
                presentes += 1
        total = await members_service.count(session, include_deleted=True)
    if total > presentes and not force:
        raise NonDemoDataError
    return spec


async def _existing_plans(session_factory: Any, spec: DemoSpec) -> int:
    async with read_only_session(session_factory) as session:
        hallados = [await _plan_id(session, plan.name) for plan in spec.plans]
    return sum(1 for hallado in hallados if hallado is not None)


async def _plan_id(session: Any, name: str) -> UUID | None:
    pagina = await plans_service.list(
        session, q=name, active=None, page=PageParams(limit=50, offset=0), role="admin"
    )
    return next((plan.id for plan in pagina.items if plan.name == name), None)


async def _sell_back_dated(session: Any, **venta: Any) -> Any:
    """Única llamada con `enforce_retroactive_limit=False` y `role="admin"` (S4B-D33)."""
    return await memberships_service.sell(
        session, enforce_retroactive_limit=False, role="admin", **venta
    )


async def _ensure_plans(session_factory: Any, plans: tuple[DemoPlan, ...]) -> dict[str, UUID]:
    """Crea los planes que falten (por nombre) y devuelve `{nombre: id}`."""
    salida: dict[str, UUID] = {}
    for plan in plans:
        async with session_factory() as session, session.begin():
            existente = await _plan_id(session, plan.name)
            if existente is None:
                creado = await plans_service.create(
                    session,
                    PlanCreate(
                        name=plan.name,
                        price_cop=plan.price_cop,
                        kind=plan.kind,
                        duration_days=plan.duration_days,
                        class_count=plan.class_count,
                    ),
                )
                existente = creado.id
        salida[plan.name] = existente
    return salida


async def _ensure_member(session_factory: Any, member: DemoMember) -> UUID:
    """Transacción 1 del socio: alta (o el id si ya existe) y commit."""
    async with session_factory() as session, session.begin():
        existente = await members_service.id_by_document(session, member.document)
        if existente is not None:
            return existente
        creado = await members_service.create(
            session,
            MemberCreate(
                first_name=member.first_name,
                last_name=member.last_name,
                document=member.document,
                phone=member.phone,
                email=member.email,
                birth_date=member.birth_date,
                sex=member.sex,
                data_consent=member.data_consent,
            ),
        )
        return creado.id


async def _sell_and_pay(
    session_factory: Any, member_id: UUID, member: DemoMember, plan_ids: dict[str, UUID]
) -> int:
    """Transacción 2 del socio: `lock_member`, venta, pagos, anulación, congelación, anulada y
    renovación; devuelve cuántas membresías creó (0 si ya estaba completo)."""
    venta = member.sale
    async with session_factory() as session, session.begin():
        await lock_member(session, member_id)
        pagina = await memberships_service.list_for_member(
            session, member_id, PageParams(limit=1, offset=0)
        )
        if pagina.total:
            return 0
        primero = venta.first_payment
        vendida = await _sell_back_dated(
            session,
            member_id=member_id,
            plan_id=plan_ids[venta.plan_name],
            start_date=venta.start_date,
            first_payment=_payment_in(primero) if primero is not None else None,
        )
        if primero is not None and primero.void and vendida.first_payment_id is not None:
            await payments_service.void(
                session, payment_id=vendida.first_payment_id, reason=VOID_REASON
            )
        await _after_sale(session, vendida.id, member_id, member, plan_ids)
    return 2 if venta.renewal else 1


async def _after_sale(
    session: Any,
    membership_id: UUID,
    member_id: UUID,
    member: DemoMember,
    plan_ids: dict[str, UUID],
) -> None:
    """Pagos extra (con su anulación), congelación, anulación y renovación de la venta."""
    venta = member.sale
    for pago in venta.extra_payments:
        registrado = await payments_service.register(
            session,
            membership_id=membership_id,
            amount_cop=pago.amount_cop,
            method=pago.method,
            paid_at=_paid_at(pago),
            role="admin",
        )
        if pago.void:
            await payments_service.void(session, payment_id=registrado.id, reason=VOID_REASON)
    if venta.freeze is not None:
        await memberships_service.freeze(
            session,
            membership_id=membership_id,
            frozen_from=venta.freeze.frozen_from,
            frozen_to=venta.freeze.frozen_to,
        )
    if venta.cancel:
        await memberships_service.cancel(session, membership_id=membership_id, reason=CANCEL_REASON)
    if venta.renewal:
        await _sell_back_dated(
            session, member_id=member_id, plan_id=plan_ids[venta.plan_name], renew=True
        )


async def _finish(session_factory: Any, today: date) -> None:
    """`recompute_statuses(db.get_sessionmaker(), today=...)` tras el último commit."""
    resumen = await memberships_service.recompute_statuses(session_factory, today=today)
    if resumen.errores or resumen.busy_omitidos:
        raise RuntimeError("recompute_statuses no terminó limpio")
