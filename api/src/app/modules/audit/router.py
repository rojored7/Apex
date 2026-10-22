"""Router del módulo `audit` (S2-B6, decisión 21): vacío en v0.1.

Existe para que `audit` sea un módulo completo de `MODULES` (riesgo 6.10); las rutas de
consulta y verificación de la cadena llegan con EP-17.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
