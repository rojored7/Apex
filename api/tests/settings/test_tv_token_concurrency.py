"""H-1 (S8-C1, S8-D30): regenerar y guardar a la vez nunca reviven el token viejo. Commit real."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.security import hash_opaque_token
from app.modules.settings import service
from app.modules.settings.exceptions import VersionConflict
from app.modules.settings.schemas import TvEditable
from tests.settings._apoyo import ADMIN_ID

pytestmark = pytest.mark.usefixtures("reloj", "bus_confirmado")

ORIGEN = "https://apex.ejemplo.co"
EDICION = TvEditable(refresh_seconds=90, show_leaderboard=False)


async def _guardado(sesion: AsyncSession) -> str | None:
    return await sesion.scalar(
        text("SELECT value->>'device_token_hash' FROM settings.settings_sections WHERE key = 'tv'")
    )


async def test_regenerar_y_patch_a_la_vez_nunca_reviven_el_token_viejo(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    """La regeneración toma el candado y se queda con él sin confirmar; el `PATCH` (con la versión
    que dejará la regeneración) espera, y al seguir copia el hash NUEVO de la fila bloqueada."""
    una, otra = dos_sesiones
    with actor_scope(ADMIN_ID):
        viejo = await service.regenerate_tv_token(una, ADMIN_ID, origin=ORIGEN)
        await una.commit()
        nuevo = await service.regenerate_tv_token(una, ADMIN_ID, origin=ORIGEN)  # sin commit

    async def guardar() -> object:
        with actor_scope(ADMIN_ID):
            try:
                salida = await service.update_tv(otra, EDICION, nuevo.version, ADMIN_ID)
                await otra.commit()
                return salida
            except BaseException:
                await otra.rollback()
                raise

    patch = asyncio.create_task(guardar())
    try:
        await asyncio.sleep(0.5)
        assert not patch.done(), "el PATCH debe esperar al candado de la regeneración"
    finally:
        await una.commit()
        resultado = await asyncio.wait_for(patch, timeout=30)
    assert resultado is not None
    assert await _guardado(una) == hash_opaque_token(nuevo.token)
    assert await _guardado(una) != hash_opaque_token(viejo.token)
    with actor_scope(ADMIN_ID):
        assert await service.verify_tv_token(una, viejo.token) is None
        assert await service.verify_tv_token(una, nuevo.token) is not None


async def test_patch_en_vuelo_con_version_vieja_recibe_409_tras_regenerar(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    una, otra = dos_sesiones
    with actor_scope(ADMIN_ID):
        primero = await service.regenerate_tv_token(una, ADMIN_ID, origin=ORIGEN)
        await una.commit()
        nuevo = await service.regenerate_tv_token(una, ADMIN_ID, origin=ORIGEN)  # sin commit

    async def guardar() -> object:
        with actor_scope(ADMIN_ID):
            try:
                return await service.update_tv(otra, EDICION, primero.version, ADMIN_ID)
            finally:
                await otra.rollback()

    patch = asyncio.create_task(guardar())
    await asyncio.sleep(0.5)
    assert not patch.done()
    await una.commit()
    resultado = (await asyncio.gather(patch, return_exceptions=True))[0]
    assert isinstance(resultado, VersionConflict)
    assert await _guardado(una) == hash_opaque_token(nuevo.token)
