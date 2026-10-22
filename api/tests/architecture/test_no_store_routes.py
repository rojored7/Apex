"""Toda ruta autenticada responde `Cache-Control: no-store` (revisión Python M6).

Las respuestas con sesión llevan datos de personas (correos, nombres, máscaras de documento y
teléfono) o de configuración; ningún caché intermedio ni el del navegador debe guardarlas. Nginx
ya pone `no-store` en `/api/`, pero el api no depende del borde: la dependencia `core.http.
no_store` va en cada ruta con rol (las que piden `require_role`). Se revisa sobre el árbol de
dependencias efectivo de `create_app()` y, por HTTP, en `GET /members` y `GET /plans`.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi.dependencies.models import Dependant
from httpx import AsyncClient

from app.core.config import Settings
from app.core.http import no_store
from app.core.security import effective_routes, route_has_role_dependency
from app.main import create_app
from tests.conftest import Cabeceras, CrearUsuario


def _nodos(dependant: Dependant) -> Iterator[Dependant]:
    yield dependant
    for hijo in dependant.dependencies:
        yield from _nodos(hijo)


def test_toda_ruta_con_rol_lleva_no_store(settings_prueba: Settings) -> None:
    rutas, _ = effective_routes(create_app(settings_prueba, run_migrations_on_startup=False))
    con_rol = [r for r in rutas if route_has_role_dependency(r)]
    assert len(con_rol) >= 20, len(con_rol)
    sin = [
        f"{sorted(r.methods)} {r.path}"
        for r in con_rol
        if not any(n.call is no_store for n in _nodos(r.dependant))
    ]
    assert sin == [], "\n".join(sin)


async def test_members_y_plans_responden_no_store(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    for ruta in ("/api/v1/members", "/api/v1/plans"):
        r = await app_http.get(ruta, headers=cabeceras(admin))
        assert r.status_code == 200, (ruta, r.text)
        assert r.headers["cache-control"] == "no-store", ruta
