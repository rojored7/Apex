"""Desactivar una regla no toca los avisos generados (S5-V11c; S5-D267). # Rojo V11c

Vive aparte de `test_generate.py` porque necesita commit real y llaves confirmadas.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.notifications import service
from tests.notifications._apoyo import en_peticion
from tests.notifications._apoyo_avisos import HOY

pytestmark = pytest.mark.usefixtures("bus_confirmado", "reloj")


async def test_desactivar_una_regla_no_toca_los_avisos_ya_generados_y_se_envian(
    fabrica: async_sessionmaker[AsyncSession],
) -> None:
    """Rojo V11c: el aviso `pending` sobrevive a desactivar su regla y `send_pending` lo envía."""
    from app.modules.notifications.rules_crud import update_rule
    from app.modules.notifications.schemas import RulePatch
    from tests.notifications._apoyo_envio import CanalFalso, escenario_job

    await escenario_job(fabrica)
    async with fabrica() as sesion:
        resultado = await en_peticion(
            sesion, SYSTEM_USER_ID, lambda: service.generate_today(sesion, HOY)
        )
        regla = (
            await sesion.execute(text("SELECT id FROM notifications.notification_rules"))
        ).one()
    assert resultado.generados == 1
    async with fabrica() as sesion:
        with actor_scope(SYSTEM_USER_ID):
            await update_rule(sesion, regla.id, RulePatch(is_active=False))
            await sesion.commit()
    canal = CanalFalso()

    with actor_scope(SYSTEM_USER_ID):
        enviado = await service.send_pending(fabrica, HOY, channel=canal)

    assert (enviado.enviados, len(canal.enviados)) == (1, 1)
    async with fabrica() as sesion:
        estados = (
            await sesion.execute(text("SELECT status FROM notifications.notifications"))
        ).all()
    assert [e.status for e in estados] == ["sent"]
