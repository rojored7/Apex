"""`import-members` con el corte de autorización vigente (S6-C3, US-149; S6-D46, M-11).

El import llama `members.service.create(..., enforce_consent=False)` (la única llamada fuera de
`cli.py` junto con `seed/apply.py`, como `enforce_retroactive_limit`, S4B-D33): los importados
quedan SIN autorización (`data_consent_at` nulo) aunque `consent_required_from` sea hoy, y la salida
sigue advirtiendo `consent_missing`. Guarda de regresión: pasa con los stubs y se rompe si el Verde
olvida la exención.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cli import app
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID
from app.modules.members.models import Member
from tests.cli._apoyo import correr
from tests.cli.conftest import import_dir, limpiar_demo, settings_importacion  # noqa: F401
from tests.conftest import CLAVE_PRUEBA
from tests.factories.users import make_user
from tests.factories.xlsx import fila_valida, make_members_xlsx
from tests.members._consentimiento import HOY, publicar_politica

Fabrica = async_sessionmaker[AsyncSession]

pytestmark = pytest.mark.usefixtures("reloj", "limpiar_demo")


async def test_importar_con_el_corte_vigente_crea_los_socios_sin_autorizacion(
    limpiar_demo: Fabrica,  # noqa: F811
    settings_importacion: Settings,  # noqa: F811
    import_dir: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    async with limpiar_demo() as sesion:
        admin = await make_user(sesion, role="admin", password=CLAVE_PRUEBA)
        await publicar_politica(sesion, SYSTEM_USER_ID, corte=HOY)
    archivo = make_members_xlsx(
        import_dir / "socios.xlsx", [fila_valida(1), fila_valida(2), fila_valida(3)]
    )

    resultado = correr(
        app,
        ["import-members", str(archivo), "--as", admin.email],
        "dev",
        base=settings_importacion,
        monkeypatch=monkeypatch,
    )

    assert resultado.exit_code == 0, resultado.output
    linea = next(ln for ln in resultado.output.splitlines() if "created=" in ln)
    assert "created=3" in linea and "rejected=0" in linea and "consent_missing=3" in linea
    async with limpiar_demo() as sesion:
        total = await sesion.scalar(select(func.count()).select_from(Member))
        sin = await sesion.scalar(
            select(func.count()).select_from(Member).where(Member.data_consent_at.is_(None))
        )
    assert (total, sin) == (3, 3)
