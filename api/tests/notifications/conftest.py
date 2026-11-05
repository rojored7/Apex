"""Fixtures de `tests/notifications` (S5-B7). # Rojo B7

`listo`: el bus de criptografía con llaves (`bus_listo`) y el reloj congelado en `T0`
(2026-10-21 10:00 en Bogotá). Los socios de las pruebas de avisos se cifran y los avisos se
generan o se leen con ese "hoy".
"""

from __future__ import annotations

import pytest

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring


@pytest.fixture
def listo(bus_listo: Keyring, reloj: FrozenClock) -> Keyring:
    return bus_listo


from tests.members.conftest import bus_confirmado  # noqa: E402,F401  (S5-D223: llaves con commit real)
