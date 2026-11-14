"""Eventos de `classes` (S7-D20). Vacío en A2: las franjas no emiten eventos (US-155).

`SessionGenerated` y `SessionCancelled` llegan con B1 y B2; `MemberCheckedIn` y `AttendanceRemoved`
con C1 y C3 (siempre sin datos personales ni texto libre). Se exportan desde `service.py`.
"""

from __future__ import annotations
