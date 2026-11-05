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


def test_el_router_de_notifications_lleva_no_store_en_el_router() -> None:
    """S5-B6: las respuestas de plantillas y reglas llevan `Cache-Control: no-store` por la
    dependencia del `APIRouter` (como `audit`), no ruta por ruta."""
    from app.modules.notifications.router import router

    assert any(d.dependency is no_store for d in router.dependencies)


def test_el_recibo_pdf_lleva_no_store(settings_prueba: Settings) -> None:
    """S5-B11 (US-137, S5-D40): la ruta del recibo existe, tiene rol y lleva `no_store`
    (Rojo B11)."""
    rutas, _ = effective_routes(create_app(settings_prueba, run_migrations_on_startup=False))
    recibo = [r for r in rutas if r.path.endswith("/payments/{payment_id}/receipt.pdf")]
    assert len(recibo) == 1
    assert route_has_role_dependency(recibo[0])
    assert any(n.call is no_store for n in _nodos(recibo[0].dependant))


def test_las_dos_exportaciones_tienen_rol_y_no_store(settings_prueba: Settings) -> None:
    """S5-B12 (US-138, US-139, S5-D41): `GET /members/export` y `GET /payments/export` existen,
    exigen rol y llevan la dependencia `no_store` (Rojo B12)."""
    rutas, _ = effective_routes(create_app(settings_prueba, run_migrations_on_startup=False))
    for sufijo in ("/members/export", "/payments/export"):
        halladas = [r for r in rutas if r.path.endswith(sufijo)]
        assert len(halladas) == 1, sufijo
        assert route_has_role_dependency(halladas[0]), sufijo
        assert any(n.call is no_store for n in _nodos(halladas[0].dependant)), sufijo
