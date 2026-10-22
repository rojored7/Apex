"""`role_allowed`, `require_role` y `current_user` con un PrincipalLoader doble (US-034 T8, T10)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from itertools import combinations
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.clock import FrozenClock, reset_clock, set_clock
from app.core.config import Settings
from app.core.context import current_actor
from app.core.crypto.keyring import Keyring
from app.core.security import (
    ROLES,
    JwtKeys,
    Principal,
    configure_jwt,
    create_access_token,
    generate_jwt_keypair_pem,
    register_principal_loader,
    require_role,
    role_allowed,
)
from app.main import API_PREFIX, create_app
from tests.core._principal_double import principal_double
from tests.core._routes import router

T0 = datetime(2026, 10, 21, 15, 0, 0, tzinfo=UTC)
# int=1 es SYSTEM_USER_ID: los usuarios de prueba empiezan en 101.
ADMIN, COACH, MEMBER, BAJA = UUID(int=101), UUID(int=102), UUID(int=103), UUID(int=104)
SYSTEM = UUID("00000000-0000-0000-0000-000000000001")


def test_role_allowed_tabla_completa() -> None:
    for n in (1, 2, 3):
        for permitidos in combinations(ROLES, n):
            for rol in ROLES:
                assert role_allowed(rol, frozenset(permitidos)) is (rol in permitidos)  # type: ignore[arg-type]


def test_require_role_valida_al_definir() -> None:
    with pytest.raises(ValueError, match="rol"):
        require_role()
    with pytest.raises(ValueError, match="root"):
        require_role("root")  # type: ignore[arg-type]
    dep = require_role("admin", "coach")
    assert dep.__apex_roles__ == frozenset({"admin", "coach"})  # type: ignore[attr-defined]


@pytest.fixture
async def app(settings_prueba: Settings) -> AsyncIterator[FastAPI]:
    principal_double.reset()
    principal_double.usuarios.update(
        {
            ADMIN: Principal(ADMIN, "admin", None),
            COACH: Principal(COACH, "coach", None),
            MEMBER: Principal(MEMBER, "member", UUID(int=30)),
            BAJA: None,
        }
    )
    aplicacion = create_app(settings_prueba, run_migrations_on_startup=False)
    register_principal_loader(principal_double)  # create_app importa auth, que registra el real
    aplicacion.include_router(router, prefix=API_PREFIX)
    token_reloj = set_clock(FrozenClock(T0))
    try:
        async with aplicacion.router.lifespan_context(aplicacion):
            yield aplicacion
    finally:
        reset_clock(token_reloj)
        principal_double.reset()


def _token(user_id: UUID, role: str, *, en: datetime = T0, member_id: UUID | None = None) -> str:
    return create_access_token(user_id, role, member_id, FrozenClock(en))  # type: ignore[arg-type]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _get(
    app: FastAPI, ruta: str, headers: dict[str, str] | None = None
) -> tuple[int, dict, dict]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"{API_PREFIX}/_t/{ruta}", headers=headers or {})
    return r.status_code, r.json(), dict(r.headers)


async def test_admin_entra_y_coach_recibe_403(app: FastAPI) -> None:
    status, cuerpo, _ = await _get(app, "admin", _auth(_token(ADMIN, "admin")))
    assert status == 200 and cuerpo["role"] == "admin"
    status, cuerpo, _ = await _get(app, "admin", _auth(_token(COACH, "coach")))
    assert status == 403 and cuerpo["error"]["code"] == "forbidden"
    assert "coach" not in cuerpo["error"]["message"]


async def test_staff_admite_admin_y_coach_pero_no_member(app: FastAPI) -> None:
    assert (await _get(app, "staff", _auth(_token(COACH, "coach"))))[0] == 200
    assert (await _get(app, "staff", _auth(_token(ADMIN, "admin"))))[0] == 200
    status, cuerpo, _ = await _get(app, "staff", _auth(_token(MEMBER, "member")))
    assert status == 403 and cuerpo["error"]["code"] == "forbidden"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic xxx"},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer a b"},
    ],
    ids=["sin-cabecera", "basic", "bearer-vacio", "dos-tokens"],
)
async def test_sin_token_valido_401_unauthorized(app: FastAPI, headers: dict[str, str]) -> None:
    status, cuerpo, resp = await _get(app, "admin", headers)
    assert status == 401 and cuerpo["error"]["code"] == "unauthorized"
    assert resp["www-authenticate"] == "Bearer"


async def test_token_vencido_401_token_expired(app: FastAPI) -> None:
    status, cuerpo, resp = await _get(
        app, "admin", _auth(_token(ADMIN, "admin", en=T0 - timedelta(minutes=20)))
    )
    assert status == 401 and cuerpo["error"]["code"] == "token_expired"
    assert resp["www-authenticate"] == "Bearer"


async def test_otra_llave_system_user_y_usuarios_sin_acceso(app: FastAPI) -> None:
    privada, publica = generate_jwt_keypair_pem()
    original_keys = app.state.settings
    configure_jwt(JwtKeys(privada, publica))
    ajeno = _token(ADMIN, "admin")
    from app.core.security import configure_security

    configure_security(original_keys)
    assert (await _get(app, "admin", _auth(ajeno)))[1]["error"]["code"] == "unauthorized"

    status, cuerpo, _ = await _get(app, "admin", _auth(_token(SYSTEM, "admin")))
    assert status == 401 and cuerpo["error"]["code"] == "unauthorized"
    assert SYSTEM not in principal_double.llamadas  # rechazado antes de ir a la base

    inexistente = await _get(app, "admin", _auth(_token(uuid4(), "admin")))
    baja = await _get(app, "admin", _auth(_token(BAJA, "admin")))
    assert inexistente[0] == baja[0] == 401
    assert inexistente[1] == baja[1]  # cuerpos idénticos: no se revela por qué


async def test_el_rol_vigente_manda_sobre_el_claim(app: FastAPI) -> None:
    principal_double.usuarios[COACH] = Principal(COACH, "coach", None)
    status, _, _ = await _get(app, "admin", _auth(_token(COACH, "admin")))  # claim dice admin
    assert status == 403


async def test_actor_visible_en_el_handler_y_limpio_despues(app: FastAPI) -> None:
    token = current_actor.set(None)
    try:
        status, cuerpo, _ = await _get(
            app, "actor", _auth(_token(MEMBER, "member", member_id=UUID(int=30)))
        )
        assert status == 200
        assert cuerpo["actor"] == str(MEMBER) and cuerpo["member_id"] == str(UUID(int=30))
        assert current_actor.get() is None
    finally:
        current_actor.reset(token)


async def test_dos_peticiones_concurrentes_no_mezclan_actores(app: FastAPI) -> None:
    async def pedir(user_id: UUID, role: str) -> str:
        _, cuerpo, _ = await _get(app, "actor", _auth(_token(user_id, role)))
        return str(cuerpo["actor"])

    resultados = await asyncio.gather(
        *(pedir(ADMIN, "admin") if i % 2 else pedir(COACH, "coach") for i in range(10))
    )
    assert resultados == [str(COACH) if i % 2 == 0 else str(ADMIN) for i in range(10)]


# S2-B2 · S2-D11 (M-3 del Sprint 1) y S2-D37 (H-3) ----------------------------------------


class _EspiaKeyring:
    """Cuenta las llamadas a `Keyring.refresh_if_stale` (lo que hace `refresh_current`)."""

    def __init__(self) -> None:
        self.llamadas = 0

    def instalar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        original = Keyring.refresh_if_stale
        espia = self

        async def contar(keyring: Keyring, session: object, provider: object) -> bool:
            espia.llamadas += 1
            return await original(keyring, session, provider)  # type: ignore[arg-type]

        monkeypatch.setattr(Keyring, "refresh_if_stale", contar)


async def test_refresh_current_solo_tras_un_token_valido(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    espia = _EspiaKeyring()
    espia.instalar(monkeypatch)
    assert (await _get(app, "admin", {}))[0] == 401
    assert (await _get(app, "admin", {"Authorization": "Bearer basura"}))[0] == 401
    vencido = _token(ADMIN, "admin", en=T0 - timedelta(minutes=20))
    assert (await _get(app, "admin", _auth(vencido)))[0] == 401
    assert (await _get(app, "admin", _auth(_token(SYSTEM, "admin"))))[0] == 401
    assert (await _get(app, "admin", _auth(_token(BAJA, "admin"))))[0] == 401
    assert espia.llamadas == 0, "ningún token inválido abre el keyring"
    assert (await _get(app, "admin", _auth(_token(ADMIN, "admin"))))[0] == 200
    assert espia.llamadas == 1, "un token válido refresca el keyring una vez"


async def test_las_rutas_publicas_no_tocan_el_keyring(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, sleeper_nulo: object
) -> None:
    """S2-D11: se quita la dependencia global de `include_module_routers`; login y refresh
    no abren el keyring."""
    espia = _EspiaKeyring()
    espia.instalar(monkeypatch)
    origen = {"Origin": "http://localhost"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        login = await c.post(
            f"{API_PREFIX}/auth/login",
            json={"email": "nadie@test.apex", "password": "Zanahoria-Lunar-42x"},
            headers=origen,
        )
        refresh = await c.post(f"{API_PREFIX}/auth/refresh", headers=origen)
    assert login.status_code == 401 and login.json()["error"]["code"] == "invalid_credentials"
    assert refresh.status_code == 401 and refresh.json()["error"]["code"] == "invalid_refresh"
    assert espia.llamadas == 0


async def test_access_emitido_antes_de_tokens_valid_after_da_401_unauthorized(
    app: FastAPI,
) -> None:
    """H-3: `iat < tokens_valid_after` → 401 `unauthorized` (no `token_expired`); el `iat`
    igual o posterior pasa. `tokens_valid_after` va truncado a segundos (E8)."""
    corte = T0 + timedelta(seconds=1)
    principal_double.usuarios[ADMIN] = Principal(ADMIN, "admin", None, tokens_valid_after=corte)
    status, cuerpo, resp = await _get(app, "admin", _auth(_token(ADMIN, "admin", en=T0)))
    assert status == 401 and cuerpo["error"]["code"] == "unauthorized"
    assert resp["www-authenticate"] == "Bearer"
    mismo_segundo = _token(ADMIN, "admin", en=corte + timedelta(milliseconds=900))
    assert (await _get(app, "admin", _auth(mismo_segundo)))[0] == 200
    assert (await _get(app, "admin", _auth(_token(ADMIN, "admin", en=corte))))[0] == 200


def test_principal_lleva_los_campos_nuevos_con_defaults() -> None:
    """E8: construcción posicional intacta; los campos nuevos tienen valor por defecto."""
    principal = Principal(ADMIN, "admin", None)
    assert principal.must_change_password is False
    assert principal.tokens_valid_after is None
