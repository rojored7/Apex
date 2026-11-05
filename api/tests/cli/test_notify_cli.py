"""`python -m app.cli notify --generate-only [--as <correo>]` (S5-B7, US-124; S5-D26, S5-D97).
# Rojo B7

Comando provisional de B7 (B8 le suma `--send-only` y el reclamo del job):
- `--generate-only` llama `notifications.service.generate_today` con el "hoy" de Bogotá del reloj
  (a las 23:30 locales todavía es el día anterior; pasada la medianoche local, el siguiente) y
  confirma por lote; sin `--generate-only` sale con 2 sin tocar nada;
- imprime una línea `notify: generados N, ya renovaron N, sin consentimiento N, sin reglas
  sí|no`, sin UUID, nombres ni teléfonos; sale con 0;
- idempotente: la segunda corrida da `generados 0` y no cambia filas;
- `--as <correo>` atribuye `created_by` y la auditoría a esa persona; sin `--as`, al usuario
  técnico; un `--as` inexistente sale con 2 sin escribir nada;
- con `ENV=production` exige `--as` y rechaza `--db-timeouts off` (salida 2);
- el comando está registrado en `register_ops` y aparece en la ayuda.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from typer.testing import CliRunner

from app.cli import app
from app.core.audit import AuditEntry
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID
from tests.cli._apoyo import correr
from tests.conftest import CLAVE_PRUEBA, limpiar_tras_dos_sesiones
from tests.factories.notifications import EXPIRED
from tests.factories.plans import make_plan
from tests.factories.users import make_user
from tests.memberships.conftest import bus_confirmado  # noqa: F401
from tests.notifications._apoyo_avisos import (
    HOY,
    con_membresia,
    regla_aislada,
    reglas_por_defecto,
    socio,
)

Fabrica = async_sessionmaker[AsyncSession]
_runner = CliRunner()
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

pytestmark = pytest.mark.usefixtures("bus_confirmado", "reloj")


@pytest.fixture
async def fabrica(engine: AsyncEngine) -> AsyncIterator[Fabrica]:
    """Fábrica con commit real; al salir borra lo que quedó (como `dos_sesiones`)."""
    async with engine.connect() as conexion:
        ultima = await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0)))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await limpiar_tras_dos_sesiones(engine, ultima or 0)


async def _escenario(fabrica: Fabrica, fin: date = HOY + timedelta(days=3)) -> None:
    """Reglas por defecto y un socio consentido con una membresía que termina en `fin`."""
    async with fabrica() as sesion:
        await reglas_por_defecto(sesion)
        plan = await make_plan(sesion)
        await con_membresia(sesion, await socio(sesion), plan, fin)


async def _admin(fabrica: Fabrica) -> Any:
    async with fabrica() as sesion:
        return await make_user(sesion, role="admin", password=CLAVE_PRUEBA)


async def _avisos(fabrica: Fabrica) -> list[tuple[date, int]]:
    async with fabrica() as sesion:
        filas = await sesion.execute(
            text(
                "SELECT n.target_date, r.offset_days FROM notifications.notifications n "
                "JOIN notifications.notification_rules r ON r.id = n.rule_id "
                "ORDER BY n.target_date, r.offset_days"
            )
        )
        return [(f[0], f[1]) for f in filas]


async def _autores(fabrica: Fabrica) -> tuple[set[Any], set[Any]]:
    async with fabrica() as sesion:
        creadores = await sesion.execute(text("SELECT created_by FROM notifications.notifications"))
        actores = await sesion.execute(
            text(
                "SELECT user_id FROM audit.audit_log "
                "WHERE table_name = 'notifications.notifications'"
            )
        )
        return {f[0] for f in creadores}, {f[0] for f in actores}


def _numeros(salida: str) -> list[int]:
    return [int(n) for n in re.findall(r"(?:generados|renovaron|consentimiento) (\d+)", salida)]


async def test_genera_los_avisos_del_dia_e_imprime_solo_conteos(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _escenario(fabrica)
    admin = await _admin(fabrica)

    resultado = correr(
        app,
        ["notify", "--generate-only", "--as", admin.email],
        "dev",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )

    assert resultado.exit_code == 0, resultado.output
    assert _numeros(resultado.output) == [1, 0, 0], resultado.output
    assert "sin reglas no" in resultado.output
    assert not UUID_RE.search(resultado.output) and "Lucía" not in resultado.output
    assert await _avisos(fabrica) == [(HOY, -3)]


async def test_la_segunda_corrida_no_cambia_nada(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _escenario(fabrica)
    args = ["notify", "--generate-only"]
    correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)
    antes = await _avisos(fabrica)

    segunda = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)

    assert segunda.exit_code == 0, segunda.output
    assert _numeros(segunda.output) == [0, 0, 0], segunda.output
    assert await _avisos(fabrica) == antes


async def test_sin_generate_only_sale_con_2_y_no_escribe(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _escenario(fabrica)
    resultado = correr(app, ["notify"], "dev", base=settings_prueba, monkeypatch=monkeypatch)
    assert resultado.exit_code == 2, resultado.output
    assert await _avisos(fabrica) == []


async def test_sin_reglas_activas_lo_dice_y_sale_con_0(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = correr(
        app, ["notify", "--generate-only"], "dev", base=settings_prueba, monkeypatch=monkeypatch
    )
    assert resultado.exit_code == 0, resultado.output
    assert "sin reglas sí" in resultado.output


async def test_cuenta_a_los_socios_sin_consentimiento_y_a_los_que_ya_renovaron(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with fabrica() as sesion:
        await regla_aislada(sesion, "membership_expired", 1, plantilla=EXPIRED)
        plan = await make_plan(sesion)
        ayer = HOY - timedelta(days=1)
        await con_membresia(sesion, await socio(sesion, consentido=False), plan, ayer)
        renovo = await socio(sesion)
        await con_membresia(sesion, renovo, plan, ayer)
        await con_membresia(sesion, renovo, plan, HOY + timedelta(days=29))
    resultado = correr(
        app, ["notify", "--generate-only"], "dev", base=settings_prueba, monkeypatch=monkeypatch
    )
    assert resultado.exit_code == 0, resultado.output
    assert _numeros(resultado.output) == [0, 1, 1], resultado.output


# Atribución -------------------------------------------------------------------------------------


async def test_as_atribuye_las_filas_y_la_auditoria_a_esa_persona(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _escenario(fabrica)
    admin = await _admin(fabrica)
    correr(
        app,
        ["notify", "--generate-only", "--as", admin.email],
        "dev",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )
    assert await _autores(fabrica) == ({admin.id}, {admin.id})


async def test_sin_as_se_atribuye_al_usuario_tecnico(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _escenario(fabrica)
    correr(app, ["notify", "--generate-only"], "dev", base=settings_prueba, monkeypatch=monkeypatch)
    assert await _autores(fabrica) == ({SYSTEM_USER_ID}, {SYSTEM_USER_ID})


async def test_un_as_inexistente_sale_con_2_y_no_escribe(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _escenario(fabrica)
    resultado = correr(
        app,
        ["notify", "--generate-only", "--as", "nadie@apex.co"],
        "dev",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )
    assert resultado.exit_code == 2, resultado.output
    assert await _avisos(fabrica) == []


# El día de Bogotá ---------------------------------------------------------------------------------


async def test_usa_el_dia_de_bogota_y_no_el_utc(
    fabrica: Fabrica,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    reloj: FrozenClock,
) -> None:
    """Fin el 22: la regla `Vence hoy` toca el 22. A las 04:30Z del 22 son las 23:30 del 21 en
    Bogotá (todavía no); a las 05:30Z ya es 22 y se genera."""
    fin = HOY + timedelta(days=1)
    async with fabrica() as sesion:
        await regla_aislada(sesion, "membership_expiring", 0)
        await con_membresia(sesion, await socio(sesion), await make_plan(sesion), fin)
    args = ["notify", "--generate-only"]

    reloj.advance(hours=13, minutes=30)
    antes = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)
    avisos_antes = await _avisos(fabrica)
    reloj.advance(hours=1)
    despues = correr(app, args, "dev", base=settings_prueba, monkeypatch=monkeypatch)

    assert antes.exit_code == 0 and _numeros(antes.output)[0] == 0, antes.output
    assert avisos_antes == []
    assert _numeros(despues.output)[0] == 1, despues.output
    assert await _avisos(fabrica) == [(fin, 0)]


# Producción -------------------------------------------------------------------------------------


async def test_en_produccion_exige_as(
    fabrica: Fabrica,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _escenario(fabrica)
    admin = await _admin(fabrica)

    sin = correr(
        app,
        ["notify", "--generate-only"],
        "production",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )
    con = correr(
        app,
        ["notify", "--generate-only", "--as", admin.email],
        "production",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )

    assert sin.exit_code == 2, sin.output
    assert await _avisos(fabrica) == [(HOY, -3)] and con.exit_code == 0, con.output


async def test_en_produccion_rechaza_db_timeouts_off(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _escenario(fabrica)
    admin = await _admin(fabrica)
    resultado = correr(
        app,
        ["--db-timeouts", "off", "notify", "--generate-only", "--as", admin.email],
        "production",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )
    assert resultado.exit_code == 2, resultado.output
    assert await _avisos(fabrica) == []


def test_el_comando_esta_registrado_y_aparece_en_la_ayuda() -> None:
    ayuda = _runner.invoke(app, ["--help"])
    assert ayuda.exit_code == 0 and "notify" in ayuda.output
    propia = _runner.invoke(app, ["notify", "--help"])
    assert propia.exit_code == 0
    assert "--generate-only" in propia.output and "--as" in propia.output
