"""`seed-notifications [--as]` y su invocación desde `seed` (S5-B6, US-120 y US-121; S5-D25,
S5-D97). # Rojo B6

- `seed-notifications` crea las dos plantillas y las cinco reglas por defecto, imprime los
  conteos (2 y 5 la primera vez; 0 y 0 la segunda), sale con 0 y no toca socios.
- La segunda corrida no cambia filas ni audita; `--as <correo>` atribuye `created_by` y la
  auditoría a esa persona, sin `--as` al usuario técnico (N-15); un `--as` inexistente sale con 2
  sin escribir nada.
- El comando está registrado en `register_ops`.
- `seed` (primer seed) también siembra plantillas y reglas, con la misma atribución; una
  contraseña débil sale con 2 y no siembra nada.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from typer.testing import CliRunner

from app.cli import app
from app.core.audit import AuditEntry
from app.core.config import Settings, reset_settings_cache
from app.core.context import SYSTEM_USER_ID
from app.modules.members.models import Member
from app.modules.notifications.models import NotificationRule, NotificationTemplate
from tests.cli._apoyo import correr
from tests.cli.test_seed_cli import CLAVE, entorno  # noqa: F401  (fixture del `seed`)
from tests.conftest import CLAVE_PRUEBA, limpiar_tras_dos_sesiones
from tests.factories.notifications import DEFAULT_RULES
from tests.factories.users import make_user

Fabrica = async_sessionmaker[AsyncSession]
_runner = CliRunner()


@pytest.fixture
async def fabrica(engine: AsyncEngine) -> AsyncIterator[Fabrica]:
    """Fábrica con commit real; al salir borra lo que quedó (como `dos_sesiones`)."""
    async with engine.connect() as conexion:
        ultima = await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0)))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await limpiar_tras_dos_sesiones(engine, ultima or 0)


async def _conteos(fabrica: Fabrica) -> tuple[int, int]:
    async with fabrica() as sesion:
        plantillas = await sesion.scalar(select(func.count()).select_from(NotificationTemplate))
        reglas = await sesion.scalar(select(func.count()).select_from(NotificationRule))
        return int(plantillas or 0), int(reglas or 0)


async def _autores(fabrica: Fabrica) -> set[Any]:
    async with fabrica() as sesion:
        filas = await sesion.execute(
            text(
                "SELECT created_by FROM notifications.notification_templates "
                "UNION SELECT created_by FROM notifications.notification_rules"
            )
        )
        return {f[0] for f in filas}


async def _auditoria(fabrica: Fabrica) -> list[tuple[str, str, Any]]:
    async with fabrica() as sesion:
        filas = await sesion.execute(
            text(
                "SELECT table_name, action, user_id FROM audit.audit_log "
                "WHERE table_name LIKE 'notifications.%' ORDER BY seq"
            )
        )
        return [(f[0], f[1], f[2]) for f in filas]


async def _admin(fabrica: Fabrica) -> Any:
    async with fabrica() as sesion:
        return await make_user(sesion, role="admin", password=CLAVE_PRUEBA)


def _numeros(salida: str) -> list[int]:
    return [int(n) for n in re.findall(r"\b\d+\b", salida)]


# seed-notifications -----------------------------------------------------------------------------


async def test_la_primera_corrida_siembra_dos_plantillas_y_cinco_reglas(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await _admin(fabrica)
    resultado = correr(
        app,
        ["seed-notifications", "--as", admin.email],
        "dev",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )
    assert resultado.exit_code == 0, resultado.output
    assert _numeros(resultado.output) == [2, 5], resultado.output
    assert await _conteos(fabrica) == (2, len(DEFAULT_RULES))


async def test_la_segunda_corrida_no_cambia_nada_ni_audita(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await _admin(fabrica)
    args = ["seed-notifications", "--as", admin.email]
    correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)
    auditoria = await _auditoria(fabrica)
    segunda = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)
    assert segunda.exit_code == 0, segunda.output
    assert _numeros(segunda.output) == [0, 0], segunda.output
    assert await _conteos(fabrica) == (2, 5)
    assert await _auditoria(fabrica) == auditoria


async def test_as_atribuye_las_filas_y_la_auditoria_a_esa_persona(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await _admin(fabrica)
    correr(
        app,
        ["seed-notifications", "--as", admin.email],
        "dev",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )
    assert await _autores(fabrica) == {admin.id}
    auditoria = await _auditoria(fabrica)
    assert len(auditoria) == 7 and {a for _, a, _ in auditoria} == {"insert"}
    assert {u for _, _, u in auditoria} == {admin.id}


async def test_sin_as_se_atribuye_al_usuario_tecnico(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = correr(
        app, ["seed-notifications"], "dev", base=settings_prueba, monkeypatch=monkeypatch
    )
    assert resultado.exit_code == 0, resultado.output
    assert await _autores(fabrica) == {SYSTEM_USER_ID}
    assert {u for _, _, u in await _auditoria(fabrica)} == {SYSTEM_USER_ID}


async def test_un_as_inexistente_sale_con_2_y_no_escribe_nada(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = correr(
        app,
        ["seed-notifications", "--as", "nadie@apex.co"],
        "dev",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )
    assert resultado.exit_code == 2, resultado.output
    assert await _conteos(fabrica) == (0, 0)
    assert await _auditoria(fabrica) == []


async def test_no_toca_a_los_socios(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    correr(app, ["seed-notifications"], "dev", base=settings_prueba, monkeypatch=monkeypatch)
    async with fabrica() as sesion:
        socios = await sesion.scalar(select(func.count()).select_from(Member))
    assert socios == 0


def test_el_comando_esta_registrado_y_aparece_en_la_ayuda() -> None:
    ayuda = _runner.invoke(app, ["--help"])
    assert ayuda.exit_code == 0 and "seed-notifications" in ayuda.output
    propia = _runner.invoke(app, ["seed-notifications", "--help"])
    assert propia.exit_code == 0 and "--as" in propia.output


# seed (primer seed) ----------------------------------------------------------------------------

pytestmark_seed = pytest.mark.usefixtures("entorno")


@pytestmark_seed
async def test_seed_tambien_siembra_plantillas_y_reglas(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", CLAVE)
    reset_settings_cache()
    try:
        resultado = _runner.invoke(app, ["seed"])
        assert resultado.exit_code == 0, resultado.output
        assert await _conteos(fabrica) == (2, 5)
        assert await _autores(fabrica) == {SYSTEM_USER_ID}
        segundo = _runner.invoke(app, ["seed"])
        assert segundo.exit_code == 0, segundo.output
        assert await _conteos(fabrica) == (2, 5)
    finally:
        async with engine.begin() as conexion:
            for sql in (
                "DELETE FROM notifications.notification_rules",
                "DELETE FROM notifications.notification_templates",
            ):
                await conexion.execute(text(sql))


@pytestmark_seed
async def test_seed_con_contrasena_debil_sale_con_2_y_no_siembra_nada(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "corta")
    reset_settings_cache()
    resultado = _runner.invoke(app, ["seed"])
    assert resultado.exit_code == 2, resultado.output
    assert await _conteos(fabrica) == (0, 0)


@pytestmark_seed
async def test_seed_con_as_atribuye_las_plantillas_a_esa_persona(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with fabrica() as sesion:
        duena = await make_user(
            sesion, role="coach", email="dueno-avisos@apex.co", password=CLAVE_PRUEBA
        )
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", CLAVE)
    reset_settings_cache()
    try:
        resultado = _runner.invoke(app, ["seed", "--as", "dueno-avisos@apex.co"])
        assert resultado.exit_code == 0, resultado.output
        assert await _autores(fabrica) == {duena.id}
    finally:
        async with engine.begin() as conexion:
            for sql in (
                "DELETE FROM notifications.notification_rules",
                "DELETE FROM notifications.notification_templates",
            ):
                await conexion.execute(text(sql))


@pytestmark_seed
async def test_si_la_siembra_de_avisos_falla_el_admin_queda_creado_y_sale_1(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S5-D215: la siembra de avisos va en una segunda transacción; su fallo no revierte al admin"""
    from app.modules.notifications import service
    from app.modules.notifications.exceptions import SeedInProgress

    async def falla(session: object) -> object:
        raise SeedInProgress

    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", CLAVE)
    monkeypatch.setattr(service, "seed_defaults", falla)
    reset_settings_cache()
    resultado = _runner.invoke(app, ["seed"])
    assert resultado.exit_code == 1, resultado.output
    assert "seed-notifications" in resultado.output
    assert CLAVE not in resultado.output
    async with fabrica() as sesion:
        admins = await sesion.scalar(
            text(
                "SELECT count(*) FROM auth.users "
                "WHERE role = 'admin' AND email = 'admin@apex.local'"
            )
        )
    assert admins == 1
    assert await _conteos(fabrica) == (0, 0)
