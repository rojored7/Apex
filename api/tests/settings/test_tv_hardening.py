"""Correcciones de la revisión de C1 (S8-C1b): L-2, L-3 y las carreras de L-5. Base real."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.settings import service
from app.modules.settings.exceptions import SectionNotAvailable, SettingsValidationError
from app.modules.settings.schemas import SectionKey, TvEditable
from tests.settings._apoyo import ADMIN_ID

ORIGEN = "https://apex.ejemplo.co"
EDICION = TvEditable(refresh_seconds=90, show_leaderboard=False)
CORRUPTA = '{"refresh_seconds": "no es un numero", "device_token_hash": 7}'


async def _corromper(db: AsyncSession) -> None:
    await db.execute(
        text("UPDATE settings.settings_sections SET value = CAST(:v AS jsonb) WHERE key = 'tv'"),
        {"v": CORRUPTA},
    )
    await db.flush()


@pytest.mark.usefixtures("reloj")
async def test_get_de_otro_modulo_no_entrega_la_seccion_tv(session: AsyncSession) -> None:
    """L-2: `get(session, SectionKey.tv)` no devuelve `TvStored` (con el hash) a un consumidor."""
    with actor_scope(ADMIN_ID):
        await service.regenerate_tv_token(session, ADMIN_ID, origin=ORIGEN)
        with pytest.raises(SectionNotAvailable):
            await service.get(session, SectionKey.tv)


@pytest.mark.usefixtures("reloj")
async def test_patch_sobre_una_fila_que_no_valida_da_422_controlado(session: AsyncSession) -> None:
    """L-3: una fila guardada que no valida no es un 500: el `PATCH` responde 422."""
    with actor_scope(ADMIN_ID):
        salida = await service.regenerate_tv_token(session, ADMIN_ID, origin=ORIGEN)
        await _corromper(session)
        with pytest.raises(SettingsValidationError):
            await service.update_tv(session, EDICION, salida.version, ADMIN_ID)


@pytest.mark.usefixtures("reloj")
async def test_vista_regenerar_y_revocar_se_recuperan_de_una_fila_que_no_valida(
    session: AsyncSession,
) -> None:
    """L-3 [DECISIÓN DE DISEÑO]: leer, regenerar y revocar parten de los defaults (la fila vuelve
    a ser válida); nunca un 500 que deje al admin sin forma de repararla."""
    with actor_scope(ADMIN_ID):
        await service.regenerate_tv_token(session, ADMIN_ID, origin=ORIGEN)
        await _corromper(session)
        vista = await service.get_tv(session)
        assert vista.value.has_token is False and vista.value.refresh_seconds == 30
        nuevo = await service.regenerate_tv_token(session, ADMIN_ID, origin=ORIGEN)
        assert await service.verify_tv_token(session, nuevo.token) is not None
        await _corromper(session)
        revocada = await service.revoke_tv_token(session, ADMIN_ID)
        assert revocada.value.has_token is False
        assert await service.verify_tv_token(session, nuevo.token) is None


@pytest.mark.usefixtures("reloj", "bus_confirmado")
async def test_primer_guardado_sin_fila_en_carrera_no_pierde_ninguno(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    """L-5: dos regeneraciones sin fila previa. La primera inserta sin confirmar; la segunda choca
    con el índice único (rama `except VersionConflict` de `_tv_locked`), espera la fila y sigue."""
    una, otra = dos_sesiones
    with actor_scope(ADMIN_ID):
        primera = await service.regenerate_tv_token(una, ADMIN_ID, origin=ORIGEN)  # sin commit

    async def segunda() -> object:
        with actor_scope(ADMIN_ID):
            try:
                salida = await service.regenerate_tv_token(otra, ADMIN_ID, origin=ORIGEN)
                await otra.commit()
                return salida
            except BaseException:
                await otra.rollback()
                raise

    tarea = asyncio.create_task(segunda())
    try:
        await asyncio.sleep(0.5)
        assert not tarea.done(), "la segunda debe esperar a la primera"
    finally:
        await una.commit()
        resultado = await asyncio.wait_for(tarea, timeout=30)
    assert getattr(resultado, "version", None) == primera.version + 1
    with actor_scope(ADMIN_ID):
        assert await service.verify_tv_token(una, primera.token) is None  # la segunda lo rota
        assert await service.verify_tv_token(una, resultado.token) is not None  # type: ignore[attr-defined]


@pytest.mark.usefixtures("reloj", "bus_confirmado")
async def test_revocar_y_patch_a_la_vez_nunca_reviven_el_token(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    """L-5: la revocación toma el candado sin confirmar; el `PATCH` (con la versión que dejará)
    espera y, al seguir, conserva `has_token = false`."""
    una, otra = dos_sesiones
    with actor_scope(ADMIN_ID):
        emitido = await service.regenerate_tv_token(una, ADMIN_ID, origin=ORIGEN)
        await una.commit()
        revocada = await service.revoke_tv_token(una, ADMIN_ID)  # sin commit

    async def guardar() -> object:
        with actor_scope(ADMIN_ID):
            try:
                salida = await service.update_tv(otra, EDICION, revocada.version, ADMIN_ID)
                await otra.commit()
                return salida
            except BaseException:
                await otra.rollback()
                raise

    tarea = asyncio.create_task(guardar())
    try:
        await asyncio.sleep(0.5)
        assert not tarea.done(), "el PATCH debe esperar al candado de la revocación"
    finally:
        await una.commit()
        resultado = await asyncio.wait_for(tarea, timeout=30)
    assert resultado.value.has_token is False  # type: ignore[attr-defined]
    with actor_scope(ADMIN_ID):
        assert await service.verify_tv_token(una, emitido.token) is None
