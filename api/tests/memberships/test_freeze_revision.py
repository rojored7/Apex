"""`memberships.service.freeze`: casos que nacieron en la revisión de seguridad del Verde de S3-B2.

"Hoy" es 2026-10-21 (`reloj`). La membresía base es `active` del 2026-10-01 al 2026-10-31.

- M1: un socio dado de baja o inactivo no congela (422 `member_inactive`, como `sell`, D21), sin
  congelación, sin fin corrido y sin fila `update` de auditoría.
- L4: `freezes` sale en orden de `frozen_from` aunque la nueva sea anterior a otra ya terminada
  (previa del 19 al 20 de octubre; nueva del 14 al 15, retroactiva dentro de los 7 días de Q9).
- La `EXCLUDE` de congelaciones (`ex_membership_freezes_dates`) es la red si la lectura de las
  previas no viera una ventana: el flush choca con 23P01 y `freeze` responde 409
  `freeze_already_scheduled`, sin filas nuevas.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.modules.memberships import lifecycle as lifecycle_module
from app.modules.memberships.exceptions import FreezeRejected, MemberInactive
from app.modules.memberships.models import MembershipFreeze
from tests.factories.members import make_member
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import (
    congelaciones_de,
    congelar,
    leer_auditoria,
    leer_membresia,
)

ACTOR = UUID("0000000a-0000-4000-8000-00000000a004")
HOY = date(2026, 10, 21)
INICIO = date(2026, 10, 1)
FIN = date(2026, 10, 31)


@pytest.mark.parametrize(
    "cambios",
    [{"status": "inactive"}, {"deleted_at": datetime(2026, 10, 20, 12, tzinfo=UTC)}],
    ids=["inactivo", "dado-de-baja"],
)
async def test_un_socio_inactivo_o_dado_de_baja_no_congela(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, cambios: dict[str, Any]
) -> None:
    socio = await make_member(session, **cambios)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan, status="active", start=INICIO)
    membresia_id = membresia.id
    with pytest.raises(MemberInactive) as error:
        await congelar(session, ACTOR, membership_id=membresia_id, frozen_from=HOY, frozen_to=HOY)
    assert (error.value.status, error.value.code) == (422, "member_inactive")
    assert await congelaciones_de(session, membresia_id) == []
    fila = await leer_membresia(session, membresia_id)
    assert fila is not None and (fila["status"], fila["end_date"]) == ("active", FIN)
    acciones = [
        f["action"] for f in await leer_auditoria(session, "memberships.memberships", membresia_id)
    ]
    assert "update" not in acciones


async def test_las_congelaciones_salen_en_orden_de_frozen_from(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan, status="active", start=INICIO)
    await make_freeze(session, membresia, date(2026, 10, 19), date(2026, 10, 20))
    salida = await congelar(
        session,
        ACTOR,
        membership_id=membresia.id,
        frozen_from=date(2026, 10, 14),
        frozen_to=date(2026, 10, 15),
    )
    assert [(f.frozen_from, f.days) for f in salida.freezes] == [
        (date(2026, 10, 14), 2),
        (date(2026, 10, 19), 2),
    ]
    assert (salida.status, salida.end_date) == ("active", date(2026, 11, 2))


async def test_la_exclude_de_congelaciones_sale_como_freeze_already_scheduled(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan, status="active", start=INICIO)
    membresia_id = membresia.id
    await make_freeze(session, membresia, date(2026, 10, 25), date(2026, 10, 27))

    async def sin_previas(
        _session: AsyncSession, ids: Iterable[UUID]
    ) -> dict[UUID, list[MembershipFreeze]]:
        return {membership_id: [] for membership_id in ids}

    monkeypatch.setattr(lifecycle_module, "_freeze_rows_for", sin_previas)
    with pytest.raises(FreezeRejected) as error:
        await congelar(
            session,
            ACTOR,
            membership_id=membresia_id,
            frozen_from=HOY,
            frozen_to=date(2026, 10, 26),
        )
    assert (error.value.status, error.value.code, error.value.field) == (
        409,
        "freeze_already_scheduled",
        None,
    )
    assert len(await congelaciones_de(session, membresia_id)) == 1
    fila = await leer_membresia(session, membresia_id)
    assert fila is not None and fila["end_date"] == FIN
