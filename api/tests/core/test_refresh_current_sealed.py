"""`refresh_current` con el custodio caído conserva el keyring y no falla la petición (S5-B3; M-4,
S5-D54, S5-D162). Rojo B3: el código de B1 puede ya cumplirlo; la prueba lo fija contra regresión.

Otro proceso rota una llave (aparece una fila nueva en `crypto_keys`) y el proveedor está sellado:
`refresh_current` no lanza, el keyring sigue siendo el mismo objeto con las mismas llaves y una
petición autenticada responde 200.
"""

from __future__ import annotations

import os
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import bus
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.keyring import configure_keyring, current_keyring, refresh_current
from app.core.crypto.models import CryptoKey
from app.core.crypto.provider import configure_provider
from tests.conftest import Cabeceras, CrearUsuario
from tests.core._cripto_apoyo import proveedor_ctl
from tests.factories.fake_provider import ProveedorControlable

__all__ = ["proveedor_ctl"]


async def _llave_nueva_de_otro_proceso(
    session: AsyncSession, proveedor: ProveedorControlable
) -> None:
    envuelta = await proveedor.wrap(os.urandom(32))
    with actor_scope(SYSTEM_USER_ID):
        session.add(
            CryptoKey(
                id=uuid4(),
                purpose="encrypt",
                data_class="member.document",
                algorithm="A256GCM",
                provider="local",
                version=99,
                state="decrypt_only",
                wrapped_material=envuelta,
                created_by=SYSTEM_USER_ID,
            )
        )
        await session.flush()


async def test_refresh_current_sellado_no_lanza_y_conserva_el_keyring(
    sin_llaves: AsyncSession, proveedor_ctl: ProveedorControlable
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        keyring = await ensure_keys(sin_llaves, proveedor_ctl, lambda _n: proveedor_ctl)
    configure_provider(proveedor_ctl)
    blob = bus.encrypt("member.phone", b"3001234567", b"aad", record_id=uuid4())
    llaves_antes = {k.key_id for k in keyring.keys()}
    await _llave_nueva_de_otro_proceso(sin_llaves, proveedor_ctl)
    proveedor_ctl.estado = "sealed"

    await refresh_current(sin_llaves)  # no debe lanzar

    assert current_keyring() is keyring
    assert {k.key_id for k in current_keyring().keys()} == llaves_antes
    assert bus.decrypt(blob, b"aad") == b"3001234567"
    configure_keyring(None)
    configure_provider(None)


async def test_una_peticion_autenticada_con_el_proveedor_sellado_responde_200(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    proveedor_ctl: ProveedorControlable,
) -> None:
    quien = await usuario_real("admin")
    await _llave_nueva_de_otro_proceso(session, proveedor_ctl)
    proveedor_ctl.estado = "sealed"
    configure_provider(proveedor_ctl)
    keyring = current_keyring()

    r = await app_http.get("/api/v1/auth/me", headers=cabeceras(quien))

    assert r.status_code == 200, r.text
    assert current_keyring() is keyring
