"""`notify` con el custodio de llaves sellado (US-125; S5-D16, S5-D86, M-4). # Rojo B8

- sellado o inalcanzable al empezar: se genera igual, NO se envía, `details["sellado"] = 1`, el job
  queda `ok` y se emite `crypto_sealed`; los avisos quedan `pending` sin intentos ni descifrado;
- al volver el custodio la corrida siguiente carga el keyring (`try_load` al comienzo) y envía lo
  pendiente;
- `forbidden` y `unwrap_failed` NO se tragan: el job termina en `error`.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.crypto import recovery
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.keyring import configure_keyring
from app.core.jobs import last_run
from app.worker import runner
from app.worker.jobs import JOBS, notify
from tests.core._canales_apoyo import SmtpFalso, con_smtp, instalar_smtp
from tests.core._cripto_apoyo import (
    GrabadoraDeAlertas,
    alertas,
    estado_de_recovery_limpio,
    proveedor_ctl,
)
from tests.factories.fake_provider import ProveedorControlable, inyectar_proveedor
from tests.members.conftest import bus_confirmado  # noqa: F401
from tests.notifications._apoyo_envio import escenario_job, todos

__all__ = ["alertas", "estado_de_recovery_limpio", "proveedor_ctl"]

Fabrica = async_sessionmaker[AsyncSession]
SPEC = next((s for s in JOBS if s.name == "notify"), None)
DESCIFRADOS = "SELECT count(*) FROM crypto.crypto_ops WHERE verb = 'decrypt'"
REVELADOS = "SELECT count(*) FROM audit.audit_log WHERE action = 'reveal'"

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


async def _detalles(fabrica: Fabrica) -> dict[str, Any]:
    async with fabrica() as sesion:
        fila = await last_run(sesion, "notify")
    assert fila is not None
    return {k: v for k, v in fila.details.items() if k != "attempts"}


def _sellar(proveedor: ProveedorControlable, estado: str) -> None:
    proveedor.estado = estado  # type: ignore[assignment]
    configure_keyring(None)
    recovery.reset()


@pytest.mark.parametrize("estado", ["sealed", "unreachable"])
async def test_con_el_custodio_caido_genera_pero_no_envia_y_queda_ok(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    smtp: SmtpFalso,
    proveedor_ctl: ProveedorControlable,
    alertas: GrabadoraDeAlertas,
    estado: str,
) -> None:
    await escenario_job(session_factory)
    _sellar(proveedor_ctl, estado)

    salida = await _correr(session_factory, reloj_worker)

    (fila,) = await todos(session_factory)
    detalles = await _detalles(session_factory)
    assert (salida.result, salida.error_type) == ("ok", None)
    assert (fila["status"], fila["attempts"]) == ("pending", 0)
    assert smtp.conexiones == []
    assert (detalles["sellado"], detalles["generados"], detalles["enviados"]) == (1, 1, 0)
    assert "crypto_sealed" in alertas.codigos


async def test_sellado_no_descifra_ni_audita_ningun_contacto(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    smtp: SmtpFalso,
    proveedor_ctl: ProveedorControlable,
) -> None:
    await escenario_job(session_factory)
    async with session_factory() as sesion:
        antes = await sesion.scalar(text(DESCIFRADOS))
    _sellar(proveedor_ctl, "sealed")

    salida = await _correr(session_factory, reloj_worker)

    async with session_factory() as sesion:
        despues = await sesion.scalar(text(DESCIFRADOS))
        revelados = await sesion.scalar(text(REVELADOS))
    assert salida.result == "ok" and despues == antes and revelados == 0


async def test_sellado_igual_emite_el_resumen_con_enteros(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    smtp: SmtpFalso,
    proveedor_ctl: ProveedorControlable,
    alertas: GrabadoraDeAlertas,
) -> None:
    await escenario_job(session_factory)
    _sellar(proveedor_ctl, "sealed")

    await _correr(session_factory, reloj_worker)

    resumenes = [ctx for codigo, ctx in alertas.enviadas if codigo == "notify_summary"]
    assert len(resumenes) == 1 and resumenes[0]["enviados"] == 0
    assert all(type(v) is int for v in resumenes[0].values())


async def test_al_volver_el_custodio_la_corrida_siguiente_envia_lo_pendiente(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    smtp: SmtpFalso,
    proveedor_ctl: ProveedorControlable,
) -> None:
    await escenario_job(session_factory)
    _sellar(proveedor_ctl, "sealed")
    await _correr(session_factory, reloj_worker)
    proveedor_ctl.estado = "ok"

    segunda = await _correr(session_factory, reloj_worker)

    (fila,) = await todos(session_factory)
    detalles = await _detalles(session_factory)
    assert segunda.result == "ok"
    assert (fila["status"], fila["attempts"]) == ("sent", 1)
    assert detalles["enviados"] == 1 and "sellado" not in detalles
    assert len(smtp.mensajes) == 1


@pytest.mark.parametrize(
    "error",
    [CryptoUnavailable("forbidden"), CryptoError("unwrap_failed", "no se pudo abrir la llave")],
)
async def test_los_errores_de_custodia_que_no_son_sello_hacen_fallar_el_job(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    smtp: SmtpFalso,
    proveedor_ctl: ProveedorControlable,
    error: Exception,
) -> None:
    await escenario_job(session_factory)
    configure_keyring(None)
    recovery.reset()
    proveedor_ctl.error = error

    salida = await _correr(session_factory, reloj_worker)

    (fila,) = await todos(session_factory)
    assert salida.result == "error" and salida.error_type == type(error).__name__
    assert fila["status"] == "pending" and smtp.conexiones == []
