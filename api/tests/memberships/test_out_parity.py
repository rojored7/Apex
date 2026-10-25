"""Paridad del estado EFECTIVO entre las salidas de membresías (PM4 y PM5 de la revisión de Fase 4
del Sprint 3; D5, S3-D91, S3-D92).

Hoy es 2026-10-21 (`reloj`), `expiring_days` 7 (política por defecto). Una membresía `active`
guardada del 2026-09-25 al 2026-10-25 (faltan 4 días) tiene estado efectivo `expiring`:
- `get`, la fila de `list`, la de `list_for_member` y la salida de `freeze` (con una ventana
  futura, del 22 al 23 de octubre, que corre el fin al 27: siguen faltando 6) dan el mismo
  estado, y es un `MembershipStatus`, no un texto suelto (PM5);
- la de `cancel` da `cancelled`, igual que `get` después;
- el OpenAPI publica `status` de `MembershipOut` y de `MembershipRow` como el enum
  `MembershipStatus` con sus seis valores (antes era `string`).

Todas las salidas salen de un solo constructor (`queries.out_fields` y `queries.row_fields`) y de
un solo `rules.snapshot` (PM4).
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.core.crypto.keyring import Keyring
from app.core.pagination import PageParams
from app.modules.memberships import service
from app.modules.memberships.rules import MembershipStatus
from app.modules.memberships.schemas import MembershipListQuery
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import cancelar, congelar

PAGINA = PageParams(limit=50, offset=0)
ESTADOS = ["active", "cancelled", "expired", "expiring", "frozen", "pending_payment"]


async def _vigente_por_vencer(session: AsyncSession) -> tuple[UUID, UUID]:
    """La membresía `active` guardada que vence el 2026-10-25 y su socio."""
    socio = await make_member(session, first_name="Paridad", document=unique_document())
    plan = await make_plan(session)
    membresia = await make_membership(
        session, socio, plan, status="active", start=date(2026, 9, 25), end=date(2026, 10, 25)
    )
    return membresia.id, socio.id


async def _estados(session: AsyncSession, membership_id: UUID, member_id: UUID) -> list[Any]:
    detalle = await service.get(session, membership_id)
    filas = await service.list(session, MembershipListQuery(member_id=member_id), PAGINA)
    pestana = await service.list_for_member(session, member_id, PAGINA)
    return [
        detalle.status,
        next(f.status for f in filas.items if f.id == membership_id),
        next(m.status for m in pestana.items if m.id == membership_id),
    ]


async def test_get_list_y_la_pestana_dan_el_mismo_estado_efectivo_y_es_el_enum(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia, socio = await _vigente_por_vencer(session)
    estados = await _estados(session, membresia, socio)
    assert estados == [MembershipStatus.expiring] * 3
    assert all(type(estado) is MembershipStatus for estado in estados), estados


async def test_freeze_responde_el_mismo_estado_que_get_despues(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia, socio = await _vigente_por_vencer(session)
    salida = await congelar(
        session,
        SYSTEM_USER_ID,
        membership_id=membresia,
        frozen_from=date(2026, 10, 22),
        frozen_to=date(2026, 10, 23),
    )
    assert salida.end_date == date(2026, 10, 27)
    assert type(salida.status) is MembershipStatus
    assert [salida.status, *await _estados(session, membresia, socio)] == (
        [MembershipStatus.expiring] * 4
    )


async def test_cancel_responde_cancelled_como_get(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia, _ = await _vigente_por_vencer(session)
    salida = await cancelar(
        session, SYSTEM_USER_ID, membership_id=membresia, reason="Error de digitación"
    )
    assert salida.status is MembershipStatus.cancelled
    assert (await service.get(session, membresia)).status is MembershipStatus.cancelled


def _status_de(esquema: dict[str, Any], componente: str) -> dict[str, Any]:
    propiedad: dict[str, Any] = esquema["components"]["schemas"][componente]["properties"]["status"]
    return propiedad


def test_el_openapi_publica_status_como_el_enum_membership_status(api_prueba: FastAPI) -> None:
    esquema = api_prueba.openapi()
    for componente in ("MembershipOut", "MembershipRow", "SellMembershipOut"):
        assert _status_de(esquema, componente) == {"$ref": "#/components/schemas/MembershipStatus"}
    enum = esquema["components"]["schemas"]["MembershipStatus"]
    assert enum["type"] == "string"
    assert sorted(enum["enum"]) == ESTADOS
