"""Rendimiento del recibo PDF (S5-V11c; US-137.8). # Rojo V11c

Marcado `perf` (S2-D27): no es gate. `GET /payments/{id}/receipt.pdf` responde en menos de 1 s en
el p95 de 20 descargas (tras un calentamiento).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.payments.test_router_receipt import ruta_recibo

pytestmark = pytest.mark.perf

CORRIDAS = 20
TOPE_S = 1.0


async def test_el_recibo_responde_en_menos_de_1_s_p95(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    plan = await make_plan(session)
    socio = await make_member(session)
    membresia = await make_membership(session, socio, plan, status="active")
    pago = await make_payment(
        session, membresia, amount=60_000, paid_at=datetime(2026, 10, 10, 15, tzinfo=UTC)
    )
    cab = cabeceras(admin)
    primera = await app_http.get(ruta_recibo(pago.id), headers=cab)  # calentamiento
    assert primera.status_code == 200, primera.text
    muestras: list[float] = []

    for _ in range(CORRIDAS):
        inicio = time.perf_counter()
        r = await app_http.get(ruta_recibo(pago.id), headers=cab)
        muestras.append(time.perf_counter() - inicio)
        assert r.status_code == 200

    p95 = sorted(muestras)[int(CORRIDAS * 0.95) - 1]
    assert p95 < TOPE_S, f"p95={p95:.3f}s"
