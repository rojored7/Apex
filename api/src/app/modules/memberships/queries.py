"""Lecturas de membresías (S3-B1: `refs_for`; B7 agrega listas, resumen y estados). Privado (D7).

- `refs_for(session, membership_ids)`: por cada id existente, `MembershipRef` con el nombre del
  socio (`members.service.names_for`, incluye dados de baja), el del plan
  (`plans.service.names_for`, incluye dados de baja) y las fechas. Consulta `memberships` en lotes
  de `core.pagination.ID_BATCH` con `chunked` (S3-D59); sin ids no consulta nada.
- `_load_freezes_for(session, ids)`: congelaciones por lote (D6); hasta B2 devuelve listas
  vacías para cada id.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import chunked
from app.modules.members import service as members_service
from app.modules.memberships.models import Membership
from app.modules.memberships.rules import FreezeWindow
from app.modules.memberships.schemas import MembershipRef
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


async def _load_freezes_for(
    session: AsyncSession, membership_ids: Iterable[UUID]
) -> dict[UUID, list[FreezeWindow]]:
    """Congelaciones por id (D6). Hasta B2 no existe la tabla: lista vacía para cada id, sin
    consultar la base."""
    return {membership_id: [] for membership_id in membership_ids}
