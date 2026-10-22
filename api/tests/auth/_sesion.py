"""Ayudas de las pruebas de sesión de S2-B2 (login, refresh y logout).

- `politica(**cambios)`: `AuthPolicy` con los valores por defecto de `Settings` (E5, S2-D10).
- `post_auth`: POST a una ruta de auth con `Origin` del front (S2-D38) y, si se pide, la cookie
  `apex_refresh` puesta a mano; vacía antes la jarra de cookies de httpx para que cada prueba
  diga exactamente qué cookie viaja.
- `cookie_de` y `set_cookie`: el valor de `apex_refresh` y la cabecera `Set-Cookie` en bruto.
- `EspiaArgon2`: cuenta las verificaciones de argon2 (reales y `dummy_verify`) envolviendo el
  hasher de `core/security`, sin depender de cómo importe el service (M-6).
"""

from __future__ import annotations

from datetime import timedelta
from http.cookies import SimpleCookie
from typing import Any

from httpx import AsyncClient, Response

from app.core import security
from app.modules.auth.rules import AuthPolicy

ORIGEN = "http://localhost"  # origen de FRONT_BASE_URL en `settings_prueba`
ORIGEN_AJENO = "http://evil.example"
COOKIE = "apex_refresh"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
IP_A = "203.0.113.9"
IP_A2 = "203.0.113.77"  # misma red /24 que IP_A
IP_B = "198.51.100.7"  # otra red /24


def politica(**cambios: Any) -> AuthPolicy:
    valores: dict[str, Any] = {
        "access_ttl_s": 900,
        "refresh_ttl": timedelta(days=7),
        "refresh_absolute_ttl": timedelta(days=30),
        "reuse_grace": timedelta(seconds=10),
        "account_limit": 10,
        "account_window_s": 900,
        "account_global_limit": 100,
        "account_global_window_s": 3600,
        "lock_after": 20,
        "min_duration_ms": 400,
    }
    valores.update(cambios)
    return AuthPolicy(**valores)


async def post_auth(
    cliente: AsyncClient,
    ruta: str,
    *,
    cookie: str | None = None,
    origin: str | None = ORIGEN,
    json: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    cliente.cookies.clear()
    cabeceras: dict[str, str] = {}
    if origin is not None:
        cabeceras["Origin"] = origin
    if cookie is not None:
        cabeceras["Cookie"] = f"{COOKIE}={cookie}"
    cabeceras.update(headers or {})
    return await cliente.post(ruta, json=json, headers=cabeceras)


def set_cookie(respuesta: Response) -> str:
    """Las cabeceras `Set-Cookie` de `apex_refresh`, unidas (vacío si no hay)."""
    return " || ".join(
        valor for valor in respuesta.headers.get_list("set-cookie") if valor.startswith(COOKIE)
    )


def cookie_de(respuesta: Response) -> str | None:
    """Valor de `apex_refresh` en la respuesta (o `None`); vacío si es un borrado."""
    crudo = set_cookie(respuesta)
    if not crudo:
        return None
    galleta: SimpleCookie = SimpleCookie()
    galleta.load(crudo.split(" || ")[0])
    return galleta[COOKIE].value if COOKIE in galleta else None


class EspiaArgon2:
    """Envuelve `security._hasher`: registra cada `verify` y si fue contra el hash ficticio.

    Se instala y se quita a mano (fixture `espia_argon2` de `tests/auth/conftest.py`) para
    restaurar el hasher antes de que `argon2_rapido` vuelva a los parámetros de producción.
    """

    def __init__(self) -> None:
        self.reales = 0
        self.ficticias = 0
        self._real: Any = None

    def instalar(self) -> None:
        self._real = security._hasher
        espia = self

        class _Envoltura:
            def __getattr__(self, nombre: str) -> Any:
                return getattr(espia._real, nombre)

            def verify(self, hash_: str, plain: str) -> Any:
                if hash_ == security._dummy_hash:
                    espia.ficticias += 1
                else:
                    espia.reales += 1
                return espia._real.verify(hash_, plain)

        security._hasher = _Envoltura()  # type: ignore[assignment]

    def quitar(self) -> None:
        if self._real is not None:
            security._hasher = self._real
            self._real = None

    def reiniciar(self) -> None:
        self.reales = 0
        self.ficticias = 0

    @property
    def total(self) -> int:
        return self.reales + self.ficticias
