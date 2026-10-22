"""`settings.service.gym_name` tolera una fila que ya no valida (revisión Python M3).

`GET /auth/me` lee el nombre del gimnasio en cada carga del panel; si el valor guardado deja de
validar contra `GymSettings` (un cambio de esquema, una edición a mano), antes daba 500 a todos
los usuarios. Ahora registra un aviso sin el valor y responde con el respaldo `"APEX"`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID
from app.modules.settings.service import gym_name
from tests.conftest import Cabeceras, CrearUsuario

VALORES_INVALIDOS: list[dict[str, Any]] = [
    {"name": 5},
    {"name": ""},
    {"name": "Apex", "campo_viejo": True},
    {"nombre": "sin name"},
]


async def _guardar_crudo(session: AsyncSession, valor: dict[str, Any]) -> None:
    await session.execute(
        text(
            "INSERT INTO settings.settings_sections (id, key, value, version, updated_by,"
            " created_by) VALUES (gen_random_uuid(), 'gym', CAST(:v AS jsonb), 1, :u, :u)"
        ),
        {"v": json.dumps(valor), "u": SYSTEM_USER_ID},
    )


@pytest.mark.parametrize("valor", VALORES_INVALIDOS, ids=["entero", "vacio", "extra", "sin-name"])
async def test_un_valor_guardado_invalido_da_el_respaldo(
    session: AsyncSession, valor: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    await _guardar_crudo(session, valor)
    with caplog.at_level(logging.WARNING, logger="app.settings"):
        assert await gym_name(session) == "APEX"
    avisos = [r for r in caplog.records if r.name == "app.settings"]
    assert avisos and all("sin name" not in r.getMessage() for r in avisos)


async def test_auth_me_responde_200_con_el_respaldo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    await _guardar_crudo(session, {"name": 5})
    r = await app_http.get("/api/v1/auth/me", headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert r.json()["gym_name"] == "APEX"
