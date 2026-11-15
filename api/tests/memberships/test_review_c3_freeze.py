"""Punto MEDIUM de la revisión de S7-C3 (S7-C3b): congelar corre también `original_end_date`.

Camino real: agotar (recorte a hoy) -> renovar -> quitar asistencia con solape (la clase vuelve y el
recorte queda) -> anular la renovación -> congelar. La membresía queda con `end_date` = hoy y
`original_end_date` unos días después; si los días congelados alcanzan ese original, el CHECK
`ck_memberships_original_end_date_after_end` (0030) saltaba como 500. Hoy es 2026-10-21 (`reloj`).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.memberships.rules import (
    FreezeLimits,
    MembershipSnapshot,
    MembershipStatus,
    apply_freeze,
)
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import congelar

ACTOR = UUID("00000000-0000-0000-0000-000000000001")
HOY = date(2026, 10, 21)
ORIGINAL = date(2026, 10, 25)
LIMITES = FreezeLimits(max_days=30, max_count=3, max_retroactive_days=7)

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


def _snapshot() -> MembershipSnapshot:
    return MembershipSnapshot(
        id=UUID(int=1),
        status=MembershipStatus.active,
        start_date=date(2026, 10, 1),
        end_date=HOY,
        classes_remaining=3,
    )


def test_la_regla_corre_el_original_los_mismos_dias() -> None:
    salida = apply_freeze(
        _snapshot(), [], HOY, date(2026, 10, 30), LIMITES, HOY, 7, original_end_date=ORIGINAL
    )
    assert salida.new_end_date == date(2026, 10, 31)
    assert salida.new_original_end_date == date(2026, 11, 4)


def test_sin_original_el_resultado_no_lo_inventa() -> None:
    salida = apply_freeze(_snapshot(), [], HOY, date(2026, 10, 30), LIMITES, HOY, 7)
    assert salida.new_original_end_date is None


async def _recortada(session: AsyncSession):  # type: ignore[no-untyped-def]
    socio = await make_member(session)
    plan = await make_plan(session, name="Tiquetera 12", kind="classes", class_count=12)
    return await make_membership(
        session,
        socio,
        plan,
        status="active",
        start=date(2026, 10, 1),
        end=HOY,
        classes_remaining=3,
        original_end_date=ORIGINAL,
    )


async def test_congelar_con_dias_que_alcanzan_el_original_no_da_500(
    session: AsyncSession,
) -> None:
    membresia = await _recortada(session)
    membership_id = membresia.id
    salida = await congelar(
        session, ACTOR, membership_id=membership_id, frozen_from=HOY, frozen_to=date(2026, 10, 30)
    )
    assert salida.end_date == date(2026, 10, 31)
    fila = (
        await session.execute(
            text("SELECT end_date, original_end_date FROM memberships.memberships WHERE id = :i"),
            {"i": membership_id},
        )
    ).one()
    assert (fila.end_date, fila.original_end_date) == (date(2026, 10, 31), date(2026, 11, 4))


async def test_una_membresia_sin_original_sigue_igual(session: AsyncSession) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(
        session, socio, plan, status="active", start=date(2026, 10, 1), end=date(2026, 10, 31)
    )
    membership_id = membresia.id
    await congelar(
        session, ACTOR, membership_id=membership_id, frozen_from=HOY, frozen_to=date(2026, 10, 30)
    )
    original = await session.scalar(
        text("SELECT original_end_date FROM memberships.memberships WHERE id = :i"),
        {"i": membership_id},
    )
    assert original is None
