"""`current_privacy_version()` y auditoría de la política (US-057 T4; S2-D45)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.settings.service import current_privacy_version, get_section, update_section
from tests.settings._apoyo import ADMIN_ID, PRIVACY_DEFAULTS, PRIVACY_OK, filas_de_auditoria


@pytest.fixture
async def db(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    with actor_scope(ADMIN_ID):
        yield session


async def test_sin_fila_la_version_vigente_es_none(db: AsyncSession) -> None:
    assert await current_privacy_version(db) is None


async def test_sin_fila_la_seccion_muestra_la_politica_sin_publicar(db: AsyncSession) -> None:
    salida = await get_section(db, "privacy")
    assert salida.version == 0 and salida.value == PRIVACY_DEFAULTS


async def test_despues_de_guardar_devuelve_la_version_publicada(db: AsyncSession) -> None:
    await update_section(db, "privacy", PRIVACY_OK, 0, ADMIN_ID)
    assert await current_privacy_version(db) == "2026-10"


async def test_publicar_una_version_nueva_audita_update_con_las_dos(db: AsyncSession) -> None:
    await update_section(db, "privacy", {**PRIVACY_OK, "policy_version": "2026-01"}, 0, ADMIN_ID)
    await update_section(db, "privacy", PRIVACY_OK, 1, ADMIN_ID)
    assert await current_privacy_version(db) == "2026-10"

    auditoria = await filas_de_auditoria(db)
    assert [f["action"] for f in auditoria] == ["insert", "update"]
    update = auditoria[1]
    assert update["before"]["value"]["policy_version"] == "2026-01"
    assert update["after"]["value"]["policy_version"] == "2026-10"
    assert update["before"]["version"] == 1 and update["after"]["version"] == 2
    assert update["subject_member_id"] is None
