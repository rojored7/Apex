"""`payments.queries._detail` sin referencia de membresía (revisión de seguridad de S3-B8, LOW-1).

Un pago cuya membresía no devuelve `memberships.refs_for` (socio o plan ausentes) rompe la
integridad: falla cerrado con `LookupError` (500 sin datos) y deja un `logger.error` del logger
`app.payments` con solo el id del pago.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.payments import queries
from app.modules.payments.models import Payment


def test_un_pago_sin_referencia_falla_cerrado_y_lo_registra_con_solo_el_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    instante = datetime(2026, 10, 10, 15, tzinfo=UTC)
    pago = Payment(
        id=uuid4(),
        membership_id=uuid4(),
        member_id=uuid4(),
        amount_cop=60_000,
        method="cash",
        reference="EF-001",
        paid_at=instante,
        registered_by=uuid4(),
        voided=False,
        created_at=instante,
    )
    with caplog.at_level(logging.ERROR, logger="app.payments"), pytest.raises(LookupError):
        queries._detail(pago, {}, {})
    registros = [r for r in caplog.records if r.name == "app.payments"]
    assert len(registros) == 1
    assert getattr(registros[0], "payment_id", None) == str(pago.id)
    assert "EF-001" not in registros[0].getMessage()
