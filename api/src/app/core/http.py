"""Dependencias HTTP compartidas por los routers (revisión Python M6).

- `no_store`: `Cache-Control: no-store` en la respuesta. Va en toda ruta con rol (las
  respuestas con sesión llevan datos de personas o de configuración) y en las de sesión de
  `auth`; la prueba `tests/architecture/test_no_store_routes.py` lo exige. Nginx también lo pone
  en `/api/`, pero el api no depende del borde. Antes vivía en `auth/cookies.py` (privado de
  `auth`), por eso socios y planes no lo llevaban.

Solo importa FastAPI; ningún módulo de negocio.
"""

from __future__ import annotations

from typing import Final

from fastapi import Response

NO_STORE: Final = "no-store"


async def no_store(response: Response) -> None:
    """Dependencia: `dependencies=[Depends(no_store)]` en la ruta o en el `APIRouter`."""
    response.headers["Cache-Control"] = NO_STORE
