"""Fixtures de `tests/payments` (plan del Sprint 3, sección 2, bloque B3; D1).

- `payments_service` se importa al nivel del módulo (blueprint, reglas de pruebas 2):
  `restaurar_bus` restaura el bus al terminar cada prueba y una suscripción hecha por un import
  perezoso dentro de una prueba se perdería.
- `gate_doble` (opt-in, nunca autouse): registra un `GateDoble` (`_apoyo.py`) como
  `MembershipGate` y al salir restaura el gate que hubiera. No lo usan la prueba de router de
  `POST /memberships/{id}/payments` ni `test_gates_registered` (B4), que necesitan el gate real.
- `bus_confirmado`: el de `tests/memberships/conftest.py` (llaves del bus con commit real para las
  pruebas con `dos_sesiones`).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.modules.payments import service as payments_service  # noqa: F401
from tests.memberships.conftest import bus_confirmado  # noqa: F401
from tests.payments._apoyo import GateDoble, gate_registrado


@pytest.fixture
def gate_doble() -> Iterator[GateDoble]:
    with gate_registrado(GateDoble()) as doble:
        yield doble
