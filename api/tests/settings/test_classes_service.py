"""`settings.service.classes` (S7-D8): cupo y ventana por defecto, tolerante a lo guardado."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID
from app.modules.settings.service import classes
from tests.settings._apoyo import CLASSES_DEFAULTS, CLASSES_OK


async def _guardar_crudo(session: AsyncSession, valor: dict[str, Any]) -> None:
    await session.execute(
        text(
            "INSERT INTO settings.settings_sections (id, key, value, version, updated_by,"
            " created_by) VALUES (gen_random_uuid(), 'classes', CAST(:v AS jsonb), 1, :u, :u)"
        ),
        {"v": json.dumps(valor), "u": SYSTEM_USER_ID},
    )


async def test_sin_fila_da_15_y_30(session: AsyncSession) -> None:
    salida = await classes(session)
    assert salida.model_dump() == CLASSES_DEFAULTS


async def test_fila_valida_se_devuelve(session: AsyncSession) -> None:
    await _guardar_crudo(session, CLASSES_OK)
    salida = await classes(session)
    assert salida.default_capacity == 18 and salida.checkin_window_min == 45


@pytest.mark.parametrize(
    "valor",
    [{"default_capacity": "x", "checkin_window_min": 30}, {"allow_over_capacity": True}],
    ids=["tipo_malo", "campo_retirado"],
)
async def test_fila_corrupta_da_defaults_y_avisa(
    session: AsyncSession, valor: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    await _guardar_crudo(session, valor)
    with caplog.at_level(logging.WARNING, logger="app.settings"):
        salida = await classes(session)
    assert salida.model_dump() == CLASSES_DEFAULTS
    avisos = [r for r in caplog.records if r.name == "app.settings"]
    assert avisos and all("allow_over_capacity" not in r.getMessage() for r in avisos)
