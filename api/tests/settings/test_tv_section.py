"""Sección `tv` de configuración (S8-C1, US-175; S8-D17, S8-D30, S8-D33)."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.settings.exceptions import SectionNotAvailable
from app.modules.settings.schemas import (
    ENABLED_SECTIONS,
    SECTION_DEFAULTS,
    SECTION_REGISTRY,
    SECTION_VIEWS,
    SectionKey,
    TvEditable,
    TvPatchIn,
    TvStored,
)
from app.modules.settings.service import get_section, update_section
from tests.conftest import Cabeceras, CrearUsuario
from tests.settings._apoyo import ADMIN_ID, API

TV = f"{API}/settings/tv"


def test_tv_esta_en_el_catalogo_de_secciones() -> None:
    assert SectionKey.tv in ENABLED_SECTIONS and len(ENABLED_SECTIONS) == 8
    assert SECTION_REGISTRY[SectionKey.tv] is TvStored
    assert SECTION_VIEWS[SectionKey.tv] is TvStored
    assert TvStored.model_validate(SECTION_DEFAULTS[SectionKey.tv]).refresh_seconds == 30


@pytest.mark.parametrize("campo", ["device_token", "device_token_hash", "token", "token_last4"])
async def test_422_con_device_token_o_hash(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, campo: str
) -> None:
    admin = await usuario_real("admin")
    valor: dict[str, Any] = {"refresh_seconds": 30, "show_leaderboard": True, campo: "x" * 64}
    r = await app_http.patch(TV, headers=cabeceras(admin), json={"value": valor, "version": 0})
    assert r.status_code == 422, r.text
    with pytest.raises(ValidationError):
        TvPatchIn.model_validate({"value": valor, "version": 0})


@pytest.mark.parametrize(
    ("segundos", "valido"), [(14, False), (15, True), (300, True), (301, False)]
)
async def test_refresh_seconds_15_a_300(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    segundos: int,
    valido: bool,
) -> None:
    admin = await usuario_real("admin")
    cuerpo = {"value": {"refresh_seconds": segundos, "show_leaderboard": False}, "version": 0}
    r = await app_http.patch(TV, headers=cabeceras(admin), json=cuerpo)
    assert r.status_code == (200 if valido else 422), r.text
    if valido:
        assert r.json()["value"]["refresh_seconds"] == segundos


def test_refresh_seconds_no_acepta_texto_ni_booleano() -> None:
    for malo in ("30", True, 30.5, None):
        with pytest.raises(ValidationError):
            TvEditable.model_validate({"refresh_seconds": malo, "show_leaderboard": True})
    with pytest.raises(ValidationError):
        TvEditable.model_validate({"refresh_seconds": 30, "show_leaderboard": "si"})


async def test_get_sin_fila_da_defaults_y_nunca_el_hash(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.get(TV, headers=cabeceras(admin))
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["key"] == "tv" and cuerpo["version"] == 0
    assert cuerpo["value"] == {
        "refresh_seconds": 30,
        "show_leaderboard": True,
        "has_token": False,
        "token_last4": None,
        "rotated_at": None,
    }
    assert "device_token_hash" not in r.text


async def test_ruta_generica_get_y_patch_tv_404_section_not_available(
    session: AsyncSession,
) -> None:
    """La genérica rechaza `tv` (L-1): solo las rutas propias leen y escriben la sección."""
    with actor_scope(ADMIN_ID):
        with pytest.raises(SectionNotAvailable):
            await get_section(session, "tv")
        with pytest.raises(SectionNotAvailable):
            await update_section(
                session, "tv", {"refresh_seconds": 30, "show_leaderboard": True}, 0, ADMIN_ID
            )
