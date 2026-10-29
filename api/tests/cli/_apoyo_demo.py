"""Apoyo de `seed --demo` (S4B-B1): lo que el catálogo de `demo_dataset` obliga a la base.

- `HOY` y `EXPIRING_DAYS`: el "hoy" del reloj de prueba (`T0`, 2026-10-21 en Bogotá) y el valor por
  defecto de `expiring_days`; el seed los lee del reloj y de `settings.memberships_policy`.
- `catalogo()`: `demo_dataset(HOY, EXPIRING_DAYS)`.
- `esperados(spec)`: conteos exactos que deja una corrida completa (planes, socios, membresías,
  pagos, pagos anulados y estados guardados). Una renovación suma una membresía `pending_payment`.
- `contar(fabrica)`: los mismos conteos leídos de la base, más `audit_log` y `crypto_ops`.
- `titular(estados)`: el estado del socio según US-092 (vigente > pendiente > vencido).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import date
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.audit import AuditEntry
from app.core.crypto.models import CryptoOp
from app.modules.members.models import Member
from app.modules.memberships.models import Membership
from app.modules.payments.models import Payment
from app.modules.plans.models import Plan
from app.seed.dataset import DemoSpec, demo_dataset

HOY: Final = date(2026, 10, 21)
EXPIRING_DAYS: Final = 7
VIGENTES: Final = frozenset({"active", "expiring", "frozen"})
Fabrica = async_sessionmaker[AsyncSession]


def catalogo() -> DemoSpec:
    return demo_dataset(HOY, EXPIRING_DAYS)


def esperados(spec: DemoSpec) -> dict[str, int]:
    pagos = [
        pago
        for socio in spec.members
        for pago in (
            ([socio.sale.first_payment] if socio.sale.first_payment is not None else [])
            + list(socio.sale.extra_payments)
        )
    ]
    return {
        "planes": len(spec.plans),
        "socios": len(spec.members),
        "membresias": len(spec.members) + sum(1 for s in spec.members if s.sale.renewal),
        "pagos": len(pagos),
        "anulados": sum(1 for pago in pagos if pago.void),
    }


def estados_esperados(spec: DemoSpec) -> Counter[str]:
    cuenta: Counter[str] = Counter(socio.sale.expected_status for socio in spec.members)
    cuenta["pending_payment"] += sum(1 for socio in spec.members if socio.sale.renewal)
    return Counter({estado: n for estado, n in cuenta.items() if n})


def titular(estados: Iterable[str]) -> str | None:
    """Estado del socio (US-092) entre sus membresías no anuladas; `None` si no tiene ninguna."""
    vivos = [estado for estado in estados if estado != "cancelled"]
    for estado in vivos:
        if estado in VIGENTES:
            return estado
    for categoria in ("pending_payment", "expired"):
        if categoria in vivos:
            return categoria
    return None


def estados_de_socios(spec: DemoSpec) -> Counter[str]:
    """Cuántos socios hay por estado resuelto (lo que muestra el tablero)."""
    salida: Counter[str] = Counter()
    for socio in spec.members:
        estados = [socio.sale.expected_status]
        if socio.sale.renewal:
            estados.append("pending_payment")
        if (estado := titular(estados)) is not None:
            salida[estado] += 1
    return salida


async def _contar(sesion: AsyncSession, modelo: type) -> int:
    return int(await sesion.scalar(select(func.count()).select_from(modelo)) or 0)


async def contar(fabrica: Fabrica) -> dict[str, int]:
    async with fabrica() as sesion:
        anulados = await sesion.scalar(
            select(func.count()).select_from(Payment).where(Payment.voided.is_(True))
        )
        return {
            "planes": await _contar(sesion, Plan),
            "socios": await _contar(sesion, Member),
            "membresias": await _contar(sesion, Membership),
            "pagos": await _contar(sesion, Payment),
            "anulados": int(anulados or 0),
            "audit_log": await _contar(sesion, AuditEntry),
            "crypto_ops": await _contar(sesion, CryptoOp),
        }


async def estados_guardados(fabrica: Fabrica) -> Counter[str]:
    async with fabrica() as sesion:
        filas = await sesion.execute(
            select(Membership.status, func.count()).group_by(Membership.status)
        )
        return Counter({estado: int(n) for estado, n in filas})
