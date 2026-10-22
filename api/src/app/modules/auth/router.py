"""Router de auth. Sin endpoints en el Sprint 1: login, refresh y cuentas llegan en EP-04
(Sprint 2). Existe para que `MODULES` incluya `auth` y su `service.py` registre el
`PrincipalLoader` al arrancar (US-034)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])
