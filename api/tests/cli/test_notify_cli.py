"""`python -m app.cli notify --generate-only [--as <correo>]` (S5-B7, US-124; S5-D26, S5-D97).
# Rojo B7

Comando de B7 (B8 le suma `--send-only` y ambas fases; ver al final, «Rojo B8»):
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


async def test_generate_only_y_send_only_juntos_salen_con_2_y_no_escriben(
    fabrica: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _escenario(fabrica)
    resultado = correr(
        app,
        ["notify", "--generate-only", "--send-only"],
        "dev",
        base=settings_prueba,
        monkeypatch=monkeypatch,
    )
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


# Rojo B8: envío (`--send-only`) y ambas fases -----------------------------------------------------
# Contrato: sin flags corre generar + enviar; `--send-only` solo envía; ambos flags juntos salen con
# 2. Las dos formas reclaman `notify` por `worker.runner.run_job` (el CLI no importa `core.jobs`):
# si hay una corrida `running` vigente salen con 3 sin enviar; si el job falla (SMTP) salen con 1.
# La salida es `notify: ...` con conteos (`enviados N, fallidos N, omitidos N`), sin UUID, correos
# ni nombres. `--as` es obligatorio en producción y debe existir. El CLI vive en < 150 líneas.

from pathlib import Path  # noqa: E402

from app.core.context import actor_scope  # noqa: E402
from app.core.jobs import claim_run  # noqa: E402
from app.worker.jobs import notify as notify_job  # noqa: E402
from tests.core._canales_apoyo import SmtpFalso, con_smtp, instalar_smtp  # noqa: E402
from tests.notifications._apoyo_envio import (  # noqa: E402
    CORREO,
    aviso_correo,
    escenario_job,
    habilitar_correo,
    regla_correo,
    socio_con_correo,
    todos,
)

NOTIFY_CLI = Path(__file__).resolve().parents[2] / "src" / "app" / "cli_ops" / "notify.py"


@pytest.fixture
def envio(settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch) -> tuple[SmtpFalso, Settings]:
    """SMTP falso y `Settings` con credenciales; el job las lee por `notify_job.get_settings`."""
    ajustes = con_smtp(settings_prueba)
    monkeypatch.setattr(notify_job, "get_settings", lambda: ajustes)
    return instalar_smtp(monkeypatch), ajustes


def _enviados(salida: str) -> list[int]:
    return [int(n) for n in re.findall(r"(?:enviados|fallidos|omitidos) (\d+)", salida)]


async def test_send_only_envia_lo_pendiente_y_no_genera(
    fabrica: Fabrica, envio: tuple[SmtpFalso, Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    smtp, ajustes = envio
    await habilitar_correo(fabrica)
    miembro = await socio_con_correo(fabrica)
    await aviso_correo(fabrica, await regla_correo(fabrica), miembro)
    otra = await socio_con_correo(
        fabrica, "ana@example.com", nombre="Ana"
    )  # `generate` la avisaría
    async with fabrica() as sesion:
        plan = await make_plan(sesion, name="Plan Ana")
        await con_membresia(sesion, otra, plan, HOY + timedelta(days=3))
    antes = len(await todos(fabrica))

    resultado = correr(app, ["notify", "--send-only"], "dev", base=ajustes, monkeypatch=monkeypatch)

    assert resultado.exit_code == 0, resultado.output
    assert _enviados(resultado.output) == [1, 0, 0], resultado.output
    assert len(await todos(fabrica)) == antes and len(smtp.mensajes) == 1


async def test_sin_flags_genera_y_envia(
    fabrica: Fabrica, envio: tuple[SmtpFalso, Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    smtp, ajustes = envio
    await escenario_job(fabrica)

    resultado = correr(app, ["notify"], "dev", base=ajustes, monkeypatch=monkeypatch)

    (fila,) = await todos(fabrica)
    assert resultado.exit_code == 0, resultado.output
    assert "generados 1" in resultado.output and "enviados 1" in resultado.output
    assert fila["status"] == "sent" and len(smtp.mensajes) == 1


async def test_la_salida_del_envio_no_lleva_uuid_correo_ni_nombre(
    fabrica: Fabrica, envio: tuple[SmtpFalso, Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ajustes = envio
    await escenario_job(fabrica)

    resultado = correr(app, ["notify"], "dev", base=ajustes, monkeypatch=monkeypatch)

    assert resultado.exit_code == 0, resultado.output
    texto = resultado.output
    assert not UUID_RE.search(texto)
    assert CORREO not in texto and "Lucía" not in texto


async def test_con_una_corrida_notify_vigente_sale_con_3_y_no_envia(
    fabrica: Fabrica,
    envio: tuple[SmtpFalso, Settings],
    monkeypatch: pytest.MonkeyPatch,
    reloj: FrozenClock,
) -> None:
    smtp, ajustes = envio
    await escenario_job(fabrica)
    async with fabrica() as sesion:
        with actor_scope(SYSTEM_USER_ID):
            await claim_run(
                sesion,
                "notify",
                HOY,
                now=reloj.now_utc(),
                stale_after=timedelta(hours=1),
                reclaim_finished=True,
            )
            await sesion.commit()

    for args in (["notify"], ["notify", "--send-only"]):
        resultado = correr(app, args, "dev", base=ajustes, monkeypatch=monkeypatch)
        assert resultado.exit_code == 3, (args, resultado.output)

    assert smtp.mensajes == [] and await todos(fabrica) == []


async def test_si_el_smtp_falla_sale_con_1_y_cuenta_el_fallo(
    fabrica: Fabrica, envio: tuple[SmtpFalso, Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    smtp, ajustes = envio
    await escenario_job(fabrica)
    smtp.fallo = TimeoutError()

    resultado = correr(app, ["notify"], "dev", base=ajustes, monkeypatch=monkeypatch)

    (fila,) = await todos(fabrica)
    assert resultado.exit_code == 1, resultado.output
    assert "fallidos 1" in resultado.output
    assert (fila["status"], fila["last_error"]) == ("failed", "timeout")


async def test_send_only_en_produccion_exige_as_y_no_envia(
    fabrica: Fabrica, envio: tuple[SmtpFalso, Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    smtp, ajustes = envio
    await escenario_job(fabrica)

    sin = correr(
        app, ["notify", "--send-only"], "production", base=ajustes, monkeypatch=monkeypatch
    )

    assert sin.exit_code == 2, sin.output
    assert smtp.mensajes == []


async def test_send_only_con_un_as_inexistente_sale_con_2_y_no_envia(
    fabrica: Fabrica, envio: tuple[SmtpFalso, Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    smtp, ajustes = envio
    await escenario_job(fabrica)

    resultado = correr(
        app,
        ["notify", "--send-only", "--as", "nadie@apex.co"],
        "dev",
        base=ajustes,
        monkeypatch=monkeypatch,
    )

    assert resultado.exit_code == 2, resultado.output
    assert smtp.mensajes == []


def test_la_ayuda_lista_send_only_y_el_archivo_tiene_menos_de_150_lineas() -> None:
    propia = _runner.invoke(app, ["notify", "--help"])
    assert "--send-only" in propia.output
    assert len(NOTIFY_CLI.read_text(encoding="utf-8").splitlines()) < 150
