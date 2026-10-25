"""Lecturas de membresías (S3-B1: `refs_for`; B7 agrega listas, resumen y estados). Privado (D7).

- `refs_for(session, membership_ids)`: por cada id existente, `MembershipRef` con el nombre del
  socio (`members.service.names_for`, incluye dados de baja), el del plan
  (`plans.service.names_for`, incluye dados de baja) y las fechas. Consulta `memberships` en lotes
  de `core.pagination.ID_BATCH` con `chunked` (S3-D59); sin ids no consulta nada.
- `_freeze_rows_for(session, ids)`: las filas de `memberships.membership_freezes` de cada id, en
  orden de `frozen_from` (S3-B2, D6: sin `relationship()`), en lotes de `ID_BATCH`; todo id pedido
  aparece en el resultado (lista vacía si no tiene congelaciones).
- `_load_freezes_for(session, ids)`: las mismas, como `rules.FreezeWindow` (lo que leen
  `compute_status` y `apply_freeze`); la usan `sell` y `freeze`.
- `freeze_out(fila)` y `membership_out(session, membresia, freezes)`: la salida `MembershipOut`
  con el nombre del socio y del plan (`names_for` de cada módulo dueño) y `paid_cop = 0` hasta B4.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import chunked
from app.modules.members import service as members_service
from app.modules.memberships.models import Membership, MembershipFreeze
from app.modules.memberships.rules import FreezeWindow
from app.modules.memberships.schemas import FreezeOut, MembershipOut, MembershipRef
from app.modules.plans import service as plans_service


async def refs_for(
    session: AsyncSession, membership_ids: Iterable[UUID]
) -> dict[UUID, MembershipRef]:
    """Nombre del socio, del plan y fechas por id de membresía existente (incluye dados de baja).

    Una consulta a `memberships.memberships` por lote de `ID_BATCH` y una a cada módulo dueño de
    los nombres. Socios y planes nunca se borran físicamente (regla de datos 4); si faltara el
    nombre de alguno, esa membresía no aparece en el resultado.
    """
    buscados = list(dict.fromkeys(membership_ids))
    if not buscados:
        return {}
    filas: list[Row[*tuple[Any, ...]]] = []
    for lote in chunked(buscados):
        consulta = select(
            Membership.id,
            Membership.member_id,
            Membership.plan_id,
            Membership.start_date,
            Membership.end_date,
        ).where(Membership.id.in_(lote))
        filas.extend((await session.execute(consulta)).all())
    if not filas:
        return {}
    socios = await members_service.names_for(session, (fila.member_id for fila in filas))
    planes = await plans_service.names_for(session, (fila.plan_id for fila in filas))
    return {
        fila.id: MembershipRef(
            member_id=fila.member_id,
            member_first_name=socios[fila.member_id].first_name,
            member_last_name=socios[fila.member_id].last_name,
            plan_name=planes[fila.plan_id],
            start_date=fila.start_date,
            end_date=fila.end_date,
        )
        for fila in filas
        if fila.member_id in socios and fila.plan_id in planes
    }


async def _freeze_rows_for(
    session: AsyncSession, membership_ids: Iterable[UUID]
) -> dict[UUID, list[MembershipFreeze]]:
    """Congelaciones por id de membresía (D6), en orden de `frozen_from`; una consulta por lote de
    `ID_BATCH`. Todo id pedido tiene su lista (vacía si no tiene congelaciones)."""
    buscados = list(dict.fromkeys(membership_ids))
    salida: dict[UUID, list[MembershipFreeze]] = {membership_id: [] for membership_id in buscados}
    for lote in chunked(buscados):
        consulta = (
            select(MembershipFreeze)
            .where(MembershipFreeze.membership_id.in_(lote))
            .order_by(MembershipFreeze.frozen_from, MembershipFreeze.id)
        )
        for fila in await session.scalars(consulta):
            salida[fila.membership_id].append(fila)
    return salida


async def _load_freezes_for(
    session: AsyncSession, membership_ids: Iterable[UUID]
) -> dict[UUID, list[FreezeWindow]]:
    """Congelaciones por id (D6), en orden de `frozen_from`, como ventanas de las reglas."""
    filas = await _freeze_rows_for(session, membership_ids)
    return {
        membership_id: [FreezeWindow(fila.frozen_from, fila.frozen_to) for fila in lista]
        for membership_id, lista in filas.items()
    }


def freeze_out(fila: MembershipFreeze) -> FreezeOut:
    return FreezeOut(
        id=fila.id,
        frozen_from=fila.frozen_from,
        frozen_to=fila.frozen_to,
        days=fila.days,
        created_at=fila.created_at,
    )


async def membership_out(
    session: AsyncSession, membresia: Membership, freezes: Iterable[MembershipFreeze]
) -> MembershipOut:
    """`MembershipOut` de una membresía con sus congelaciones (en el orden dado). Socios y planes
    nunca se borran físicamente (regla de datos 4): si faltara un nombre, el `KeyError` es la
    señal de un defecto, no un caso de negocio. `paid_cop` es 0 hasta B4."""
    socio = (await members_service.names_for(session, [membresia.member_id]))[membresia.member_id]
    plan_name = (await plans_service.names_for(session, [membresia.plan_id]))[membresia.plan_id]
    return MembershipOut(
        id=membresia.id,
        member_id=membresia.member_id,
        member_name=f"{socio.first_name} {socio.last_name}",
        plan_id=membresia.plan_id,
        plan_name=plan_name,
        agreed_price_cop=membresia.agreed_price_cop,
        paid_cop=0,
        start_date=membresia.start_date,
        end_date=membresia.end_date,
        classes_total=membresia.classes_total,
        classes_remaining=membresia.classes_remaining,
        status=membresia.status,
        freezes=[freeze_out(fila) for fila in freezes],
        cancel_reason=membresia.cancel_reason,
        cancelled_at=membresia.cancelled_at,
        created_at=membresia.created_at,
    )
