"""Fixtures de `tests/dashboard` (plan del Sprint 4A, sección 2, bloque B8).

- `dashboard_service` se importa al nivel del módulo (como `audit_service` en B3): importa los
  services que compone (gate de pagos y suscripciones de `memberships` en el bus) antes de la
  foto de `restaurar_bus`.
- `sin_cache_de_resumen`: el autouse de `tests/memberships/conftest.py` (TTL 0; ninguna prueba ve
  el resumen de otra).
- `audit_chain_factory`, `ana` (admin, `ana.perez`) y `juan` (coach, `juan.rios`): los de
  `tests/audit/conftest.py` (la cadena vacía dentro de la transacción de la prueba; sus dos
  `insert` de `auth.users` son del sistema y nunca salen en el tablero).
"""

from __future__ import annotations

import app.modules.dashboard.service as dashboard_service
from tests.audit.conftest import (
    ana,
    audit_chain_factory,
    audit_service,
    juan,
    memberships_service,
    payments_service,
)
from tests.memberships.conftest import sin_cache_de_resumen

__all__ = [
    "ana",
    "audit_chain_factory",
    "audit_service",
    "dashboard_service",
    "juan",
    "memberships_service",
    "payments_service",
    "sin_cache_de_resumen",
]
