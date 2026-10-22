"""Límite de intentos: función pura, IP real y dependencia por ruta (US-036 T7, T8)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from ipaddress import ip_network
from typing import Annotated

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
