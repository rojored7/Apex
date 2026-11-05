"""Api sellado: sin keyring el socio no se descifra, lo demás sigue (S5-B3; US-136). Rojo B3.

Los socios existen (cifrados con el keyring cargado); luego el proceso queda sin keyring, como un
api que arrancó con OpenBao sellado:
- `GET /members/{id}` (descifra la ficha) -> 503 `crypto_unavailable` con `Retry-After: 30`;
- `GET /members` (la lista no descifra nada) -> 200 con los socios;
- `POST /auth/login` -> 200 (la sesión no usa el bus).
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto.keyring import Keyring, configure_keyring
from tests.auth._sesion import LOGIN, post_auth
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member
from tests.members._apoyo import MEMBERS, ruta_socio

MENSAJE = "El custodio de llaves no está disponible. Avise al administrador para desellarlo."


async def test_la_ficha_del_socio_responde_503_crypto_unavailable_sin_keyring(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    quien = await usuario_real("admin")
    configure_keyring(None)

    r = await app_http.get(ruta_socio(socio.id), headers=cabeceras(quien))

    assert r.status_code == 503, r.text
    assert r.json() == {"error": {"code": "crypto_unavailable", "message": MENSAJE}}
    assert r.headers["retry-after"] == "30"


async def test_la_lista_de_socios_sigue_respondiendo_200_sin_keyring(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    quien = await usuario_real("coach")
    configure_keyring(None)

    r = await app_http.get(MEMBERS, headers=cabeceras(quien))

    assert r.status_code == 200, r.text
    assert str(socio.id) in {fila["id"] for fila in r.json()["items"]}


async def test_el_login_sigue_respondiendo_200_sin_keyring(
    app_http: AsyncClient, usuario_real: CrearUsuario, bus_listo: Keyring
) -> None:
    coach = await usuario_real("coach")
    configure_keyring(None)

    r = await post_auth(app_http, LOGIN, json={"email": coach.email, "password": coach.password})

    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == coach.email
