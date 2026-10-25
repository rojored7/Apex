"""Paridad del estado derivado en SQL con la regla pura (S3-B7, US-091, US-092; D5, M-10, S3-D53).

- `queries.status_expr(today, expiring_days)` ejecutado en PostgreSQL da, fila por fila, lo mismo
  que `rules.compute_status(snapshot, today, expiring_days, congelaciones)` sobre una malla:
  `today` desde el fin menos 9 hasta el fin más 2 (fin 2026-10-31: del 2026-10-22 al 2026-11-02),
  `expiring_days` 0, 3 y 7, con filas guardadas `active`, `expired` y `frozen` (lo guardado no
  manda salvo `pending_payment` y `cancelled`), con una congelación del 25 al 28 de octubre que
  contiene algunos `today` de la malla, con una congelación que cruza el fin (30 de octubre al 1
  de noviembre: congelada gana a vencida), con `classes_remaining` 0 y 5, `pending_payment`,
  `cancelled` y una futura (del 2026-11-01 al 2026-11-30).
- `queries.member_status_rank_expr(today, expiring_days)` es, para cada fila no anulada de la
  misma malla, la posición en `rules.MEMBER_STATUS_PRIORITY` de su categoría: `pending_payment`
  y `expired` por su estado efectivo; si no, `current` con inicio <= hoy y `future` después.
- La prioridad del `DISTINCT ON (member_id)` armado con esas dos expresiones (sin anuladas;
  orden `member_id, rango, end_date DESC`) coincide con `rules.resolve_member_status` sobre los
  nueve casos de US-092 sembrados con la fábrica (hoy 2026-10-21, `expiring_days` 7), y
  `queries.status_for` da el mismo estado (los socios sin membresías no anuladas no aparecen).

Casos de US-092 con hoy 2026-10-21 (fechas a mano; `expiring_days` 7):
1. vigente del 1 al 31 de octubre: faltan 10 días → `active`;
2. `active` guardada del 26 de septiembre al 26 de octubre (faltan 5: `expiring`) y renovación
   `pending_payment` del 27 de octubre al 26 de noviembre → `expiring`;
3. solo una futura `active` del 28 de octubre al 27 de noviembre → `active`;
4. solo una `active` guardada del 1 al 31 de agosto (vencida por fecha) → `expired`;
5. solo una anulada → `none` (no aparece);
6. `active` del 1 de octubre al 15 de noviembre con congelación del 20 al 23 de octubre →
   `frozen`;
7. vencida (guardada `expired`, agosto) y `pending_payment` del 21 de octubre al 20 de noviembre
   → `pending_payment`;
8. vencida (agosto) y futura `active` del 28 de octubre al 27 de noviembre → `expired`;
9. socio sin membresías → `none` (no aparece).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.dialects.postgresql.asyncpg import dialect as postgresql_dialect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.modules.memberships import queries, service
from app.modules.memberships.models import Membership
from app.modules.memberships.rules import (
    MEMBER_STATUS_PRIORITY,
    FreezeWindow,
    MembershipSnapshot,
    MembershipStatus,
    compute_status,
    effective,
    resolve_member_status,
)
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.plans import make_plan

HOY = date(2026, 10, 21)
FIN = date(2026, 10, 31)
INICIO = date(2026, 9, 1)
MALLA_DE_HOY = [FIN + timedelta(days=d) for d in range(-9, 3)]
EXPIRING_DAYS = (0, 3, 7)


@dataclass(frozen=True)
class Fila:
    snapshot: MembershipSnapshot
    freezes: tuple[FreezeWindow, ...]


def _snapshot(m: Membership) -> MembershipSnapshot:
    return MembershipSnapshot(
        id=m.id,
        status=MembershipStatus(m.status),
        start_date=m.start_date,
        end_date=m.end_date,
        classes_remaining=m.classes_remaining,
    )


async def _socio(session: AsyncSession, apellido: str) -> Any:
    return await make_member(
        session,
        first_name="Paridad",
        last_name=apellido,
        document=unique_document(),
        phone=None,
        email=None,
    )


async def _malla(session: AsyncSession) -> dict[str, Fila]:
    """Una fila por caso de la malla, cada una de un socio distinto (la `EXCLUDE` es por socio)."""
    dias = await make_plan(session, name="Paridad días")
    clases = await make_plan(
        session, name="Paridad clases", kind="classes", duration_days=60, class_count=10
    )
    casos: dict[str, tuple[Any, dict[str, Any], list[tuple[date, date]]]] = {
        "activa": (dias, {"status": "active"}, []),
        "guardada-vencida": (dias, {"status": "expired"}, []),
        "guardada-congelada-sin-ventana": (dias, {"status": "frozen"}, []),
        "con-congelacion": (dias, {"status": "active"}, [(date(2026, 10, 25), date(2026, 10, 28))]),
        "congelacion-que-cruza-el-fin": (
            dias,
            {"status": "active"},
            [(date(2026, 10, 30), date(2026, 11, 1))],
        ),
        "sin-clases": (clases, {"status": "active", "classes_remaining": 0}, []),
        "con-clases": (clases, {"status": "active", "classes_remaining": 5}, []),
        "sin-clases-congelada": (
            clases,
            {"status": "active", "classes_remaining": 0},
            [(date(2026, 10, 25), date(2026, 10, 28))],
        ),
        "pendiente": (dias, {"status": "pending_payment"}, []),
        "anulada": (dias, {"status": "cancelled"}, []),
        "futura": (
            dias,
            {"status": "active", "start": date(2026, 11, 1), "end": date(2026, 11, 30)},
            [],
        ),
    }
    filas: dict[str, Fila] = {}
    for nombre, (plan, cambios, ventanas) in casos.items():
        datos = {"start": INICIO, "end": FIN, **cambios}
        membresia = await make_membership(session, await _socio(session, nombre), plan, **datos)
        for desde, hasta in ventanas:
            await make_freeze(session, membresia, desde, hasta)
        filas[nombre] = Fila(_snapshot(membresia), tuple(FreezeWindow(d, h) for d, h in ventanas))
    return filas


async def _en_sql(session: AsyncSession, expresion: Any, ids: Sequence[UUID]) -> dict[UUID, Any]:
    consulta = select(Membership.id, expresion).where(Membership.id.in_(ids))
    return {fila[0]: fila[1] for fila in (await session.execute(consulta)).all()}


async def test_status_expr_coincide_con_compute_status_en_toda_la_malla(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    filas = await _malla(session)
    ids = [f.snapshot.id for f in filas.values()]
    diferencias: list[str] = []
    for hoy in MALLA_DE_HOY:
        for dias in EXPIRING_DAYS:
            en_sql = await _en_sql(session, queries.status_expr(hoy, dias), ids)
            for nombre, fila in filas.items():
                esperado = compute_status(fila.snapshot, hoy, dias, fila.freezes)
                if en_sql[fila.snapshot.id] != esperado.value:
                    diferencias.append(f"{nombre} {hoy} d={dias}: {en_sql[fila.snapshot.id]}")
    assert diferencias == []


def _categoria(m: MembershipSnapshot, hoy: date) -> str:
    """Categoría de US-092 de un snapshot con estado efectivo (docstring de `rules`)."""
    if m.status in (MembershipStatus.pending_payment, MembershipStatus.expired):
        return m.status.value
    return "current" if m.start_date <= hoy else "future"


async def test_el_rango_es_la_posicion_de_la_categoria_en_member_status_priority(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    filas = {n: f for n, f in (await _malla(session)).items() if n != "anulada"}
    ids = [f.snapshot.id for f in filas.values()]
    diferencias: list[str] = []
    for hoy in (date(2026, 10, 21), date(2026, 10, 26), date(2026, 11, 1), date(2026, 11, 2)):
        for dias in EXPIRING_DAYS:
            rangos = await _en_sql(session, queries.member_status_rank_expr(hoy, dias), ids)
            for nombre, fila in filas.items():
                efectivo = effective(fila.snapshot, hoy, dias, fila.freezes)
                esperado = MEMBER_STATUS_PRIORITY.index(_categoria(efectivo, hoy))
                if rangos[fila.snapshot.id] != esperado:
                    diferencias.append(f"{nombre} {hoy} d={dias}: {rangos[fila.snapshot.id]}")
    assert diferencias == []


# Los nueve casos de US-092 ---------------------------------------------------------------------

NUEVE_CASOS: dict[str, tuple[list[tuple[date, date, str]], list[tuple[date, date]], str]] = {
    "solo-vigente": ([(date(2026, 10, 1), FIN, "active")], [], "active"),
    "por-vencer-y-renovacion-pendiente": (
        [
            (date(2026, 9, 26), date(2026, 10, 26), "active"),
            (date(2026, 10, 27), date(2026, 11, 26), "pending_payment"),
        ],
        [],
        "expiring",
    ),
    "solo-futura-activa": ([(date(2026, 10, 28), date(2026, 11, 27), "active")], [], "active"),
    "solo-vencida": ([(date(2026, 8, 1), date(2026, 8, 31), "active")], [], "expired"),
    "solo-anulada": ([(date(2026, 10, 1), FIN, "cancelled")], [], "none"),
    "congelada": (
        [(date(2026, 10, 1), date(2026, 11, 15), "active")],
        [(date(2026, 10, 20), date(2026, 10, 23))],
        "frozen",
    ),
    "pendiente-y-vencida": (
        [
            (date(2026, 8, 1), date(2026, 8, 31), "expired"),
            (date(2026, 10, 21), date(2026, 11, 20), "pending_payment"),
        ],
        [],
        "pending_payment",
    ),
    "vencida-y-futura-activa": (
        [
            (date(2026, 8, 1), date(2026, 8, 31), "active"),
            (date(2026, 10, 28), date(2026, 11, 27), "active"),
        ],
        [],
        "expired",
    ),
    "vacio": ([], [], "none"),
}


async def _nueve_casos(
    session: AsyncSession,
) -> dict[str, tuple[UUID, list[Fila]]]:
    """Un socio por caso; la congelación (si hay) va en la primera membresía del caso."""
    plan = await make_plan(session, name="Mensual paridad")
    salida: dict[str, tuple[UUID, list[Fila]]] = {}
    for nombre, (membresias, ventanas, _) in NUEVE_CASOS.items():
        socio = await _socio(session, nombre)
        filas: list[Fila] = []
        for indice, (inicio, fin, estado) in enumerate(membresias):
            membresia = await make_membership(
                session, socio, plan, status=estado, start=inicio, end=fin
            )
            propias = ventanas if indice == 0 else []
            for desde, hasta in propias:
                await make_freeze(session, membresia, desde, hasta)
            filas.append(Fila(_snapshot(membresia), tuple(FreezeWindow(d, h) for d, h in propias)))
        salida[nombre] = (socio.id, filas)
    return salida


def _oraculo(filas: list[Fila]) -> str:
    efectivos = [effective(f.snapshot, HOY, 7, f.freezes) for f in filas]
    return resolve_member_status(efectivos, HOY)


async def test_el_distinct_on_por_rango_coincide_con_resolve_member_status(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    casos = await _nueve_casos(session)
    por_socio = {socio: nombre for nombre, (socio, _) in casos.items()}
    consulta = (
        select(Membership.member_id, queries.status_expr(HOY, 7))
        .where(
            Membership.member_id.in_(list(por_socio)),
            Membership.status != "cancelled",
        )
        .order_by(
            Membership.member_id,
            queries.member_status_rank_expr(HOY, 7),
            Membership.end_date.desc(),
        )
        .ext(distinct_on(Membership.member_id))
    )
    en_sql = {por_socio[f[0]]: f[1] for f in (await session.execute(consulta)).all()}
    oraculo = {nombre: _oraculo(filas) for nombre, (_, filas) in casos.items()}
    esperado = {nombre: estado for nombre, (_, _, estado) in NUEVE_CASOS.items()}
    assert oraculo == esperado  # el oráculo da lo que dice US-092
    assert en_sql == {n: e for n, e in esperado.items() if e != "none"}


async def test_status_for_da_el_mismo_estado_que_el_oraculo_en_los_nueve_casos(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    casos = await _nueve_casos(session)
    estados = await service.status_for(session, [socio for socio, _ in casos.values()], today=HOY)
    obtenido = {
        nombre: estados[socio].status if socio in estados else "none"
        for nombre, (socio, _) in casos.items()
    }
    assert obtenido == {nombre: _oraculo(filas) for nombre, (_, filas) in casos.items()}
    sin_fila = {"solo-anulada", "vacio"}
    assert {nombre for nombre, (socio, _) in casos.items() if socio not in estados} == sin_fila


@pytest.mark.parametrize("dias", EXPIRING_DAYS)
async def test_status_expr_es_una_expresion_sin_filas_de_otro_esquema(dias: int) -> None:
    """La expresión solo nombra tablas de `memberships` (D5: el `EXISTS` de congelación usa
    `membership_freezes` del mismo esquema)."""
    sql = str(select(queries.status_expr(HOY, dias)).compile(dialect=postgresql_dialect())).lower()
    assert "membership_freezes" in sql
    for ajeno in ("members.", "plans.", "payments.", "auth.", "settings."):
        assert ajeno not in sql.replace("memberships.", "")
