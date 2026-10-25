"""Toda ruta publicada tiene rol o está en `PUBLIC_ROUTES` (US-035 T6; RN-15).

Con `ENV=production` no se publican `/docs`, `/redoc` ni `/openapi.json`. FastAPI incluye
los routers de los módulos de forma perezosa, así que se fuerza `app.openapi()` antes de
recorrer `app.routes`.
"""

from __future__ import annotations

from pathlib import Path

from app.cli import key_paths_in
from app.core.config import Settings, load_settings
from app.core.security import PUBLIC_ROUTES, effective_routes, unprotected_routes
from app.main import create_app


def _produccion(tmp_path: Path, base: Settings, claves: Path) -> Settings:
    rutas = key_paths_in(claves)
    archivo = tmp_path / ".env.prod"
    archivo.write_text(
        f"DATABASE_URL={base.DATABASE_URL.get_secret_value()}\n"
        f"JWT_PRIVATE_KEY_PATH={rutas.jwt_private}\nCRYPTO_PROVIDER=local\n"
        f"CRYPTO_LOCAL_KEK_PATH={rutas.kek}\nCRYPTO_LOCAL_SIGNING_KEY_PATH={rutas.signing_key}\n"
        'UPLOADS_DIR=/data\nCORS_ORIGINS=["http://localhost"]\nENV=production\n'
        "COOKIE_SECURE=true\n",  # M-9 (E3): producción exige la cookie Secure
        encoding="utf-8",
    )
    return load_settings(env_file=archivo)


def test_toda_ruta_publicada_tiene_rol_o_es_publica(
    tmp_path: Path, settings_prueba: Settings, claves_prueba: Path
) -> None:
    app = create_app(
        _produccion(tmp_path, settings_prueba, claves_prueba), run_migrations_on_startup=False
    )
    app.openapi()
    sin_rol = unprotected_routes(app)
    assert sin_rol == [], "rutas sin rol ni lista blanca:\n" + "\n".join(sin_rol)


def test_las_publicas_registradas_lo_estan_con_el_mismo_metodo(
    tmp_path: Path, settings_prueba: Settings, claves_prueba: Path
) -> None:
    app = create_app(
        _produccion(tmp_path, settings_prueba, claves_prueba), run_migrations_on_startup=False
    )
    app.openapi()
    registradas = {
        (metodo, ruta.path) for ruta in effective_routes(app)[0] for metodo in ruta.methods
    }
    rutas_publicas = {ruta for _, ruta in PUBLIC_ROUTES}
    for metodo, ruta in registradas:
        if ruta in rutas_publicas:
            assert (metodo, ruta) in PUBLIC_ROUTES or metodo in {"HEAD", "OPTIONS"}, (
                f"{metodo} {ruta}"
            )
    assert {"/health", "/api/v1/health"} <= {r for _, r in registradas}


def test_la_lista_blanca_es_la_esperada() -> None:
    """S2-D35 (H-1): logout se autentica por la cookie y entra en la lista (7 → 8 rutas)."""
    assert PUBLIC_ROUTES == frozenset(
        {
            ("GET", "/health"),
            ("GET", "/api/v1/health"),
            ("POST", "/api/v1/auth/login"),
            ("POST", "/api/v1/auth/refresh"),
            ("POST", "/api/v1/auth/logout"),
            ("POST", "/api/v1/auth/forgot"),
            ("POST", "/api/v1/auth/reset"),
            ("GET", "/api/v1/tv/today"),
        }
    )
    assert len(PUBLIC_ROUTES) == 8


def test_login_refresh_y_logout_estan_registradas_sin_rol(
    tmp_path: Path, settings_prueba: Settings, claves_prueba: Path
) -> None:
    """S2-B2: las tres rutas de sesión existen por POST y ninguna exige Bearer (H-1)."""
    from app.core.security import route_has_role_dependency

    app = create_app(
        _produccion(tmp_path, settings_prueba, claves_prueba), run_migrations_on_startup=False
    )
    app.openapi()
    sesion = {
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
    }
    encontradas = {
        ruta.path: ruta
        for ruta in effective_routes(app)[0]
        if ruta.path in sesion and "POST" in ruta.methods
    }
    assert set(encontradas) == sesion
    assert not any(route_has_role_dependency(r) for r in encontradas.values())


def test_login_y_forgot_llevan_limite_de_intentos(
    tmp_path: Path, settings_prueba: Settings, claves_prueba: Path
) -> None:
    """US-036 T9 y L-12: cuando existan, las rutas públicas de auth deben tener `rate_limit`,
    cada una con su propio bucket (logout incluido, S2-D35)."""
    from app.core.security import _dependant_has

    app = create_app(
        _produccion(tmp_path, settings_prueba, claves_prueba), run_migrations_on_startup=False
    )
    app.openapi()
    objetivo = {
        "/api/v1/auth/login": "login",
        "/api/v1/auth/refresh": "refresh",
        "/api/v1/auth/logout": "logout",
        "/api/v1/auth/forgot": "forgot",
        "/api/v1/auth/reset": "reset",
    }
    vistas: set[str] = set()
    for ruta in effective_routes(app)[0]:
        if ruta.path in objetivo and "POST" in ruta.methods:
            assert _dependant_has(ruta.dependant, "__apex_rate_limit__"), ruta.path
            buckets = {
                getattr(dep.call, "__apex_rate_limit__", None)
                for dep in ruta.dependant.dependencies
            }
            assert objetivo[ruta.path] in buckets, (ruta.path, buckets)
            vistas.add(ruta.path)
    assert {"/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/logout"} <= vistas


def test_get_payments_methods_existe_y_exige_rol(
    tmp_path: Path, settings_prueba: Settings, claves_prueba: Path
) -> None:
    """S3-B3 (US-056): `GET /payments/methods` se publica con `StaffDep` (admin y coach) y no
    entra a `PUBLIC_ROUTES`; `POST /memberships/{membership_id}/payments` todavía no existe (nace
    en B4 con el gate real, E9)."""
    from app.core.security import route_has_role_dependency

    app = create_app(
        _produccion(tmp_path, settings_prueba, claves_prueba), run_migrations_on_startup=False
    )
    app.openapi()
    rutas = effective_routes(app)[0]
    metodos = [r for r in rutas if r.path == "/api/v1/payments/methods" and "GET" in r.methods]
    assert len(metodos) == 1
    assert route_has_role_dependency(metodos[0])
    assert ("GET", "/api/v1/payments/methods") not in PUBLIC_ROUTES
    pago = "/api/v1/memberships/{membership_id}/payments"
    assert not [r for r in rutas if r.path == pago]
