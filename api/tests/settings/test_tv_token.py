"""Token de la TV (S8-C1, US-175; S8-D17, S8-D30 H-1, S8-D32 M-2, L-1, L-7, C5)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.security import hash_opaque_token
from app.modules.settings import service
from app.modules.settings.exceptions import VersionConflict
from app.modules.settings.schemas import TvEditable
from tests.settings._apoyo import ADMIN_ID, filas_de_auditoria

ORIGEN = "https://apex.ejemplo.co"
EDICION = TvEditable(refresh_seconds=60, show_leaderboard=False)

pytestmark = pytest.mark.usefixtures("reloj")


@pytest.fixture
async def db(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    with actor_scope(ADMIN_ID):
        yield session


async def _hash_guardado(db: AsyncSession) -> str | None:
    return await db.scalar(
        text("SELECT value->>'device_token_hash' FROM settings.settings_sections WHERE key = 'tv'")
    )


async def test_token_viejo_invalido_al_instante(db: AsyncSession) -> None:
    """C5: tras regenerar, el token anterior deja de valer en la misma transacción."""
    viejo = await service.regenerate_tv_token(db, ADMIN_ID, origin=ORIGEN)
    assert await service.verify_tv_token(db, viejo.token) is not None
    nuevo = await service.regenerate_tv_token(db, ADMIN_ID, origin=ORIGEN)
    assert await service.verify_tv_token(db, viejo.token) is None
    config = await service.verify_tv_token(db, nuevo.token)
    assert config is not None and (config.refresh_seconds, config.show_leaderboard) == (30, True)


async def test_auditoria_lleva_hash_nunca_el_token(db: AsyncSession) -> None:
    salida = await service.regenerate_tv_token(db, ADMIN_ID, origin=ORIGEN)
    filas = await filas_de_auditoria(db)
    volcado = json.dumps(filas, default=str)
    assert hash_opaque_token(salida.token) in volcado
    assert salida.token not in volcado
    assert salida.token_last4 == salida.token[-4:]


async def test_url_usa_fragmento_tv_token(db: AsyncSession) -> None:
    """M-2: el token va en el fragmento, que nunca sale en una petición."""
    salida = await service.regenerate_tv_token(db, ADMIN_ID, origin=ORIGEN + "/")
    assert salida.url == f"{ORIGEN}/tv#token={salida.token}"
    assert "?" not in salida.url


async def test_regenerar_sube_version(db: AsyncSession, reloj: FrozenClock) -> None:
    primero = await service.regenerate_tv_token(db, ADMIN_ID, origin=ORIGEN)
    assert primero.version == 1 and primero.rotated_at == reloj.now_utc()
    segundo = await service.regenerate_tv_token(db, ADMIN_ID, origin=ORIGEN)
    assert segundo.version == 2 and segundo.token != primero.token
    vista = await service.get_tv(db)
    assert vista.version == 2 and vista.value.has_token is True
    assert vista.value.token_last4 == segundo.token[-4:]


async def test_patch_tras_regenerar_conserva_el_hash(db: AsyncSession) -> None:
    salida = await service.regenerate_tv_token(db, ADMIN_ID, origin=ORIGEN)
    antes = await _hash_guardado(db)
    vista = await service.update_tv(db, EDICION, salida.version, ADMIN_ID)
    assert vista.version == 2 and vista.value.refresh_seconds == 60
    assert vista.value.show_leaderboard is False
    assert vista.value.has_token is True and vista.value.token_last4 == salida.token_last4
    assert await _hash_guardado(db) == antes == hash_opaque_token(salida.token)
    assert await service.verify_tv_token(db, salida.token) is not None


async def test_patch_con_version_previa_a_regenerar_da_409(db: AsyncSession) -> None:
    primero = await service.regenerate_tv_token(db, ADMIN_ID, origin=ORIGEN)
    await service.regenerate_tv_token(db, ADMIN_ID, origin=ORIGEN)
    with pytest.raises(VersionConflict):
        await service.update_tv(db, EDICION, primero.version, ADMIN_ID)


async def test_primer_patch_sin_fila_crea_la_sin_token(db: AsyncSession) -> None:
    with pytest.raises(VersionConflict):
        await service.update_tv(db, EDICION, 3, ADMIN_ID)
    vista = await service.update_tv(db, EDICION, 0, ADMIN_ID)
    assert vista.version == 1 and vista.value.has_token is False
    assert await _hash_guardado(db) is None


async def test_revoke_deja_has_token_false_y_audita(db: AsyncSession) -> None:
    salida = await service.regenerate_tv_token(db, ADMIN_ID, origin=ORIGEN)
    vista = await service.revoke_tv_token(db, ADMIN_ID)
    assert vista.value.has_token is False and vista.value.token_last4 is None
    assert vista.value.rotated_at is None and vista.version == 2
    assert await service.verify_tv_token(db, salida.token) is None
    filas = await filas_de_auditoria(db)
    assert [f["action"] for f in filas] == ["insert", "update", "update"]
    hash_viejo = hash_opaque_token(salida.token)
    assert hash_viejo not in json.dumps(filas[-1]["after"], default=str)
    assert hash_viejo in json.dumps(filas[-1]["before"], default=str)


async def test_revoke_sin_fila_la_crea_sin_token(db: AsyncSession) -> None:
    vista = await service.revoke_tv_token(db, ADMIN_ID)
    assert vista.version == 1 and vista.value.has_token is False


async def test_verify_sin_fila_sin_hash_o_cabecera_vacia_da_none(db: AsyncSession) -> None:
    """L-1: nunca 500; sin fila, sin hash, vacío, enorme, no ASCII o fila inválida: `None`."""
    assert await service.verify_tv_token(db, "abc") is None  # sin fila
    assert await service.verify_tv_token(db, None) is None
    await service.update_tv(db, EDICION, 0, ADMIN_ID)  # fila sin hash
    assert await service.verify_tv_token(db, "abc") is None
    salida = await service.regenerate_tv_token(db, ADMIN_ID, origin=ORIGEN)
    for malo in ("", " ", "x" * 500, "ñandú", salida.token + "x", salida.token.upper()):
        assert await service.verify_tv_token(db, malo) is None
    assert await service.verify_tv_token(db, salida.token) is not None
    roto = '{"device_token_hash": 5}'
    await db.execute(
        text("UPDATE settings.settings_sections SET value = CAST(:v AS jsonb) WHERE key = 'tv'"),
        {"v": roto},
    )
    assert await service.verify_tv_token(db, salida.token) is None  # lo guardado no valida
