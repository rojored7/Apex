"""Fábrica de `payments.payments` (plan del Sprint 3, sección 2, bloque B3; US-095).

- `make_payment(session, membership, *, amount=None, method="cash", paid_at=None, voided=False,
  void_reason=None, reference=None, registered_by=None, **cambios) -> Payment`: inserta por ORM
  (el hook de auditoría la ve) bajo `actor_scope(SYSTEM_USER_ID)`, hace `flush` y confirma el
  savepoint, como `make_membership`. `member_id` sale de la membresía; `amount` por defecto es
  `membership.agreed_price_cop`; `paid_at` por defecto es "ahora" del reloj actual;
  `registered_by` por defecto es `SYSTEM_USER_ID`. `voided=True` llena las cuatro columnas de
  anulación (motivo por defecto, `voided_by = SYSTEM_USER_ID`, `voided_at` = ahora): es un `INSERT`
  legal también con los triggers de `0011` (B4), que solo vigilan `UPDATE`, `DELETE` y el vaciado.
  `**cambios` admite cualquier columna (por ejemplo `created_at` para fijar cuándo se registró).
  **No** emite eventos ni pasa por `register`: prepara sumas, conteos y huellas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.memberships.models import Membership
from app.modules.payments.models import Payment

MOTIVO_ANULACION: Final = "Anulado en la fábrica de pruebas"


async def make_payment(
    session: AsyncSession,
    membership: Membership,
    *,
    amount: int | None = None,
    method: str = "cash",
    paid_at: datetime | None = None,
    voided: bool = False,
    void_reason: str | None = None,
    reference: str | None = None,
    registered_by: UUID | None = None,
    **cambios: Any,
) -> Payment:
    """Inserta un `Payment` de la membresía bajo `SYSTEM_USER_ID` y confirma."""
    ahora = current_clock().now_utc()
    valores: dict[str, Any] = {
        "membership_id": membership.id,
        "member_id": membership.member_id,
        "amount_cop": membership.agreed_price_cop if amount is None else amount,
        "method": method,
        "reference": reference,
        "paid_at": paid_at or ahora,
        "registered_by": registered_by or SYSTEM_USER_ID,
        "voided": voided,
        "created_by": SYSTEM_USER_ID,
    }
    if voided:
        valores.update(
            void_reason=void_reason or MOTIVO_ANULACION,
            voided_by=SYSTEM_USER_ID,
            voided_at=ahora,
        )
    valores.update(cambios)
    pago = Payment(**valores)
    with actor_scope(SYSTEM_USER_ID):
        session.add(pago)
        await session.flush()
        await session.commit()
    return pago
