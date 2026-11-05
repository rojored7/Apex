"""Job `notify`: generar, enviar y resumir (US-124, US-125, US-126; S5-D35, S5-D86). # Rojo B8

Se corre por `runner.run_job` con el `JobSpec` real de `JOBS`. Contrato que fija el Rojo:
- `JOBS == [expirations, notify, backup_check]`, `notify` a las 07:00 con `timeout_s = 600`;
- `JobResult.details` solo enteros: `generados`, `ya_renovaron`, `sin_consentimiento`,
  `sin_reglas` (0/1), `enviados`, `fallidos`, `omitidos`, `pendientes`; `sellado` solo si el keyring
  no cargó; `ok = fallidos == 0` (los omitidos no son error);
- una sola `alert("notify_summary", ...)` por corrida, solo enteros;
- al comienzo llama `recovery.try_load(..., create_missing=False, classes=phone+email)`;
- dos corridas el mismo día no duplican avisos ni correos; una corrida `running` vigente de
  `notify` (`claim_run`) impide otra;
- `run_send_only(ctx)` (lo usa el CLI `--send-only`) no genera.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import recovery
from app.core.jobs import claim_run, last_run
from app.worker import runner
from app.worker.jobs import JOBS, notify
from app.worker.runner import JobContext
from app.worker.schedule import DAILY_HOUR, DAILY_MINUTE
from tests.core._canales_apoyo import SmtpFalso, con_smtp, instalar_smtp
from tests.core._cripto_apoyo import (
    GrabadoraDeAlertas,
    alertas,
    estado_de_recovery_limpio,
    proveedor_ctl,
)
from tests.factories.fake_provider import ProveedorControlable, inyectar_proveedor
from tests.factories.plans import make_plan
from tests.members.conftest import bus_confirmado  # noqa: F401
from tests.notifications._apoyo_avisos import HOY, con_membresia, socio
from tests.notifications._apoyo_envio import (
    CORREO,
    aviso_correo,
    escenario_job,
    habilitar_correo,
    regla_correo,
    socio_con_correo,
    todos,
)

__all__ = ["alertas", "estado_de_recovery_limpio", "proveedor_ctl"]

Fabrica = async_sessionmaker[AsyncSession]
SPEC = next((s for s in JOBS if s.name == "notify"), None)

pytestmark = pytest.mark.usefixtures("bus_confirmado", "estado_de_recovery_limpio")


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch, settings_prueba: Settings) -> SmtpFalso:
    ajustes = con_smtp(settings_prueba)
    monkeypatch.setattr(notify, "get_settings", lambda: ajustes)
    return instalar_smtp(monkeypatch)


@pytest.fixture(autouse=True)
def _proveedor(monkeypatch: pytest.MonkeyPatch, proveedor_ctl: ProveedorControlable) -> None:
    inyectar_proveedor(monkeypatch, proveedor_ctl)


async def _correr(fabrica: Fabrica, reloj: FrozenClock) -> runner.JobOutcome:
    assert SPEC is not None, "notify no está en JOBS"
    return await runner.run_job(SPEC, clock=reloj, session_factory=fabrica)


async def _fila(fabrica: Fabrica) -> Any:
    async with fabrica() as sesion:
        return await last_run(sesion, "notify")


# Registro ----------------------------------------------------------------------------------------


def test_notify_esta_entre_expirations_y_backup_check_a_las_siete() -> None:
    assert [(s.name, s.hour, s.minute, s.timeout_s) for s in JOBS] == [
        ("expirations", DAILY_HOUR, DAILY_MINUTE, 900),
        ("notify", DAILY_HOUR, DAILY_MINUTE, 600),
        ("backup_check", DAILY_HOUR, DAILY_MINUTE, 600),
    ]
    assert notify.NAME == "notify"


def test_notify_expone_run_y_run_send_only() -> None:
    assert callable(notify.run) and callable(notify.run_send_only)
    assert SPEC is not None and SPEC.run is notify.run


# Camino feliz ------------------------------------------------------------------------------------


async def test_genera_y_envia_el_correo_del_dia(
    session_factory: Fabrica, reloj_worker: FrozenClock, smtp: SmtpFalso
) -> None:
    await escenario_job(session_factory)

    salida = await _correr(session_factory, reloj_worker)

    (fila,) = await todos(session_factory)
    assert (salida.result, salida.error_type) == ("ok", None)
    assert (fila["status"], fila["attempts"], fila["channel"]) == ("sent", 1, "email")
    (mensaje,) = smtp.mensajes
    assert mensaje["To"] == CORREO
    assert mensaje["Subject"] == fila["rendered_subject"]
    assert fila["rendered_body"] in mensaje.get_content()


async def test_details_son_enteros_con_los_conteos_de_las_tres_fases(
    session_factory: Fabrica, reloj_worker: FrozenClock, smtp: SmtpFalso
) -> None:
    await escenario_job(session_factory)

    await _correr(session_factory, reloj_worker)

    detalles = (await _fila(session_factory)).details
    datos = {k: v for k, v in detalles.items() if k != "attempts"}
    assert datos == {
        "generados": 1,
        "ya_renovaron": 0,
        "sin_consentimiento": 0,
        "sin_reglas": 0,
        "enviados": 1,
        "fallidos": 0,
        "omitidos": 0,
        "pendientes": 0,
    }
    assert all(type(v) is int for v in datos.values())


async def test_sin_reglas_activas_se_marca_y_no_es_un_error(
    session_factory: Fabrica, reloj_worker: FrozenClock, smtp: SmtpFalso
) -> None:
    salida = await _correr(session_factory, reloj_worker)

    detalles = (await _fila(session_factory)).details
    assert salida.result == "ok"
    assert (detalles["sin_reglas"], detalles["generados"], detalles["enviados"]) == (1, 0, 0)
    assert smtp.mensajes == []


async def test_una_segunda_corrida_el_mismo_dia_no_duplica_avisos_ni_correos(
    session_factory: Fabrica, reloj_worker: FrozenClock, smtp: SmtpFalso
) -> None:
    await escenario_job(session_factory)
    await _correr(session_factory, reloj_worker)

    segunda = await _correr(session_factory, reloj_worker)

    detalles = (await _fila(session_factory)).details
    assert segunda.result == "ok"
    assert (detalles["generados"], detalles["enviados"], detalles["pendientes"]) == (0, 0, 0)
    assert len(smtp.mensajes) == 1 and len(await todos(session_factory)) == 1


async def test_cuenta_a_los_socios_sin_consentimiento(
    session_factory: Fabrica, reloj_worker: FrozenClock, smtp: SmtpFalso
) -> None:
    await escenario_job(session_factory)
    async with session_factory() as sesion:
        sin = await socio(sesion, consentido=False, nombre="Ana")
        await con_membresia(
            sesion, sin, await make_plan(sesion, name="Plan Ana"), HOY + timedelta(days=3)
        )

    await _correr(session_factory, reloj_worker)

    detalles = (await _fila(session_factory)).details
    assert (detalles["generados"], detalles["sin_consentimiento"]) == (1, 1)


# Fallos y omisiones ------------------------------------------------------------------------------


async def test_un_fallo_de_smtp_deja_el_job_en_error_y_reintenta_en_la_siguiente_corrida(
    session_factory: Fabrica, reloj_worker: FrozenClock, smtp: SmtpFalso
) -> None:
    await escenario_job(session_factory)
    smtp.fallo = TimeoutError()

    primera = await _correr(session_factory, reloj_worker)
    (fila,) = await todos(session_factory)
    detalles = (await _fila(session_factory)).details
    assert primera.result == "error"
    assert (fila["status"], fila["last_error"], fila["attempts"]) == ("failed", "timeout", 1)
    assert (detalles["fallidos"], detalles["enviados"], detalles["pendientes"]) == (1, 0, 1)

    smtp.fallo = None
    segunda = await _correr(session_factory, reloj_worker)
    (fila,) = await todos(session_factory)
    assert segunda.result == "ok"
    assert (fila["status"], fila["attempts"], fila["last_error"]) == ("sent", 2, None)
    assert len(smtp.mensajes) == 1


async def test_sin_credenciales_smtp_los_avisos_esperan_y_se_avisa_una_vez(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    alertas: GrabadoraDeAlertas,
) -> None:
    """S5-D231: canal habilitado y sin SMTP no es una omisión definitiva: el aviso queda
    `pending` y el equipo recibe UNA alerta `mail_unconfigured` por corrida."""
    monkeypatch.setattr(notify, "get_settings", lambda: settings_prueba)
    smtp = instalar_smtp(monkeypatch)
    await escenario_job(session_factory)

    salida = await _correr(session_factory, reloj_worker)

    (fila,) = await todos(session_factory)
    detalles = (await _fila(session_factory)).details
    assert salida.result == "ok"
    assert (fila["status"], fila["skip_reason"]) == ("pending", None)
    assert (detalles["omitidos"], detalles["enviados"], detalles["pendientes"]) == (0, 0, 1)
    assert alertas.codigos.count("mail_unconfigured") == 1
    assert smtp.conexiones == []


async def test_con_el_canal_apagado_por_el_admin_se_omite_y_no_se_alerta(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    alertas: GrabadoraDeAlertas,
) -> None:
    monkeypatch.setattr(notify, "get_settings", lambda: settings_prueba)
    instalar_smtp(monkeypatch)
    await escenario_job(session_factory)
    async with session_factory() as sesion:
        await sesion.execute(
            text(
                "UPDATE settings.settings_sections SET value = "
                "jsonb_set(value, '{email,enabled}', 'false') WHERE key = 'channels'"
            )
        )
        await sesion.commit()

    await _correr(session_factory, reloj_worker)

    (fila,) = await todos(session_factory)
    assert (fila["status"], fila["skip_reason"]) == ("skipped", "canal_no_configurado")
    assert "mail_unconfigured" not in alertas.codigos


# Resumen y alertas -------------------------------------------------------------------------------


async def test_emite_un_solo_notify_summary_con_enteros_y_sin_datos_personales(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    smtp: SmtpFalso,
    alertas: GrabadoraDeAlertas,
) -> None:
    await escenario_job(session_factory)

    await _correr(session_factory, reloj_worker)

    resumenes = [ctx for codigo, ctx in alertas.enviadas if codigo == "notify_summary"]
    assert len(resumenes) == 1
    (resumen,) = resumenes
    assert {"pendientes", "enviados", "fallidos", "omitidos"} <= set(resumen)
    assert set(resumen) <= {"generados", "pendientes", "enviados", "fallidos", "omitidos"}
    assert resumen["enviados"] == 1 and all(type(v) is int for v in resumen.values())
    todo = json.dumps(alertas.enviadas, default=str)
    for dato in (CORREO, "Lucía", "Gómez"):
        assert dato not in todo


# try_load y reclamo ------------------------------------------------------------------------------


async def test_al_comienzo_llama_try_load_del_worker_sin_crear_llaves(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    smtp: SmtpFalso,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[dict[str, Any]] = []
    original = recovery.try_load

    async def espia(fabrica: Any, settings: Any, **kw: Any) -> Any:
        llamadas.append(kw)
        return await original(fabrica, settings, **kw)

    monkeypatch.setattr(recovery, "try_load", espia)
    await escenario_job(session_factory)

    await _correr(session_factory, reloj_worker)

    assert len(llamadas) == 1
    assert llamadas[0]["create_missing"] is False
    assert set(llamadas[0]["classes"]) == {"member.phone", "member.email"}


async def test_una_corrida_notify_vigente_impide_otra_y_no_envia_nada(
    session_factory: Fabrica, reloj_worker: FrozenClock, smtp: SmtpFalso
) -> None:
    await escenario_job(session_factory)
    async with session_factory() as sesion:
        with actor_scope(SYSTEM_USER_ID):
            reclamo = await claim_run(
                sesion,
                "notify",
                HOY,
                now=reloj_worker.now_utc(),
                stale_after=timedelta(hours=1),
                reclaim_finished=True,
            )
        await sesion.commit()
    assert reclamo is not None

    salida = await _correr(session_factory, reloj_worker)

    assert salida.result == runner.RESULT_RUNNING
    assert smtp.mensajes == [] and await todos(session_factory) == []


async def test_run_send_only_no_genera_pero_envia_lo_pendiente(
    session_factory: Fabrica, reloj_worker: FrozenClock, smtp: SmtpFalso
) -> None:
    await habilitar_correo(session_factory)
    miembro = await socio_con_correo(session_factory)
    await aviso_correo(session_factory, await regla_correo(session_factory), miembro)
    async with session_factory() as sesion:  # lo que `generate` convertiría en un aviso
        otro = await socio(sesion, nombre="Ana")
        await con_membresia(
            sesion, otro, await make_plan(sesion, name="Plan Ana"), HOY + timedelta(days=3)
        )
    ctx = JobContext(session_factory, HOY, reloj_worker)

    resultado = await notify.run_send_only(ctx)

    assert resultado.ok is True
    assert resultado.details["enviados"] == 1
    assert "generados" not in resultado.details
    assert len(smtp.mensajes) == 1 and len(await todos(session_factory)) == 1
