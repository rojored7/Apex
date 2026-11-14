"""Serialización de `init-keys --data-class` y `rotate-key --provider` (S6-A2, revisión M2).

Ambos toman `pg_advisory_xact_lock(hashtext('apex:rotate:<clase>'))` como primera sentencia: dos
sesiones a la vez no duplican versiones ni dejan dos filas activas; la segunda espera y ve lo que
dejó la primera.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import select

from app.cli_base import unit_of_work
from app.cli_ops.keys_data_class import ensure_data_class
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID
from app.core.crypto import provider as provider_mod
from app.core.crypto.models import CryptoKey
from app.core.crypto.sign_rotation import SignRotationError, switch_provider
from tests.crypto._migracion import Entorno, migracion_lista
from tests.crypto.conftest import fila_sign

pytestmark = pytest.mark.usefixtures("reloj")
__all__ = ["migracion_lista"]
CLASE = "audit.signature"


@pytest.fixture
def destinos(migracion_lista: Entorno, monkeypatch: pytest.MonkeyPatch) -> Entorno:
    e = migracion_lista
    por_nombre: dict[str, Any] = {"local": e.local, "openbao": e.openbao}
    monkeypatch.setattr(
        provider_mod, "get_provider_named", lambda _s, nombre, **_kw: por_nombre[nombre]
    )
    provider_mod.configure_provider(e.local)
    yield e  # type: ignore[misc]
    provider_mod.configure_provider(None)


async def _filas(e: Entorno) -> list[tuple[int, str, str]]:
    async with e.fabrica() as sesion:
        filas = await sesion.scalars(
            select(CryptoKey).where(CryptoKey.purpose == "sign").order_by(CryptoKey.version)
        )
        return [(k.version, k.state, k.provider) for k in filas]


async def _rotar(e: Entorno, settings: Settings, destino: str) -> object:
    async with e.fabrica() as sesion:
        with unit_of_work(SYSTEM_USER_ID):
            return await switch_provider(sesion, settings, CLASE, destino, "prueba", SYSTEM_USER_ID)


async def _iniciar(e: Entorno, settings: Settings) -> object:
    async with e.fabrica() as sesion:
        with unit_of_work(SYSTEM_USER_ID):
            async with sesion.begin():
                return await ensure_data_class(sesion, settings, CLASE, SYSTEM_USER_ID)


async def test_dos_rotaciones_a_la_vez_no_duplican_versiones(
    destinos: Entorno, settings_prueba: Settings
) -> None:
    e = destinos
    async with e.fabrica() as sesion:
        await fila_sign(sesion, e.local)
        await sesion.commit()

    salidas = await asyncio.gather(
        _rotar(e, settings_prueba, "openbao"),
        _rotar(e, settings_prueba, "openbao"),
        return_exceptions=True,
    )

    rechazos = [s for s in salidas if isinstance(s, SignRotationError)]
    assert len(rechazos) == 1 and "purpose_not_rotatable" in str(rechazos[0])
    assert sum(isinstance(s, CryptoKey) for s in salidas) == 1
    assert await _filas(e) == [(1, "decrypt_only", "local"), (2, "active", "openbao")]


async def test_init_keys_y_rotate_a_la_vez_dejan_una_sola_fila_activa_coherente(
    destinos: Entorno, settings_prueba: Settings
) -> None:
    e = destinos

    salidas = await asyncio.gather(
        _iniciar(e, settings_prueba), _rotar(e, settings_prueba, "openbao"), return_exceptions=True
    )

    ajenas = [
        s for s in salidas if isinstance(s, BaseException) and not isinstance(s, SignRotationError)
    ]
    assert ajenas == []
    filas = await _filas(e)
    assert [f for f in filas if f[1] == "active"] and len(
        [f for f in filas if f[1] == "active"]
    ) == 1
    assert [v for v, _, _ in filas] == list(range(1, len(filas) + 1))
