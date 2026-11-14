"""`generate-sessions [--days N] [--as <correo>]` (S7-B1, US-156; S7-D10). Rojo B1.

Hoy (reloj `T0`) es el 21 de octubre de 2026 en Bogotá. Base real con commit; no escribe `job_runs`.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.cli import app
from app.core.audit import AuditEntry
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID
from tests.cli._apoyo import correr
from tests.conftest import CLAVE_PRUEBA, limpiar_tras_dos_sesiones
from tests.factories.classes import make_slot
from tests.factories.users import make_user

Fabrica = async_sessionmaker[AsyncSession]
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

pytestmark = pytest.mark.usefixtures("reloj")


@pytest.fixture
async def fabrica(engine: AsyncEngine) -> AsyncIterator[Fabrica]:
    async with engine.connect() as conexion:
        ultima = await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0)))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await limpiar_tras_dos_sesiones(engine, ultima or 0)


async def _contar(fabrica: Fabrica) -> int:
    async with fabrica() as sesion:
        return int(await sesion.scalar(text("SELECT count(*) FROM classes.class_sessions")) or 0)


async def _con_franja(fabrica: Fabrica, **cambios: Any) -> None:
    async with fabrica() as sesion:
        await make_slot(sesion, weekdays=[0], **cambios)


def _correr(settings: Settings, mp: pytest.MonkeyPatch, *args: str, env: str = "dev") -> Any:
    return correr(app, ["generate-sessions", *args], env, base=settings, monkeypatch=mp)  # type: ignore[arg-type]


async def test_genera_14_dias_por_omision_e_imprime_solo_conteos(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _con_franja(fabrica)
    r = _correr(settings_prueba, monkeypatch)
    assert r.exit_code == 0, r.output
    assert "creadas 2" in r.output and "franjas 1" in r.output
    assert not UUID_RE.search(r.output)
    assert await _contar(fabrica) == 2


async def test_la_segunda_corrida_no_cambia_nada(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _con_franja(fabrica)
    _correr(settings_prueba, monkeypatch)
    r = _correr(settings_prueba, monkeypatch)
    assert r.exit_code == 0 and "creadas 0" in r.output
    assert await _contar(fabrica) == 2


async def test_days_acota_la_ventana(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _con_franja(fabrica)
    r = _correr(settings_prueba, monkeypatch, "--days", "5")  # 21 al 25: sin lunes
    assert r.exit_code == 0 and "creadas 0" in r.output
    r = _correr(settings_prueba, monkeypatch, "--days", "28")
    assert r.exit_code == 0 and "creadas 4" in r.output


@pytest.mark.parametrize("dias", ["0", "29", "-1"])
async def test_days_fuera_de_1_a_28_sale_con_2_y_no_escribe(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch, dias: str
) -> None:
    await _con_franja(fabrica)
    r = _correr(settings_prueba, monkeypatch, "--days", dias)
    assert r.exit_code == 2, r.output
    assert await _contar(fabrica) == 0


async def test_sin_as_se_atribuye_al_usuario_tecnico(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _con_franja(fabrica)
    _correr(settings_prueba, monkeypatch)
    async with fabrica() as sesion:
        autores = (
            (await sesion.execute(text("SELECT DISTINCT created_by FROM classes.class_sessions")))
            .scalars()
            .all()
        )
    assert list(autores) == [SYSTEM_USER_ID]


async def test_as_atribuye_las_filas_y_la_auditoria_a_esa_persona(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _con_franja(fabrica)
    async with fabrica() as sesion:
        admin = await make_user(sesion, role="admin", password=CLAVE_PRUEBA)
    r = _correr(settings_prueba, monkeypatch, "--as", admin.email)
    assert r.exit_code == 0, r.output
    async with fabrica() as sesion:
        creadores = (
            (await sesion.execute(text("SELECT DISTINCT created_by FROM classes.class_sessions")))
            .scalars()
            .all()
        )
        actores = (
            (
                await sesion.execute(
                    text(
                        "SELECT DISTINCT user_id FROM audit.audit_log "
                        "WHERE table_name = 'classes.class_sessions'"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert list(creadores) == [admin.id] and list(actores) == [admin.id]


async def test_un_as_inexistente_sale_con_2_y_no_escribe(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _con_franja(fabrica)
    r = _correr(settings_prueba, monkeypatch, "--as", "nadie@test.apex")
    assert r.exit_code == 2, r.output
    assert await _contar(fabrica) == 0


async def test_en_produccion_exige_as(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _con_franja(fabrica)
    r = _correr(settings_prueba, monkeypatch, env="production")
    assert r.exit_code == 2, r.output
    assert await _contar(fabrica) == 0


async def test_no_escribe_job_runs(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _con_franja(fabrica)
    _correr(settings_prueba, monkeypatch)
    async with fabrica() as sesion:
        assert await sesion.scalar(text("SELECT count(*) FROM worker.job_runs")) == 0


def test_el_comando_esta_registrado() -> None:
    from typer.testing import CliRunner

    salida = CliRunner().invoke(app, ["--help"]).output
    assert "generate-sessions" in salida
