"""Forma de las rutas de auth y usuarios (S2-B4; S2-D35/H-1, S2-D47, L-12, N-12).

Nace en B4. Manda la revisión de seguridad sobre el blueprint: las rutas públicas de auth son
exactamente `login`, `refresh`, `logout` (por la cookie, H-1), `forgot` y `reset`, las cinco con
la marca `__apex_rate_limit__` de su propio bucket. Toda ruta bajo `/api/v1/users` exige
exactamente `{"admin"}` (marca `__apex_roles__` de `require_role`); `me` y `me/password`
admiten los tres roles. No existe ninguna ruta `/activation-link` (N-12) ni `/auth/activate`
(S2-D47). Las marcas se leen del árbol de dependencias de las rutas efectivas
(`core.security.effective_routes`), igual que `test_every_route_has_role.py`.
S2-B5 suma las seis rutas del ciclo de vida: la lista bajo `/api/v1/users` es exacta
(`RUTAS_USERS`) y todas llevan `no_store`.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant

from app.core.config import Settings
from app.core.http import no_store
from app.core.security import RouteInfo, effective_routes, route_has_role_dependency
from app.main import create_app
from app.modules.auth.cookies import require_same_origin

AUTH = "/api/v1/auth/"
USERS = "/api/v1/users"
PUBLICAS_AUTH = {
    ("POST", "/api/v1/auth/login"): "login",
    ("POST", "/api/v1/auth/refresh"): "refresh",
    ("POST", "/api/v1/auth/logout"): "logout",
    ("POST", "/api/v1/auth/forgot"): "forgot",
    ("POST", "/api/v1/auth/reset"): "reset",
}
TRES_ROLES = frozenset({"admin", "coach", "member"})


@pytest.fixture
def app(settings_prueba: Settings) -> FastAPI:
    aplicacion = create_app(settings_prueba, run_migrations_on_startup=False)
    aplicacion.openapi()  # fuerza la inclusión perezosa de los routers
    return aplicacion


def _calls(dependant: Dependant) -> Iterator[object]:
    for dep in dependant.dependencies:
        yield dep.call
        yield from _calls(dep)


def _marcas(ruta: RouteInfo, marca: str) -> set[object]:
    return {getattr(c, marca) for c in _calls(ruta.dependant) if getattr(c, marca, None)}


def _roles(ruta: RouteInfo) -> set[frozenset[str]]:
    return {frozenset(r) for r in _marcas(ruta, "__apex_roles__")}


def _pares(app: FastAPI) -> dict[tuple[str, str], RouteInfo]:
    return {
        (metodo, ruta.path): ruta
        for ruta in effective_routes(app)[0]
        for metodo in ruta.methods - {"HEAD", "OPTIONS"}
    }


def test_ninguna_ruta_termina_en_activation_link_ni_existe_activate(app: FastAPI) -> None:
    rutas = {path for _, path in _pares(app)}
    assert not [r for r in rutas if r.rstrip("/").endswith("/activation-link")]
    assert "/api/v1/auth/activate" not in rutas


def test_las_publicas_de_auth_son_exactamente_las_cinco(app: FastAPI) -> None:
    publicas = {
        par
        for par, ruta in _pares(app).items()
        if par[1].startswith(AUTH) and not route_has_role_dependency(ruta)
    }
    assert publicas == set(PUBLICAS_AUTH)


def test_las_cinco_publicas_llevan_su_propio_rate_limit(app: FastAPI) -> None:
    pares = _pares(app)
    for par, bucket in PUBLICAS_AUTH.items():
        assert par in pares, par
        assert bucket in _marcas(pares[par], "__apex_rate_limit__"), par


RUTAS_USERS = {
    ("GET", USERS),
    ("POST", USERS),
    ("POST", f"{USERS}/{{user_id}}/resend-link"),
    # S2-B5 · ciclo de vida del usuario (US-049, US-050, US-051).
    ("GET", f"{USERS}/{{user_id}}"),
    ("PATCH", f"{USERS}/{{user_id}}"),
    ("DELETE", f"{USERS}/{{user_id}}"),
    ("POST", f"{USERS}/{{user_id}}/lock"),
    ("POST", f"{USERS}/{{user_id}}/unlock"),
    ("POST", f"{USERS}/{{user_id}}/revoke-sessions"),
}


def test_las_rutas_bajo_users_son_exactamente_las_del_plan(app: FastAPI) -> None:
    bajo_users = {par for par in _pares(app) if par[1].startswith(USERS)}
    assert bajo_users == RUTAS_USERS


def test_toda_ruta_bajo_users_exige_exactamente_admin(app: FastAPI) -> None:
    pares = _pares(app)
    bajo_users = {par: r for par, r in pares.items() if par[1].startswith(USERS)}
    assert RUTAS_USERS <= set(bajo_users)
    for par, ruta in bajo_users.items():
        assert _roles(ruta) == {frozenset({"admin"})}, par


def test_las_rutas_de_ciclo_de_vida_no_se_cachean(app: FastAPI) -> None:
    pares = _pares(app)
    for par in RUTAS_USERS:
        assert no_store in set(_calls(pares[par].dependant)), par


def test_logout_es_publico_por_cookie_con_origen(app: FastAPI) -> None:
    ruta = _pares(app)[("POST", "/api/v1/auth/logout")]
    assert not route_has_role_dependency(ruta)
    assert require_same_origin in set(_calls(ruta.dependant))


@pytest.mark.parametrize("par", [("GET", "/api/v1/auth/me"), ("POST", "/api/v1/auth/me/password")])
def test_me_y_me_password_admiten_los_tres_roles(app: FastAPI, par: tuple[str, str]) -> None:
    ruta = _pares(app)[par]
    assert _roles(ruta) == {TRES_ROLES}
