"""Fábrica de `memberships.memberships` (plan del Sprint 3, sección 2, bloque B1; US-083, US-084).

- `make_membership(session, member, plan, *, status="pending_payment", start=None, end=None,
  price=None, classes_remaining=None, **cambios)`: inserta por ORM (el hook de auditoría la ve)
  bajo `actor_scope(SYSTEM_USER_ID)`, hace `flush` y confirma el savepoint, como `make_plan`.
  `start` por defecto es "hoy" del reloj actual (la fixture `reloj`: 2026-10-21); `end` por defecto
  sale de `rules.compute_end_date(start, plan)`; `price` por defecto es `plan.price_cop`. En un plan
  por clases `classes_total = class_count` y `classes_remaining` (por defecto `class_count`). Una
  `cancelled` lleva motivo, quién y cuándo (el CHECK `cancelled_has_reason`). No emite eventos ni
  pasa por `sell`: sirve para preparar estados.
- `make_memberships(session, n, plan, *, members=None, **cambios)`: `n` membresías, una por socio
  (la `EXCLUDE` impide dos solapadas del mismo socio); sin `members` crea `n` socios con
  `make_members` (necesita el bus listo). Para las pruebas `perf` de B7.
- `make_freeze(session, membership, frozen_from=None, frozen_to=None, **cambios)` (S3-B2, sección
  2 del plan): inserta una `MembershipFreeze` por ORM bajo `actor_scope(SYSTEM_USER_ID)` con
  `days = (frozen_to - frozen_from) + 1` (RN-07) y confirma el savepoint. Por defecto la ventana es
  de un día en el inicio de la membresía. **No** corre `end_date` ni cambia el estado: prepara
  historiales (congelaciones pasadas, ya programadas) para las reglas de `freeze`.
- `make_memberships_para_recalculo(session, *, n_socios, por_socio, hoy, status="active",
  plan=None)` (S4A-B2, plan del Sprint 4A, sección 2, bloque B2): `n_socios` socios (con
  `make_members`, necesita el bus confirmado) con `por_socio` membresías consecutivas de un plan de
  30 días cada uno, sin solaparse, todas guardadas con `status`. Para el socio `k` la última
  empieza `hoy - (k % 31)` (vigente: `active` o `expiring` según los días que le queden) y las
  anteriores, 31 días antes cada una (vencidas). Con `status="active"` todas las anteriores y las
  que están por vencer son candidatas del recálculo. Devuelve `[(socio, [membresías])]`, en el
  orden de creación.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.members.models import Member
from app.modules.memberships.models import Membership, MembershipFreeze
from app.modules.memberships.rules import PlanTerms, compute_end_date
from app.modules.plans.models import Plan
from tests.factories.members import make_members
from tests.factories.plans import make_plan

MOTIVO_ANULACION: Final = "Anulada en la fábrica de pruebas"


def _terminos(plan: Plan) -> PlanTerms:
    return PlanTerms(kind=plan.kind, duration_days=plan.duration_days, class_count=plan.class_count)


async def make_membership(
    session: AsyncSession,
    member: Member,
    plan: Plan,
    *,
    status: str = "pending_payment",
    start: date | None = None,
    end: date | None = None,
    price: int | None = None,
    classes_remaining: int | None = None,
    **cambios: Any,
) -> Membership:
    """Inserta una `Membership` del socio y el plan dados bajo `SYSTEM_USER_ID` y confirma."""
    inicio = start or current_clock().today_bogota()
    clases = plan.class_count
    valores: dict[str, Any] = {
        "member_id": member.id,
        "plan_id": plan.id,
        "agreed_price_cop": plan.price_cop if price is None else price,
        "start_date": inicio,
        "end_date": end or compute_end_date(inicio, _terminos(plan)),
        "classes_total": clases,
        "classes_remaining": clases if classes_remaining is None else classes_remaining,
        "status": status,
        "created_by": SYSTEM_USER_ID,
    }
    if status == "cancelled":
        valores.update(
            cancel_reason=MOTIVO_ANULACION,
            cancelled_by=SYSTEM_USER_ID,
            cancelled_at=current_clock().now_utc(),
        )
    valores.update(cambios)
    membresia = Membership(**valores)
    with actor_scope(SYSTEM_USER_ID):
        session.add(membresia)
        await session.flush()
        await session.commit()
    return membresia


async def make_memberships(
    session: AsyncSession,
    n: int,
    plan: Plan,
    *,
    members: Sequence[Member] | None = None,
    **cambios: Any,
) -> list[Membership]:
    """`n` membresías del plan, una por socio (crea los socios si no se pasan)."""
    socios = list(members) if members is not None else await make_members(session, n)
    return [await make_membership(session, socio, plan, **cambios) for socio in socios[:n]]


async def make_freeze(
    session: AsyncSession,
    membership: Membership,
    frozen_from: date | None = None,
    frozen_to: date | None = None,
    **cambios: Any,
) -> MembershipFreeze:
    """Inserta una congelación de `membership` (sin mover su fin) bajo `SYSTEM_USER_ID`."""
    desde = frozen_from or membership.start_date
    hasta = frozen_to or desde
    valores: dict[str, Any] = {
        "membership_id": membership.id,
        "frozen_from": desde,
        "frozen_to": hasta,
        "days": (hasta - desde).days + 1,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    congelacion = MembershipFreeze(**valores)
    with actor_scope(SYSTEM_USER_ID):
        session.add(congelacion)
        await session.flush()
        await session.commit()
    return congelacion


BLOQUE_RECALCULO: Final = 31
"""Días de cada membresía del recálculo (plan de 30 días: fin inclusivo a los 30, RN-05)."""


async def make_memberships_para_recalculo(
    session: AsyncSession,
    *,
    n_socios: int,
    por_socio: int,
    hoy: date,
    status: str = "active",
    plan: Plan | None = None,
) -> list[tuple[Member, list[Membership]]]:
    """Socios con `por_socio` membresías consecutivas guardadas con `status` (docstring)."""
    del_plan = plan or await make_plan(session, name=f"Recálculo {hoy.isoformat()}")
    socios = await make_members(session, n_socios)
    salida: list[tuple[Member, list[Membership]]] = []
    for indice, socio in enumerate(socios):
        ultima = hoy - timedelta(days=indice % BLOQUE_RECALCULO)
        inicios = [
            ultima - timedelta(days=BLOQUE_RECALCULO * atras)
            for atras in range(por_socio - 1, -1, -1)
        ]
        filas = [
            await make_membership(session, socio, del_plan, status=status, start=inicio)
            for inicio in inicios
        ]
        salida.append((socio, filas))
    return salida
