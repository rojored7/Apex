"""Rendimiento de la lista y del resumen de pagos (S3-B8; US-098, US-100; S3-D71, E11).

Marcado `perf` (S2-D27): los gates corren `-m "not perf"` salvo el de B8 (el que lista este
archivo) y V5. Si la lista no baja de 500 ms, la salida es la migración condicional
`0014_payments_registered_by_idx` (plan B8, migración).

- Siembra cruda permitida (plan B8.2): 100 socios y 100 membresías con SQL (blobs falsos que la
  lista nunca descifra) y 10.000 pagos con `generate_series`, todo dentro de la transacción de
  la prueba (`session`: se revierte al salir; `db_test` queda sin sus filas). El `INSERT` de
  pagos es legal con los triggers de `0011` (solo vigilan `UPDATE`, `DELETE` y el vaciado).
  Pago `i` (de 0 a 9.999): membresía `i % 100`, monto `1.000 + i`, medio `i % 3` (0 efectivo, 1
  Nequi, 2 Bre-B), `paid_at = 2026-10-01T05:00Z + 4 min * i` (el último el 2026-10-28T23:36Z:
  todos en octubre de Bogotá) y anulado si `i % 50 = 0` (200 anulados).
- Totales a mano: suma de todos `10.000 * 1.000 + (0 + ... + 9.999) = 59.995.000`; anulados
  `200 * 1.000 + 50 * (0 + ... + 199) = 1.195.000`; `total_cop` 58.800.000 y
  `payments_count` 9.800 (el desglose por medio se calcula en la prueba con la misma regla).
- Tras un calentamiento, `GET /payments?limit=25` (total 10.000) responde en menos de 500 ms y
  `GET /payments/summary?month=2026-10` en menos de 300 ms (`time.perf_counter`).
"""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.plans import make_plan
from tests.payments._apoyo import PAYMENTS, RESUMEN

pytestmark = pytest.mark.perf

PAGOS = 10_000
MEMBRESIAS = 100
LISTA_MS = 500
RESUMEN_MS = 300
MEDIOS = ("cash", "nequi", "breb")

_SOCIOS = text(
    "INSERT INTO members.members (id, first_name, last_name, status, document_type, document, "
    "document_idx, created_by) "
    "SELECT gen_random_uuid(), 'Carga', 'Pagos', 'active', 'CC', 'apx1.prueba.A256GCM.x.x', "
    "'carga-pagos-' || i, :actor FROM generate_series(1, :n) AS i"
)
_MEMBRESIAS = text(
    "INSERT INTO memberships.memberships (id, member_id, plan_id, agreed_price_cop, start_date, "
    "end_date, status, created_by) "
    "SELECT gen_random_uuid(), m.id, :plan, 120000, DATE '2026-10-01', DATE '2026-10-30', "
    "'active', :actor FROM members.members m WHERE m.last_name = 'Pagos'"
)
_PAGOS = text(
    "WITH ms AS (SELECT id, member_id, row_number() OVER (ORDER BY id) - 1 AS k "
    "FROM memberships.memberships WHERE plan_id = :plan) "
    "INSERT INTO payments.payments (id, membership_id, member_id, amount_cop, method, paid_at, "
    "registered_by, voided, void_reason, voided_by, voided_at, created_by) "
    "SELECT gen_random_uuid(), ms.id, ms.member_id, 1000 + i, "
    "(ARRAY['cash', 'nequi', 'breb'])[1 + i % 3], "
    "TIMESTAMPTZ '2026-10-01 05:00:00+00' + i * INTERVAL '4 minutes', :actor, i % 50 = 0, "
    "CASE WHEN i % 50 = 0 THEN 'Carga de rendimiento' END, "
    "CASE WHEN i % 50 = 0 THEN CAST(:actor AS uuid) END, "
    "CASE WHEN i % 50 = 0 THEN TIMESTAMPTZ '2026-10-29 00:00:00+00' END, :actor "
    "FROM generate_series(0, :n - 1) AS i JOIN ms ON ms.k = i % :m"
)


async def _sembrar(session: AsyncSession) -> None:
    plan = await make_plan(session, name="Mensual carga de pagos")
    actor = SYSTEM_USER_ID
    await session.execute(_SOCIOS, {"actor": actor, "n": MEMBRESIAS})
    await session.execute(_MEMBRESIAS, {"actor": actor, "plan": plan.id})
    await session.execute(_PAGOS, {"actor": actor, "plan": plan.id, "n": PAGOS, "m": MEMBRESIAS})
    contados = await session.scalar(text("SELECT count(*) FROM payments.payments"))
    assert contados == PAGOS
    for tabla in ("payments.payments", "memberships.memberships", "members.members"):
        await session.execute(text(f"ANALYZE {tabla}"))


async def _medir(
    cliente: AsyncClient, ruta: str, cabeceras: dict[str, str], **params: str
) -> float:
    inicio = time.perf_counter()
    r = await cliente.get(ruta, params=params, headers=cabeceras)
    transcurrido = (time.perf_counter() - inicio) * 1000
    assert r.status_code == 200, r.text
    return transcurrido


async def test_con_diez_mil_pagos_la_primera_pagina_tarda_menos_de_500_ms(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    await _sembrar(session)
    coach = cabeceras(await usuario_real("coach"))
    await _medir(app_http, PAYMENTS, coach, limit="25")  # calentamiento
    transcurrido = await _medir(app_http, PAYMENTS, coach, limit="25")
    r = await app_http.get(PAYMENTS, params={"limit": "25"}, headers=coach)
    assert (r.json()["total"], len(r.json()["items"])) == (PAGOS, 25)
    assert r.json()["items"][0]["amount_cop"] == 1_000 + PAGOS - 1  # el más reciente
    print(f"\nlista de pagos con {PAGOS} pagos: {transcurrido:.1f} ms")
    assert transcurrido < LISTA_MS


async def test_con_diez_mil_pagos_el_resumen_del_mes_tarda_menos_de_300_ms(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    await _sembrar(session)
    coach = cabeceras(await usuario_real("coach"))
    await _medir(app_http, RESUMEN, coach, month="2026-10")  # calentamiento
    transcurrido = await _medir(app_http, RESUMEN, coach, month="2026-10")
    r = await app_http.get(RESUMEN, params={"month": "2026-10"}, headers=coach)
    vigentes = [i for i in range(PAGOS) if i % 50 != 0]
    por_medio = {
        medio: sum(1_000 + i for i in vigentes if i % 3 == k) for k, medio in enumerate(MEDIOS)
    }
    assert r.json() == {
        "month": "2026-10",
        "total_cop": 58_800_000,
        "by_method": por_medio,
        "voided_count": 200,
        "payments_count": 9_800,
    }
    assert sum(por_medio.values()) == 58_800_000
    print(f"\nresumen del mes con {PAGOS} pagos: {transcurrido:.1f} ms")
    assert transcurrido < RESUMEN_MS
