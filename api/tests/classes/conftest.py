"""Fixtures de `tests/classes` (S7-C1): el puerto de membresías con un doble.

`bus_confirmado` se reutiliza de `tests/members` (llaves con commit real para `dos_sesiones`).
Mientras `memberships` no registra el suyo (C2), cada prueba de check-in registra un
`FakeMembershipPort`; al terminar se quita para no filtrarlo a otras pruebas.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.modules.classes import service
from tests.factories.classes import FakeMembershipPort
from tests.members.conftest import bus_confirmado  # noqa: F401  (llaves con commit real)


@pytest.fixture
def puerto() -> Iterator[FakeMembershipPort]:
    """Un puerto doble con membresía `active`; la prueba puede cambiar `.status`."""
    doble = FakeMembershipPort("active")
    anterior = service.membership_port()
    service.set_membership_port(doble)
    try:
        yield doble
    finally:
        service.set_membership_port(anterior)
