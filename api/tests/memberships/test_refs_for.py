"""`memberships.service.refs_for` (S3-B1; contrato para `payments`, B8 y D26; S3-D59).

- por cada id de membresía existente, `MembershipRef` con el nombre del socio, el del plan y las
  fechas; los ids que no existen no aparecen;
- incluye socios y planes dados de baja (una lista de pagos viejos sigue mostrando sus nombres);
- sin ids no consulta la base;
- consulta `memberships.memberships` por lotes de `ID_BATCH = 200` (`chunked`): 450 ids son tres
  sentencias sobre la tabla.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.core.pagination import ID_BATCH
from app.modules.memberships import service
from app.modules.memberships.schemas import MembershipRef
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan


@pytest.fixture
def sentencias(engine: AsyncEngine) -> Iterator[list[str]]:
    """SQL que la sesión de la prueba manda a la base (la `session` usa una conexión de
    `engine`)."""
    vistas: list[str] = []

    def capturar(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        vistas.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capturar)
    try:
        yield vistas
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capturar)


def _de_membresias(sql: list[str]) -> list[str]:
    return [s for s in sql if "memberships.memberships" in s]


async def test_refs_for_da_nombres_y_fechas_por_id_de_membresia(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    lucia = await make_member(session)
    pedro = await make_member(
        session,
        first_name="Pedro",
        last_name="Ruiz",
        document=unique_document(),
        phone=None,
        email=None,
    )
    mensual = await make_plan(session)
    tiquetera = await make_plan(
        session, name="Tiquetera 12", kind="classes", class_count=12, duration_days=60
    )
    primera = await make_membership(session, lucia, mensual)
    segunda = await make_membership(session, pedro, tiquetera, start=date(2026, 10, 1))
    refs = await service.refs_for(session, [primera.id, segunda.id, uuid4()])
    assert refs == {
        primera.id: MembershipRef(
            member_id=lucia.id,
            member_first_name="Lucía",
            member_last_name="Gómez",
            plan_name="Mensual",
            start_date=date(2026, 10, 21),
            end_date=date(2026, 11, 20),
        ),
        segunda.id: MembershipRef(
            member_id=pedro.id,
            member_first_name="Pedro",
            member_last_name="Ruiz",
            plan_name="Tiquetera 12",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 11, 30),
        ),
    }


async def test_refs_for_incluye_socios_y_planes_dados_de_baja(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session, deleted_at=reloj.now_utc(), status="inactive")
    plan = await make_plan(session, name="Viejo", deleted_at=reloj.now_utc())
    membresia = await make_membership(
        session, socio, plan, status="expired", start=date(2026, 9, 1)
    )
    refs = await service.refs_for(session, [membresia.id])
    assert refs[membresia.id].member_first_name == "Lucía"
    assert refs[membresia.id].plan_name == "Viejo"


async def test_refs_for_sin_ids_no_consulta(session: AsyncSession, sentencias: list[str]) -> None:
    assert await service.refs_for(session, []) == {}
    assert sentencias == []


async def test_refs_for_consulta_la_tabla_por_lotes_de_id_batch(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, sentencias: list[str]
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan)
    ids = [membresia.id, *(uuid4() for _ in range(449))]
    assert ID_BATCH == 200
    sentencias.clear()
    refs = await service.refs_for(session, ids)
    assert list(refs) == [membresia.id]
    assert len(_de_membresias(sentencias)) == 3, sentencias
