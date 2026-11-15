"""La cubeta `tv` se cuenta por token, no por IP (S8-D33; L4 de la revisión de la Wave 0).

`rate_limits_from` lista `tv` junto a las cubetas por IP porque ahí vive su tope (`TV_TOKEN_LIMIT`),
pero `rate_limit("tv")` la contaría por IP (`store_for("ip")`) y un gimnasio entero detrás de una
sola IP agotaría el cupo de la TV. C2 usa `enforce(..., kind="account")` con
`hash_opaque_token(token)[:16]`. Ninguna ruta puede llevar la marca `__apex_rate_limit__ == "tv"`.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant

from app.core.config import Settings
from app.core.ratelimit import rate_limit
from app.core.security import effective_routes
from app.main import create_app

CUBETA_DE_LA_TV = "tv"


def _marcas(dependant: Dependant) -> Iterable[str]:
    for dep in dependant.dependencies:
        marca = getattr(dep.call, "__apex_rate_limit__", None)
        if marca:
            yield marca
        yield from _marcas(dep)


def rutas_con_cubeta(app: FastAPI, cubeta: str) -> list[str]:
    """Rutas efectivas cuyo árbol de dependencias lleva `rate_limit(<cubeta>)`."""
    app.openapi()
    return sorted(
        f"{sorted(ruta.methods)} {ruta.path}"
        for ruta in effective_routes(app)[0]
        if cubeta in set(_marcas(ruta.dependant))
    )


def test_el_control_detecta_una_ruta_con_rate_limit_tv() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/mala", dependencies=[Depends(rate_limit(CUBETA_DE_LA_TV))])
    async def mala() -> None: ...

    @router.get("/buena", dependencies=[Depends(rate_limit("login"))])
    async def buena() -> None: ...

    app.include_router(router)
    assert rutas_con_cubeta(app, CUBETA_DE_LA_TV) == ["['GET'] /mala"]


def test_ninguna_ruta_real_usa_rate_limit_tv(settings_prueba: Settings) -> None:
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    assert rutas_con_cubeta(app, CUBETA_DE_LA_TV) == []
