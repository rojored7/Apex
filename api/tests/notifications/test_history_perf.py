"""Rendimiento del historial de avisos de un socio (S5-V11c; US-129.6). # Rojo V11c

Marcado `perf` (S2-D27): no es gate. Un socio con 1.000 avisos (siembra cruda con
`generate_series`, dentro de la transacción de la prueba); `service.list_for_member` y
`service.list` filtrado por ese socio responden en menos de 500 ms en el p95 de 20 corridas.
"""

from __future__ import annotations

import time
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID
from app.core.pagination import PageParams
from app.modules.notifications import service
from tests.factories.notifications import make_rule
from tests.notifications._apoyo_avisos import HOY, socio

pytestmark = [pytest.mark.perf, pytest.mark.usefixtures("listo")]

AVISOS = 1_000
CORRIDAS = 20
TOPE_S = 0.5


def _p95(muestras: list[float]) -> float:
    ordenadas = sorted(muestras)
    return ordenadas[max(0, int(len(ordenadas) * 0.95) - 1)]


async def test_el_historial_de_un_socio_con_mil_avisos_responde_en_menos_de_500_ms_p95(
    session: AsyncSession,
) -> None:
    regla = await make_rule(session)
    miembro = await socio(session)
    await session.execute(
        text(
            "INSERT INTO notifications.notifications (id, rule_id, member_id, membership_id, "
            "target_date, channel, status, rendered_subject, rendered_body, attempts, created_by) "
            "SELECT gen_random_uuid(), :regla, :socio, gen_random_uuid(), "
            "CAST(:hoy AS date) - i, 'whatsapp_link', 'pending', 'Asunto', 'Cuerpo', 0, :actor "
            "FROM generate_series(0, :n - 1) AS i"
        ),
        {
            "regla": regla.id,
            "socio": miembro.id,
            "hoy": HOY + timedelta(days=0),
            "n": AVISOS,
            "actor": SYSTEM_USER_ID,
        },
    )
    await session.commit()
    pagina = PageParams(limit=50, offset=0)
    await service.list_for_member(session, miembro.id, pagina)  # calentamiento
    muestras: list[float] = []

    for _ in range(CORRIDAS):
        inicio = time.perf_counter()
        salida = await service.list_for_member(session, miembro.id, pagina)
        muestras.append(time.perf_counter() - inicio)

    assert salida.total == AVISOS and len(salida.items) == 50
    assert _p95(muestras) < TOPE_S, f"p95={_p95(muestras):.3f}s"
