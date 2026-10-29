"""Límite de intentos: función pura, IP real y dependencia por ruta (US-036 T7, T8)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from ipaddress import ip_network
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.clock import FrozenClock, reset_clock, set_clock
from app.core.errors import register_error_handlers
from app.core.ratelimit import SlidingWindowStore, allow, client_ip, rate_limit, reset_store

T0 = datetime(2026, 10, 21, 15, 0, 0, tzinfo=UTC)
CONFIANZA = [ip_network("10.0.0.0/8")]


# allow -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("marcas", "esperado"), [(0, True), (4, True), (5, False), (6, False)])
def test_allow_por_cantidad(marcas: int, esperado: bool) -> None:
    historia = [1000.0 + i for i in range(marcas)]
    permitido, _ = allow(historia, 1010.0, limit=5, window_s=60)
    assert permitido is esperado


def test_allow_ventana_deslizante_y_retry_after() -> None:
    ahora = 2000.0
    fuera = [ahora - 60.0] * 5  # justo en now - 60: fuera de la ventana
    assert allow(fuera, ahora)[0] is True
    dentro = [ahora - 59.999] * 5
    permitido, espera = allow(dentro, ahora)
    assert permitido is False and espera >= 1
    reciente = [ahora - 10.0, ahora - 5.0, ahora - 4.0, ahora - 3.0, ahora - 2.0]
    assert allow(reciente, ahora) == (False, 50)


# client_ip --------------------------------------------------------------------------------


def _request(host: str, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    scope = {"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (host, 1)}
    return Request(scope)


def test_client_ip_sin_proxy_ignora_la_cabecera() -> None:
    assert client_ip(_request("203.0.113.9"), []) == "203.0.113.9"
    assert client_ip(_request("203.0.113.9", "1.2.3.4"), []) == "203.0.113.9"
    assert client_ip(_request("203.0.113.9", "1.2.3.4"), CONFIANZA) == "203.0.113.9"


def test_client_ip_con_proxy_de_confianza() -> None:
    assert client_ip(_request("10.0.0.5", "1.2.3.4, 10.0.0.5"), CONFIANZA) == "1.2.3.4"
    assert client_ip(_request("10.0.0.5", "1.2.3.4"), CONFIANZA) == "1.2.3.4"
    assert client_ip(_request("10.0.0.5", "9.9.9.9, 1.2.3.4, 10.0.0.7"), CONFIANZA) == "1.2.3.4"


def test_client_ip_cabecera_mal_formada_o_vacia() -> None:
    assert client_ip(_request("10.0.0.5", "no-es-ip"), CONFIANZA) == "10.0.0.5"
    assert client_ip(_request("10.0.0.5", ""), CONFIANZA) == "10.0.0.5"
    assert client_ip(_request("10.0.0.5", "10.0.0.6"), CONFIANZA) == "10.0.0.5"


# store -------------------------------------------------------------------------------------


async def test_store_registra_procesados_y_no_los_rechazados() -> None:
    store = SlidingWindowStore(max_keys=2)
    clave = ("login", "1.1.1.1")
    for i in range(5):
        assert (await store.hit(clave, 100.0 + i, 5, 60))[0] is True
    assert (await store.hit(clave, 110.0, 5, 60)) == (False, 50)
    assert (await store.hit(clave, 160.0, 5, 60))[0] is True  # se libera 60 s tras el primero
    await store.hit(("login", "2.2.2.2"), 100.0, 5, 60)
    await store.hit(("login", "3.3.3.3"), 100.0, 5, 60)  # expulsa la clave más antigua
    assert len(store) == 2


# dependencia -------------------------------------------------------------------------------


@pytest.fixture
async def app() -> AsyncIterator[FastAPI]:
    reset_store()
    aplicacion = FastAPI()
    register_error_handlers(aplicacion)
    aplicacion.state.trusted_proxies = CONFIANZA

    @aplicacion.post("/login", dependencies=[Depends(rate_limit("login"))])
    async def login(email: Annotated[str, ""] = "") -> dict[str, str]:
        return {"ok": email}

    @aplicacion.post("/forgot", dependencies=[Depends(rate_limit("forgot"))])
    async def forgot() -> dict[str, str]:
        return {"ok": "forgot"}

    token = set_clock(FrozenClock(T0))
    try:
        yield aplicacion
    finally:
        reset_clock(token)
        reset_store()


def _cliente(app: FastAPI, ip: str = "10.1.1.1") -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app, client=(ip, 1234)), base_url="http://t")


async def test_sexto_intento_429_y_ventana_se_libera(app: FastAPI) -> None:
    async with _cliente(app) as c:
        for _ in range(5):
            assert (await c.post("/login")).status_code == 200
        r = await c.post("/login")
        assert r.status_code == 429
        assert r.json()["error"]["code"] == "rate_limited"
        assert int(r.headers["retry-after"]) >= 1
        assert "@" not in r.json()["error"]["message"]
        token = set_clock(FrozenClock(T0 + timedelta(seconds=61)))
        try:
            assert (await c.post("/login")).status_code == 200
        finally:
            reset_clock(token)


async def test_buckets_e_ips_independientes(app: FastAPI) -> None:
    async with _cliente(app) as c, _cliente(app, "10.1.1.2") as otro:
        for _ in range(5):
            await c.post("/login")
        assert (await c.post("/login")).status_code == 429
        assert (await c.post("/forgot")).status_code == 200
        assert (await otro.post("/login")).status_code == 200


async def test_cliente_no_confiable_no_rota_con_x_forwarded_for(app: FastAPI) -> None:
    async with _cliente(app, "203.0.113.7") as c:
        for i in range(5):
            await c.post("/login", headers={"X-Forwarded-For": f"1.2.3.{i}"})
        r = await c.post("/login", headers={"X-Forwarded-For": "1.2.3.99"})
        assert r.status_code == 429


async def test_el_429_es_identico_para_cualquier_correo(app: FastAPI) -> None:
    async with _cliente(app) as c:
        for _ in range(5):
            await c.post("/login", params={"email": "existe@apex.local"})
        a = await c.post("/login", params={"email": "existe@apex.local"})
        b = await c.post("/login", params={"email": "nadie@apex.local"})
        assert a.status_code == b.status_code == 429 and a.json() == b.json()


def test_la_dependencia_lleva_la_marca() -> None:
    assert rate_limit("login").__apex_rate_limit__ == "login"  # type: ignore[attr-defined]


# S2-B2 · M-2 del Sprint 1, H-4, L-11, L-12, E5 y E9 ------------------------------------


@pytest.mark.parametrize(
    ("ip", "esperada"),
    [
        ("203.0.113.9", "203.0.113.0/24"),
        ("203.0.113.250", "203.0.113.0/24"),
        ("198.51.100.7", "198.51.100.0/24"),
        ("2001:db8:1:2:aaaa:bbbb:cccc:dddd", "2001:db8:1:2::/64"),
        ("2001:db8:1:2::1", "2001:db8:1:2::/64"),
        ("2001:db8:1:3::1", "2001:db8:1:3::/64"),
        ("no-es-ip", "no-es-ip"),
    ],
)
def test_ip_bucket_key_red_24_y_64(ip: str, esperada: str) -> None:
    from app.core.ratelimit import ip_bucket_key

    assert ip_bucket_key(ip) == esperada


def test_ip_bucket_key_ipv4_exacta_para_el_limite_por_ip() -> None:
    """El límite por IP mantiene la IPv4 exacta (US-036); solo IPv6 se agrupa por /64."""
    from app.core.ratelimit import ip_bucket_key

    assert ip_bucket_key("10.1.1.1", ipv4_prefix=32) == "10.1.1.1/32"
    assert ip_bucket_key("10.1.1.2", ipv4_prefix=32) == "10.1.1.2/32"
    assert ip_bucket_key("2001:db8::1", ipv4_prefix=32) == "2001:db8::/64"


async def test_dos_ipv6_del_mismo_64_comparten_el_limite_por_ip(app: FastAPI) -> None:
    async with _cliente(app, "2001:db8:1:2::1") as a, _cliente(app, "2001:db8:1:2::ffff") as b:
        for _ in range(5):
            assert (await a.post("/login")).status_code == 200
        assert (await b.post("/login")).status_code == 429
    async with _cliente(app, "2001:db8:1:3::1") as otra_red:
        assert (await otra_red.post("/login")).status_code == 200


async def test_rate_limit_toma_el_tope_de_app_state(app: FastAPI) -> None:
    """E5: los topes salen de `Settings` vía `app.state.rate_limits` (`rate_limits_from`)."""
    app.state.rate_limits = {"login": (2, 60)}
    async with _cliente(app) as c:
        assert (await c.post("/login")).status_code == 200
        assert (await c.post("/login")).status_code == 200
        assert (await c.post("/login")).status_code == 429


def test_rate_limits_from_settings_por_defecto() -> None:
    from app.cli import export_settings
    from app.core.ratelimit import rate_limits_from

    assert rate_limits_from(export_settings()) == {
        "login": (5, 60),
        "refresh": (60, 60),
        "reset": (10, 60),
        "forgot": (5, 60),
        "logout": (30, 60),
    }


async def test_enforce_rechaza_al_superar_y_no_registra_el_rechazado() -> None:
    from app.core.errors import TooManyRequestsError
    from app.core.ratelimit import enforce

    token = set_clock(FrozenClock(T0))
    try:
        for _ in range(3):
            await enforce("login-account", "ana@apex.co|203.0.113.0/24", limit=3, window_s=900)
        with pytest.raises(TooManyRequestsError) as excinfo:
            await enforce("login-account", "ana@apex.co|203.0.113.0/24", limit=3, window_s=900)
        # Las tres marcas son de T0: la ventana se libera 900 s después.
        assert int(excinfo.value.headers["Retry-After"]) == 900
        await enforce("login-account", "ana@apex.co|198.51.100.0/24", limit=3, window_s=900)
    finally:
        reset_clock(token)


async def test_enforce_sin_count_solo_comprueba_y_record_suma() -> None:
    """H-4: se comprueba antes de argon2 sin sumar y solo el fallo suma (`record`)."""
    from app.core.errors import TooManyRequestsError
    from app.core.ratelimit import enforce, record

    token = set_clock(FrozenClock(T0))
    try:
        for _ in range(10):
            await enforce("login-account", "ana@apex.co", limit=2, window_s=900, count=False)
        await record("login-account", "ana@apex.co", window_s=900)
        await enforce("login-account", "ana@apex.co", limit=2, window_s=900, count=False)
        await record("login-account", "ana@apex.co", window_s=900)
        with pytest.raises(TooManyRequestsError):
            await enforce("login-account", "ana@apex.co", limit=2, window_s=900, count=False)
    finally:
        reset_clock(token)


async def test_enforce_no_escribe_la_clave_en_el_log(caplog: pytest.LogCaptureFixture) -> None:
    from app.core.errors import TooManyRequestsError
    from app.core.ratelimit import enforce

    token = set_clock(FrozenClock(T0))
    try:
        with caplog.at_level(logging.DEBUG, logger="app.ratelimit"):
            await enforce("login-account", "ana@apex.co|203.0.113.0/24", limit=1, window_s=900)
            with pytest.raises(TooManyRequestsError):
                await enforce("login-account", "ana@apex.co|203.0.113.0/24", limit=1, window_s=900)
    finally:
        reset_clock(token)
    registros = [r for r in caplog.records if r.name == "app.ratelimit"]
    assert registros, "el 429 se registra"
    assert getattr(registros[-1], "bucket", None) == "login-account"
    volcado = caplog.text + " ".join(str(r.__dict__) for r in registros)
    assert "ana@apex.co" not in volcado and "203.0.113" not in volcado


async def test_forget_borra_la_clave_y_sus_subclaves() -> None:
    from app.core.errors import TooManyRequestsError
    from app.core.ratelimit import enforce, forget, record

    token = set_clock(FrozenClock(T0))
    try:
        await record("login-account", "ana@apex.co|203.0.113.0/24", window_s=900)
        await record("login-account", "ana@apex.co|198.51.100.0/24", window_s=900)
        await record("login-account", "ana@apex.cox|203.0.113.0/24", window_s=900)
        await record("login-account-global", "ana@apex.co", window_s=3600, kind="account-global")
        assert await forget("login-account", "ana@apex.co") == 2
        assert await forget("login-account-global", "ana@apex.co", kind="account-global") == 1
        # El correo parecido no se toca: sigue en su tope de 1.
        with pytest.raises(TooManyRequestsError):
            await enforce(
                "login-account", "ana@apex.cox|203.0.113.0/24", limit=1, window_s=900, count=False
            )
        await enforce(
            "login-account", "ana@apex.co|203.0.113.0/24", limit=1, window_s=900, count=False
        )
    finally:
        reset_clock(token)


async def test_cada_tipo_de_clave_tiene_su_almacen_y_su_tope() -> None:
    """L-11: llenar el almacén de cuentas con correos no expulsa las claves por IP."""
    from app.core.ratelimit import (
        DEFAULT_MAX_KEYS,
        KEY_KINDS,
        configure_store_limits,
        enforce,
        store_for,
    )

    configure_store_limits({"ip": 2, "account": 3, "account-global": 3, "user": 3})
    token = set_clock(FrozenClock(T0))
    try:
        await enforce("login", "10.1.1.1/32", limit=5, window_s=60, kind="ip")
        await enforce("login", "10.1.1.2/32", limit=5, window_s=60, kind="ip")
        for i in range(10):
            await enforce("login-account", f"x{i}@apex.co", limit=5, window_s=900)
        assert len(store_for("account")) == 3
        assert len(store_for("ip")) == 2
        assert len(store_for("user")) == 0
        assert store_for("ip") is not store_for("account")
    finally:
        reset_clock(token)
        configure_store_limits(dict.fromkeys(KEY_KINDS, DEFAULT_MAX_KEYS))


async def test_la_expulsion_saca_la_clave_usada_hace_mas_tiempo() -> None:
    """L-11: tope lleno → sale la clave menos recientemente usada (OrderedDict, O(1))."""
    store = SlidingWindowStore(max_keys=3)
    for i, clave in enumerate(("a", "b", "c")):
        await store.hit(("login", clave), 100.0 + i, 5, 60)
    await store.hit(("login", "a"), 110.0, 5, 60)  # "a" vuelve a usarse
    await store.hit(("login", "d"), 111.0, 5, 60)  # expulsa "b", no "a"
    assert (await store.peek(("login", "a"), 112.0, 2, 60))[0] is False  # "a" conserva 2 marcas
    assert (await store.peek(("login", "b"), 112.0, 1, 60))[0] is True  # "b" volvió vacía
    assert len(store) == 3


def test_ip_bucket_key_trata_la_ipv4_mapeada_como_ipv4() -> None:
    """Revisión de seguridad de B2 (LOW-3): `::ffff:a.b.c.d` no colapsa en un solo /64."""
    from app.core.ratelimit import ip_bucket_key

    assert ip_bucket_key("::ffff:203.0.113.9") == "203.0.113.0/24"
    assert ip_bucket_key("::ffff:203.0.113.9", ipv4_prefix=32) == "203.0.113.9/32"
    assert ip_bucket_key("::ffff:198.51.100.7", ipv4_prefix=32) == "198.51.100.7/32"


async def test_reserve_es_atomica_y_release_devuelve_el_cupo() -> None:
    """Revisión Python M2: `reserve` comprueba y suma bajo el mismo candado; `release` quita la
    marca de esa reserva (y solo una); una marca ya ausente devuelve `False`."""
    import asyncio

    from app.core.errors import TooManyRequestsError
    from app.core.ratelimit import release, reserve

    token = set_clock(FrozenClock(T0))
    try:
        resultados = await asyncio.gather(
            *(reserve("login-account", "ana@apex.co", limit=3, window_s=900) for _ in range(10)),
            return_exceptions=True,
        )
        marcas = [r for r in resultados if isinstance(r, float)]
        assert len(marcas) == 3
        assert sum(isinstance(r, TooManyRequestsError) for r in resultados) == 7
        assert await release("login-account", "ana@apex.co", marcas[0]) is True
        await reserve("login-account", "ana@apex.co", limit=3, window_s=900)  # cupo devuelto
        with pytest.raises(TooManyRequestsError):
            await reserve("login-account", "ana@apex.co", limit=3, window_s=900)
        assert await release("login-account", "otra@apex.co", marcas[0]) is False
    finally:
        reset_clock(token)


# S3-W0-2 · topes por usuario (S3-D59, S3-D76; E10, E15) y `usage` (S3-D44) ----------------

USUARIO = UUID(int=501)
OTRO = UUID(int=502)
CATALOGO = {
    "members-write": (60, 60),
    "members-search": (60, 60),
    "members-detail": (120, 60),
    "members-reveal": (30, 60),
    "members-reveal-hour": (200, 3600),
    "members-reveal-day": (600, 86400),
    "memberships-write": (30, 60),
    "payments-write": (30, 60),
    "admin-write": (30, 60),
    # S4A-B3 (S4A-D45, S4A-D47, S4A-D65).
    "staff-read": (120, 60),
    "audit-verify": (3, 60),
    "audit-verify-hour": (20, 3600),
}


def _peticion(user_limits: dict[str, tuple[int, int]]) -> Request:
    """Una `Request` cuya app lleva `state.user_limits`, como la de `create_app` (E10)."""
    aplicacion = FastAPI()
    aplicacion.state.user_limits = user_limits
    return Request({"type": "http", "app": aplicacion, "headers": [], "client": ("10.1.1.1", 1)})


@pytest.fixture
def reloj_t0() -> Iterator[FrozenClock]:
    reloj = FrozenClock(T0)
    token = set_clock(reloj)
    try:
        yield reloj
    finally:
        reset_clock(token)


def test_user_limits_es_el_catalogo_del_plan() -> None:
    from app.core.ratelimit import PII_SEARCH_BUCKET, USER_LIMITS

    assert USER_LIMITS == CATALOGO
    assert PII_SEARCH_BUCKET == "members-search"
    assert PII_SEARCH_BUCKET in USER_LIMITS


def test_user_limits_from_con_los_valores_por_defecto_es_el_catalogo() -> None:
    from app.cli import export_settings
    from app.core.ratelimit import USER_LIMITS, user_limits_from

    assert user_limits_from(export_settings()) == USER_LIMITS


def test_user_limits_from_sigue_la_correspondencia_de_e15_y_conserva_las_ventanas() -> None:
    """E15: `USER_WRITE_*` alimenta `memberships-write` y `payments-write`;
    `USER_ADMIN_WRITE_*`, `admin-write`; las demás, una a una."""
    from app.cli import export_settings
    from app.core.ratelimit import user_limits_from

    ajustes = export_settings().model_copy(
        update={
            "USER_WRITE_LIMIT_PER_MIN": 11,
            "USER_ADMIN_WRITE_LIMIT_PER_MIN": 12,
            "USER_MEMBERS_WRITE_LIMIT_PER_MIN": 13,
            "USER_SEARCH_LIMIT_PER_MIN": 14,
            "USER_DETAIL_LIMIT_PER_MIN": 15,
            "USER_REVEAL_LIMIT_PER_MIN": 16,
            "USER_REVEAL_LIMIT_PER_HOUR": 17,
            "USER_REVEAL_LIMIT_PER_DAY": 18,
            "USER_READ_LIMIT_PER_MIN": 19,
            "USER_AUDIT_VERIFY_LIMIT_PER_MIN": 20,
            "USER_AUDIT_VERIFY_LIMIT_PER_HOUR": 21,
        }
    )
    assert user_limits_from(ajustes) == {
        "staff-read": (19, 60),
        "audit-verify": (20, 60),
        "audit-verify-hour": (21, 3600),
        "members-write": (13, 60),
        "members-search": (14, 60),
        "members-detail": (15, 60),
        "members-reveal": (16, 60),
        "members-reveal-hour": (17, 3600),
        "members-reveal-day": (18, 86400),
        "memberships-write": (11, 60),
        "payments-write": (11, 60),
        "admin-write": (12, 60),
    }


def test_user_limits_from_da_doce_cubetas_y_audit_verify_hour_conserva_su_ventana() -> None:
    """S4A-D65 (contradicción 1): el catálogo pasa de 9 a 12 cubetas; `audit-verify-hour` mide
    3.600 s aunque su tope venga de `Settings`."""
    from app.cli import export_settings
    from app.core.ratelimit import user_limits_from

    topes = user_limits_from(
        export_settings().model_copy(update={"USER_AUDIT_VERIFY_LIMIT_PER_HOUR": 7})
    )
    assert len(topes) == 12
    assert topes["audit-verify-hour"] == (7, 3600)
    assert topes["audit-verify"][1] == 60
    assert topes["staff-read"][1] == 60


async def test_la_cuarta_verificacion_del_minuto_da_429_y_las_lecturas_no_la_consumen(
    reloj_t0: FrozenClock,
) -> None:
    """S4A-D47 (M-3): `audit-verify` admite 3 por minuto y por usuario; `staff-read` es otra
    cubeta."""
    from app.core.errors import TooManyRequestsError
    from app.core.ratelimit import USER_LIMITS, enforce_user_limit

    peticion = _peticion(dict(USER_LIMITS))
    for _ in range(3):
        await enforce_user_limit(peticion, "audit-verify", USUARIO)
    with pytest.raises(TooManyRequestsError):
        await enforce_user_limit(peticion, "audit-verify", USUARIO)
    await enforce_user_limit(peticion, "staff-read", USUARIO)
    await enforce_user_limit(peticion, "audit-verify", OTRO)


async def test_enforce_user_limit_la_llamada_31_de_memberships_write_da_429(
    reloj_t0: FrozenClock,
) -> None:
    from app.core.errors import TooManyRequestsError
    from app.core.ratelimit import USER_LIMITS, enforce_user_limit

    peticion = _peticion(dict(USER_LIMITS))
    for _ in range(30):
        await enforce_user_limit(peticion, "memberships-write", USUARIO)
    with pytest.raises(TooManyRequestsError) as excinfo:
        await enforce_user_limit(peticion, "memberships-write", USUARIO)
    assert excinfo.value.status == 429 and excinfo.value.code == "rate_limited"
    assert int(excinfo.value.headers["Retry-After"]) == 60  # las 30 marcas son de T0
    # Otro usuario y otro bucket tienen su propio cupo.
    await enforce_user_limit(peticion, "memberships-write", OTRO)
    await enforce_user_limit(peticion, "payments-write", USUARIO)
    reloj_t0.advance(minutes=1)
    await enforce_user_limit(peticion, "memberships-write", USUARIO)  # la ventana se liberó


async def test_enforce_user_limit_cuenta_en_el_almacen_de_usuarios(reloj_t0: FrozenClock) -> None:
    from app.core.ratelimit import USER_LIMITS, enforce_user_limit, store_for

    await enforce_user_limit(_peticion(dict(USER_LIMITS)), "admin-write", USUARIO)
    assert len(store_for("user")) == 1
    assert len(store_for("account")) == 0 and len(store_for("ip")) == 0


async def test_enforce_user_limit_toma_el_tope_de_app_state(reloj_t0: FrozenClock) -> None:
    from app.core.errors import TooManyRequestsError
    from app.core.ratelimit import USER_LIMITS, enforce_user_limit

    peticion = _peticion({**USER_LIMITS, "members-write": (2, 60)})
    await enforce_user_limit(peticion, "members-write", USUARIO)
    await enforce_user_limit(peticion, "members-write", USUARIO)
    with pytest.raises(TooManyRequestsError):
        await enforce_user_limit(peticion, "members-write", USUARIO)


async def test_enforce_user_limit_con_un_bucket_fuera_del_catalogo_da_key_error(
    reloj_t0: FrozenClock,
) -> None:
    from app.core.ratelimit import USER_LIMITS, enforce_user_limit

    with pytest.raises(KeyError):
        await enforce_user_limit(_peticion(dict(USER_LIMITS)), "inventado", USUARIO)


async def test_enforce_user_limit_no_escribe_el_usuario_en_el_log(
    reloj_t0: FrozenClock, caplog: pytest.LogCaptureFixture
) -> None:
    from app.core.errors import TooManyRequestsError
    from app.core.ratelimit import USER_LIMITS, enforce_user_limit

    peticion = _peticion({**USER_LIMITS, "members-reveal": (1, 60)})
    await enforce_user_limit(peticion, "members-reveal", USUARIO)
    with caplog.at_level(logging.WARNING, logger="app.ratelimit"):
        with pytest.raises(TooManyRequestsError):
            await enforce_user_limit(peticion, "members-reveal", USUARIO)
    assert caplog.records, "el 429 deja un aviso"
    assert str(USUARIO) not in caplog.text
    assert all(getattr(r, "bucket", None) == "members-reveal" for r in caplog.records)


async def test_usage_cuenta_dentro_de_la_ventana_y_cero_fuera(reloj_t0: FrozenClock) -> None:
    from app.core.ratelimit import USER_LIMITS, enforce_user_limit, store_for, usage

    peticion = _peticion(dict(USER_LIMITS))
    for _ in range(3):
        await enforce_user_limit(peticion, "members-reveal-hour", USUARIO)
    assert await usage("members-reveal-hour", str(USUARIO), window_s=3600) == 3
    assert await usage("members-reveal-hour", str(OTRO), window_s=3600) == 0
    claves = len(store_for("user"))
    assert await usage("members-reveal-day", str(USUARIO), window_s=86400) == 0
    assert len(store_for("user")) == claves  # consultar no crea la clave
    reloj_t0.advance(hours=1)
    assert await usage("members-reveal-hour", str(USUARIO), window_s=3600) == 0


async def test_usage_respeta_el_tipo_de_almacen(reloj_t0: FrozenClock) -> None:
    from app.core.ratelimit import enforce, usage

    await enforce("login-account", "ana@apex.co", limit=5, window_s=900)
    assert await usage("login-account", "ana@apex.co", window_s=900, kind="account") == 1
    assert await usage("login-account", "ana@apex.co", window_s=900) == 0  # kind="user"
