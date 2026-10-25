"""Rendimiento de la lista y del resumen de membresías (S3-B7; US-091, US-092 criterio 10;
condición 3 del impacto, M-10, S3-D71).

Marcado `perf` (S2-D27): los gates corren `-m "not perf"` salvo el de B7 (el que lista este
archivo) y V5.

- 1.000 socios y 3.000 membresías (tres por socio, sin solaparse) sembrados con `make_members` y
  `make_memberships` dentro de la transacción de la prueba (`session`: todo se revierte al salir;
  `db_test` queda sin sus filas). Hoy 2026-10-21, `expiring_days` 7:
  - junio (del 2026-06-01 al 2026-06-30, `active` guardada: vencida) y julio (del 2026-07-01 al
    2026-07-31, `expired`) para los 1.000;
  - vigente: 300 por vencer (del 2026-09-25 al 2026-10-25), 500 al día (del 2026-10-01 al
    2026-11-15) y 200 `pending_payment` (del 2026-10-21 al 2026-11-20).
- Tras un calentamiento, `GET /memberships?status=expiring` (25 por página; `total` 300) responde
  en menos de 500 ms (`time.perf_counter`).
- `GET /memberships/summary` sin caché (la fixture autouse pone TTL 0) responde en menos de
  300 ms tras un calentamiento: 500, 300, 0, 0, 200.
"""

from __future__ import annotations

import time
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_members
from tests.factories.memberships import make_memberships
from tests.factories.plans import make_plan
from tests.memberships._apoyo import MEMBERSHIPS, RESUMEN

pytestmark = pytest.mark.perf

SOCIOS = 1000
LISTA_MS = 500
RESUMEN_MS = 300


async def _sembrar(session: AsyncSession) -> None:
    plan = await make_plan(session, name="Mensual carga")
    socios = await make_members(session, SOCIOS, last_name="Carga")
    await make_memberships(
        session,
        SOCIOS,
        plan,
        members=socios,
        status="active",
        start=date(2026, 6, 1),
        end=date(2026, 6, 30),
    )
    await make_memberships(
        session,
        SOCIOS,
        plan,
        members=socios,
        status="expired",
        start=date(2026, 7, 1),
        end=date(2026, 7, 31),
    )
    await make_memberships(
        session,
        300,
        plan,
        members=socios[:300],
        status="active",
        start=date(2026, 9, 25),
        end=date(2026, 10, 25),
    )
    await make_memberships(
        session,
        500,
        plan,
        members=socios[300:800],
        status="active",
        start=date(2026, 10, 1),
        end=date(2026, 11, 15),
    )
    await make_memberships(
        session,
        200,
        plan,
        members=socios[800:],
        status="pending_payment",
        start=date(2026, 10, 21),
        end=date(2026, 11, 20),
    )
    contadas = await session.scalar(text("SELECT count(*) FROM memberships.memberships"))
    assert contadas == 3 * SOCIOS
    await session.execute(text("ANALYZE memberships.memberships"))
    await session.execute(text("ANALYZE members.members"))


async def _medir(
    cliente: AsyncClient, ruta: str, cabeceras: dict[str, str], **params: str
) -> float:
    inicio = time.perf_counter()
    r = await cliente.get(ruta, params=params, headers=cabeceras)
    transcurrido = (time.perf_counter() - inicio) * 1000
    assert r.status_code == 200, r.text
    return transcurrido


async def test_con_mil_socios_la_lista_de_por_vencer_tarda_menos_de_500_ms(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    await _sembrar(session)
    coach = cabeceras(await usuario_real("coach"))
    await _medir(app_http, MEMBERSHIPS, coach, status="expiring")  # calentamiento
    transcurrido = await _medir(app_http, MEMBERSHIPS, coach, status="expiring")
    r = await app_http.get(MEMBERSHIPS, params={"status": "expiring"}, headers=coach)
    assert (r.json()["total"], len(r.json()["items"])) == (300, 25)
    print(f"\nlista expiring con {SOCIOS} socios y {3 * SOCIOS} membresías: {transcurrido:.1f} ms")
    assert transcurrido < LISTA_MS


async def test_con_mil_socios_el_resumen_sin_cache_tarda_menos_de_300_ms(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    await _sembrar(session)
    coach = cabeceras(await usuario_real("coach"))
    await _medir(app_http, RESUMEN, coach)  # calentamiento (TTL 0: no queda en caché)
    transcurrido = await _medir(app_http, RESUMEN, coach)
    r = await app_http.get(RESUMEN, headers=coach)
    assert r.json() == {
        "active": 500,
        "expiring": 300,
        "expired": 0,
        "frozen": 0,
        "pending_payment": 200,
    }
    print(f"\nresumen sin caché con {SOCIOS} socios: {transcurrido:.1f} ms")
    assert transcurrido < RESUMEN_MS
