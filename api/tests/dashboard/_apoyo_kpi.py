"""Escenario de los KPI de avisos del tablero (S5-B10, US-132; S5-D39, S5-D80, S5-D219). # Rojo B10

`sembrar_kpi(session, hoy)` deja, con las factorías de B7:
- cuatro socios vivos: Ana y Bea con consentimiento, Caro y Dina sin él;
- dos dados de baja (`deleted_at` fijado): Eva sin consentimiento y Fran con él;
- avisos: cuentan DOS (el `pending` de hoy de Ana y el `failed` de hace 10 días de Caro); no
  cuentan el `sent` de hoy, el `skipped` de hoy, el `pending` de hace 16 días (fuera de la
  ventana de 15, S5-D219) ni el `pending` de hoy del socio dado de baja (S5-D225).
Valores a mano: `AVISOS_DE_HOY = 2` y `SIN_CONSENTIMIENTO = 2` (Caro y Dina; Eva, dada de baja
sin consentimiento, NO cuenta).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import T0
from tests.factories.notifications import make_notification, make_rule
from tests.notifications._apoyo_avisos import ANTES, socio

AVISOS_DE_HOY: Final = 2
SIN_CONSENTIMIENTO: Final = 2


@dataclass(frozen=True)
class EscenarioKpi:
    avisos_de_hoy: int
    sin_consentimiento: int


async def sembrar_kpi(session: AsyncSession, hoy: date) -> EscenarioKpi:
    regla = await make_rule(session)
    ana = await socio(session, nombre="Ana", consentido=True)
    await socio(session, nombre="Bea", consentido=True)
    caro = await socio(session, nombre="Caro", consentido=False)
    await socio(session, nombre="Dina", consentido=False)
    eva = await socio(session, nombre="Eva", consentido=False, deleted_at=ANTES, status="inactive")
    await socio(session, nombre="Fran", consentido=True, deleted_at=T0, status="inactive")

    async def aviso(miembro_id: UUID, estado: str, objetivo: date) -> None:
        await make_notification(
            session, regla, member_id=miembro_id, status=estado, target_date=objetivo
        )

    await aviso(ana.id, "pending", hoy)
    await aviso(caro.id, "failed", hoy - timedelta(days=10))
    await aviso(ana.id, "sent", hoy)
    await aviso(ana.id, "skipped", hoy)
    await aviso(caro.id, "pending", hoy - timedelta(days=16))
    await aviso(eva.id, "pending", hoy)
    return EscenarioKpi(avisos_de_hoy=AVISOS_DE_HOY, sin_consentimiento=SIN_CONSENTIMIENTO)
