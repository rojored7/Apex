"""El modo quiosco es lista blanca (S7-C4, S7-D41, punto 5).

Con la marca `kiosk` en el access, `current_user` rechaza con 403 `kiosk_mode` TODA ruta que no
esté en `KIOSK_ALLOWED_ROUTES` (defecto: negar). Esta prueba recorre las rutas reales de la app:
- cada entrada de la lista existe, exige rol y no es una de las rutas sensibles conocidas;
- cada ruta con rol que NO está en la lista da 403 `kiosk_mode` con un access con la marca;
- las de la lista no dan `kiosk_mode`.
Una ruta nueva queda bloqueada en el quiosco sin tocar nada; abrirla exige editar la lista.
"""

from __future__ import annotations

import re
from uuid import uuid4

from fastapi import FastAPI
from httpx import AsyncClient

from app.core.clock import FrozenClock
from app.core.security import (
    KIOSK_ALLOWED_ROUTES,
    PUBLIC_ROUTES,
    create_access_token,
    effective_routes,
    route_has_role_dependency,
)
from tests.auth._sesion import ORIGEN
from tests.conftest import CrearUsuario

API = "/api/v1"
SENSIBLES = frozenset(
    {
        ("POST", f"{API}/members/{{member_id}}/reveal"),
        ("POST", f"{API}/notifications/{{notification_id}}/wa-link"),
        ("GET", f"{API}/members/export"),
        ("GET", f"{API}/payments/export"),
        ("GET", f"{API}/payments/{{payment_id}}/receipt.pdf"),
        ("GET", f"{API}/members/{{member_id}}"),
        ("GET", f"{API}/members/{{member_id}}/attachments"),
        ("POST", f"{API}/members/{{member_id}}/attachments"),
        ("GET", f"{API}/users"),
        ("GET", f"{API}/audit"),
        ("GET", f"{API}/crypto/keys"),
        ("POST", f"{API}/auth/me/password"),
        ("POST", f"{API}/memberships/{{membership_id}}/payments"),
    }
)


def _rutas(app: FastAPI) -> set[tuple[str, str]]:
    app.openapi()
    return {
        (metodo, ruta.path)
        for ruta in effective_routes(app)[0]
        if route_has_role_dependency(ruta)
        for metodo in ruta.methods
        if metodo not in {"HEAD", "OPTIONS"}
    }


async def test_la_lista_blanca_existe_exige_rol_y_no_abre_nada_sensible(
    api_prueba: FastAPI,
) -> None:
    rutas = _rutas(api_prueba)
    assert KIOSK_ALLOWED_ROUTES <= rutas, sorted(KIOSK_ALLOWED_ROUTES - rutas)
    assert KIOSK_ALLOWED_ROUTES.isdisjoint(PUBLIC_ROUTES)
    assert KIOSK_ALLOWED_ROUTES.isdisjoint(SENSIBLES)
    assert SENSIBLES <= rutas, sorted(SENSIBLES - rutas)


def test_la_lista_blanca_es_la_del_checkin_y_los_resultados() -> None:
    assert KIOSK_ALLOWED_ROUTES == frozenset(
        {
            ("GET", f"{API}/auth/me"),
            ("POST", f"{API}/auth/kiosk"),
            ("POST", f"{API}/auth/kiosk/exit"),
            ("GET", f"{API}/class-sessions"),
            ("GET", f"{API}/class-sessions/{{session_id}}"),
            ("GET", f"{API}/attendance"),
            ("POST", f"{API}/attendance"),
            ("DELETE", f"{API}/attendance/{{attendance_id}}"),
            ("GET", f"{API}/members"),
            ("GET", f"{API}/attachments/{{attachment_id}}"),
            ("GET", f"{API}/class-sessions/{{session_id}}/attendance"),
            ("PUT", f"{API}/results"),
        }
    )


CON_VENTANA = frozenset(
    {
        ("GET", f"{API}/class-sessions/{{session_id}}"),
        ("POST", f"{API}/attendance"),
        ("GET", f"{API}/class-sessions/{{session_id}}/attendance"),
    }
)


def _concreta(plantilla: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda _: str(uuid4()), plantilla)


async def test_toda_ruta_fuera_de_la_lista_da_403_kiosk_mode_con_la_marca(
    app_http: AsyncClient, api_prueba: FastAPI, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    kiosk = create_access_token(admin.id, "admin", None, reloj, kiosk=True)
    cabeceras = {"Authorization": f"Bearer {kiosk}", "Origin": ORIGEN}
    fallos: list[str] = []
    for metodo, plantilla in sorted(_rutas(api_prueba) - KIOSK_ALLOWED_ROUTES):
        r = await app_http.request(metodo, _concreta(plantilla), headers=cabeceras, json={})
        codigo = r.json().get("error", {}).get("code") if r.status_code >= 400 else None
        if r.status_code != 403 or codigo != "kiosk_mode":
            fallos.append(f"{metodo} {plantilla} -> {r.status_code} {codigo}")
    assert fallos == []


async def test_las_rutas_de_la_lista_no_dan_kiosk_mode(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    kiosk = create_access_token(admin.id, "admin", None, reloj, kiosk=True)
    cabeceras = {"Authorization": f"Bearer {kiosk}", "Origin": ORIGEN}
    bloqueadas: list[str] = []
    for metodo, plantilla in sorted(KIOSK_ALLOWED_ROUTES):
        r = await app_http.request(metodo, _concreta(plantilla), headers=cabeceras, json={})
        if r.status_code == 403 and r.json().get("error", {}).get("code") == "kiosk_mode":
            # V7 (M-1): con una sesión inexistente la ventana hoy/ayer da 403 `kiosk_mode` con su
            # propio texto; no es el filtro general de la lista blanca.
            if (metodo, plantilla) in CON_VENTANA and "hoy o de ayer" in r.text:
                continue
            bloqueadas.append(f"{metodo} {plantilla}")
    assert bloqueadas == []


def test_el_prefijo_de_core_es_el_de_main() -> None:
    from app.core.security import API_V1_PREFIX
    from app.main import API_PREFIX

    assert API_V1_PREFIX == API_PREFIX
