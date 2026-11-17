"""Fixtures de `athletes`: llaves con commit real para las pruebas con dos conexiones (S9-A3)."""

from __future__ import annotations

from tests.athletes._apoyo_derivar import alertas  # noqa: F401  (sink de alertas capturadas)
from tests.members.conftest import bus_confirmado  # noqa: F401  (llaves con commit real)
