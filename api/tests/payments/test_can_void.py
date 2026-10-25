"""`payments.rules.can_void` (S3-B4, US-096; blueprint B4; D13).

Pura: un pago vigente se puede anular y uno ya anulado no (la segunda anulación es 409
`payment_already_voided` en `void`, B5). Sin base: los `Payment` se construyen en memoria.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.modules.payments.models import Payment
from app.modules.payments.rules import can_void

PAGADO = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)


def _pago(**cambios: object) -> Payment:
    valores: dict[str, object] = {
        "membership_id": uuid4(),
        "member_id": uuid4(),
        "amount_cop": 120_000,
        "method": "cash",
        "paid_at": PAGADO,
        "registered_by": uuid4(),
        "voided": False,
    }
    valores.update(cambios)
    return Payment(**valores)


def test_un_pago_vigente_se_puede_anular() -> None:
    assert can_void(_pago()) is True


def test_un_pago_anulado_no_se_puede_anular_otra_vez() -> None:
    anulado = _pago(
        voided=True, void_reason="Monto mal digitado", voided_by=uuid4(), voided_at=PAGADO
    )
    assert can_void(anulado) is False


def test_can_void_no_cambia_el_pago() -> None:
    pago = _pago()
    can_void(pago)
    assert (pago.voided, pago.void_reason, pago.voided_by, pago.voided_at) == (
        False,
        None,
        None,
        None,
    )
