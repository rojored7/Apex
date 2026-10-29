"""Fixtures de `tests/plans` (nace en S4A-B7).

- `memberships_service` se importa al nivel del módulo (como `tests/memberships/conftest.py`):
  la baja, el conteo y las pruebas que venden usan `memberships.service` (su gate de pagos y sus
  suscripciones se registran al importarse, antes de la foto de `restaurar_bus`).
- `bus_confirmado`: el de `tests/memberships/conftest.py` (llaves con commit real), para las
  carreras con `dos_sesiones` que crean socios.
- `sin_cache_de_resumen`: el autouse de `tests/memberships/conftest.py` (las ventas de estas
  pruebas marcan el resumen; ninguna prueba ve el de otra).
"""

from __future__ import annotations

from app.modules.memberships import service as memberships_service  # noqa: F401
from tests.memberships.conftest import bus_confirmado, sin_cache_de_resumen

__all__ = ["bus_confirmado", "sin_cache_de_resumen"]
