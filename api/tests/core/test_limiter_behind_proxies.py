"""El limitador cuenta la IP real detrás de Caddy y Nginx (S6-E1, riesgo 4, D64, D82).

Nginx restaura la IP real del cliente con `real_ip` (`set_real_ip_from <Caddy>/32`,
`real_ip_recursive off`) y el api solo salta a Nginx: `TRUSTED_PROXIES` es la IP de Nginx y nunca
la de Caddy. Una cadena con Caddy en medio no amplía esa confianza.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from ipaddress import ip_network

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.clock import FrozenClock, reset_clock, set_clock
from app.core.errors import register_error_handlers
from app.core.ratelimit import client_ip, rate_limit, reset_store

T0 = datetime(2026, 11, 12, 15, 0, 0, tzinfo=UTC)
NGINX = "172.30.0.10"
CADDY = "172.30.0.11"
CLIENTE = "203.0.113.9"
OTRO_CLIENTE = "198.51.100.7"
SOLO_NGINX = [ip_network(f"{NGINX}/32")]


def _request(host: str, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    scope = {"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (host, 1)}
    return Request(scope)


# client_ip: función pura -------------------------------------------------------------------


def test_con_solo_nginx_de_confianza_cuenta_la_ip_real_del_cliente() -> None:
    assert client_ip(_request(NGINX, f"{CLIENTE}, {NGINX}"), SOLO_NGINX) == CLIENTE
    assert client_ip(_request(NGINX, CLIENTE), SOLO_NGINX) == CLIENTE


def test_caddy_en_medio_no_amplia_la_confianza() -> None:
    cadena = f"{OTRO_CLIENTE}, {CLIENTE}, {CADDY}, {NGINX}"
    resuelta = client_ip(_request(NGINX, cadena), SOLO_NGINX)
    assert resuelta == CADDY, "el api se detiene en la primera IP que no es Nginx"
    assert resuelta not in {CLIENTE, OTRO_CLIENTE}, "las IP a la izquierda no se creen"


def test_caddy_como_par_directo_no_es_de_confianza() -> None:
    assert client_ip(_request(CADDY, f"{CLIENTE}, {CADDY}"), SOLO_NGINX) == CADDY


def test_una_cabecera_falsificada_desde_fuera_no_cambia_la_ip() -> None:
    assert client_ip(_request(OTRO_CLIENTE, f"{CLIENTE}, {NGINX}"), SOLO_NGINX) == OTRO_CLIENTE


def test_una_cadena_con_basura_a_la_izquierda_de_nginx_cae_al_par() -> None:
    assert client_ip(_request(NGINX, f"no-es-ip, {NGINX}"), SOLO_NGINX) == NGINX


def test_sin_trusted_proxies_todo_cuenta_contra_el_par() -> None:
    assert client_ip(_request(NGINX, f"{CLIENTE}, {NGINX}"), []) == NGINX


# rate_limit de punta a punta ---------------------------------------------------------------


@pytest.fixture
async def app() -> AsyncIterator[FastAPI]:
    reset_store()
    aplicacion = FastAPI()
    register_error_handlers(aplicacion)
    aplicacion.state.trusted_proxies = SOLO_NGINX

    @aplicacion.post("/login", dependencies=[Depends(rate_limit("login"))])
    async def login() -> dict[str, str]:
        return {"ok": "login"}

    token = set_clock(FrozenClock(T0))
    try:
        yield aplicacion
    finally:
        reset_clock(token)
        reset_store()


def _desde_nginx(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app, client=(NGINX, 1234)), base_url="http://t")


async def _agotar(cliente: AsyncClient, forwarded: str) -> None:
    for _ in range(5):
        r = await cliente.post("/login", headers={"X-Forwarded-For": forwarded})
        assert r.status_code == 200
    r = await cliente.post("/login", headers={"X-Forwarded-For": forwarded})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"


async def test_cada_cliente_real_detras_de_nginx_tiene_su_propia_cubeta(app: FastAPI) -> None:
    async with _desde_nginx(app) as c:
        await _agotar(c, f"{CLIENTE}, {NGINX}")
        r = await c.post("/login", headers={"X-Forwarded-For": f"{OTRO_CLIENTE}, {NGINX}"})
        assert r.status_code == 200, "bloquear a un cliente no debe bloquear a los demás"


async def test_el_limite_sigue_a_la_ip_real_y_no_a_nginx(app: FastAPI) -> None:
    async with _desde_nginx(app) as c:
        await _agotar(c, f"{CLIENTE}, {NGINX}")
        r = await c.post("/login", headers={"X-Forwarded-For": f"{CLIENTE}, {NGINX}"})
        assert r.status_code == 429, "el mismo cliente real sigue limitado"


async def test_inventar_ips_a_la_izquierda_de_caddy_no_evade_el_limite(app: FastAPI) -> None:
    async with _desde_nginx(app) as c:
        cadena = f"203.0.113.1, {CADDY}, {NGINX}"
        await _agotar(c, cadena)
        for inventada in ("203.0.113.2", "203.0.113.3", "203.0.113.4"):
            r = await c.post(
                "/login", headers={"X-Forwarded-For": f"{inventada}, {CADDY}, {NGINX}"}
            )
            assert r.status_code == 429, f"{inventada} no debe abrir una cubeta nueva"
