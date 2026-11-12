"""Ayudas de las pruebas de autorización de datos (S6-C3, US-149; S6-D46, M-11).

- `HOY`, `AYER` y `MANANA`: las fechas de Bogotá alrededor de `T0` (2026-10-21 15:00 UTC, que son
  las 10:00 del mismo día en Bogotá): el corte de `consent_required_from`.
- `VERSION`: la versión de la política que las pruebas publican.
- `publicar_politica(session, actor, corte=...)`: guarda la sección `privacy` con
  `settings.service.update_section` (la misma puerta del `PATCH /settings/privacy`) y confirma.
- `quitar_version(session)`: deja la sección con `policy_version = null` por SQL directo: el
  esquema de escritura la exige, pero la lectura (`PrivacyView`) la admite, y es el estado que
  hay que cubrir (corte vigente sin política que copiar).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.settings.service import update_section
from tests.settings._apoyo import PRIVACY_OK

HOY: Final = date(2026, 10, 21)
AYER: Final = HOY - timedelta(days=1)
MANANA: Final = HOY + timedelta(days=1)
VERSION: Final = "2026-11"


async def publicar_politica(
    session: AsyncSession,
    actor: UUID,
    *,
    corte: date | None,
    version: str = VERSION,
) -> None:
    """Publica la política `version` con el corte dado (nulo = no se exige nada) y confirma."""
    valor: dict[str, Any] = {
        **PRIVACY_OK,
        "policy_version": version,
        "consent_required_from": corte,
    }
    with actor_scope(actor):
        await update_section(session, "privacy", valor, 0, actor)
        await session.commit()


async def quitar_version(session: AsyncSession) -> None:
    """`policy_version = null` en la sección ya guardada (el corte se conserva)."""
    await session.execute(
        text(
            "UPDATE settings.settings_sections "
            "SET value = jsonb_set(value, '{policy_version}', 'null'::jsonb) "
            "WHERE key = 'privacy'"
        )
    )
    await session.commit()
