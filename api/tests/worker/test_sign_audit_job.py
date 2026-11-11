"""Job `sign_audit`: firma la cadena de auditoría (US-141; S6-D8, D9, D42, D60, D100). Rojo A2.

Se corre por `runner.run_job` con el `JobSpec` real de `JOBS` y commit real (`llaves_de_firma`:
fila `sign` `local` ya en la base y keyring del proceso vacío). Contrato que fija el Rojo:
- `details` solo enteros de `DETAIL_KEYS`: `firmadas`, `nada_nuevo`, `reintentos`, `sellado`,
  `atrasada`, `cadena_rota`; sin novedades `nada_nuevo = 1` y nada que alertar;
- custodio sellado: `RETRY_WAITS_S = (2, 4, 8)` por `sign_audit.sleep`, `JobResult(ok=False)`,
  `reintentos = 3`, `sellado = 1` y una `alert("audit_sign_failed", job, result, error_type,
  attempts=3)`; nunca firma a medias;
- `signature_unverifiable` (S6-D100): un fallo sin reintento útil (sin esperas, `attempts = 1`);
- «atrasada» (más de 48 h con filas sin firmar, contra `current_clock()`): una sola
  `alert("audit_sign_late", job, age_h)` por corrida;
- cadena rota (H-1): `ok=False`, `cadena_rota = 1`, `alert("audit_chain_broken", through_seq)`,
  ninguna fila ni reintento;
- el keyring cargado contiene solo `audit.signature` y `unwrap` no se llama (S6-D42);
- cada intento acota el tiempo (`ATTEMPT_TIMEOUT_S`) y libera el candado `4_270_004`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.crypto import recovery
from app.core.crypto.keyring import configure_keyring, current_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.jobs import DETAIL_KEYS, last_run
from app.worker import runner
from app.worker.jobs import JOBS, sign_audit
from tests.core._cripto_apoyo import (
    GrabadoraDeAlertas,
    alertas,
    estado_de_recovery_limpio,
    proveedor_ctl,
)
from tests.factories.fake_provider import ProveedorControlable, inyectar_proveedor
from tests.factories.firma_real import (
    alterar,
    cadena,
    candado_libre,
    firmas,
    llaves_de_firma,
    ops_de_firma,
)

__all__ = ["alertas", "estado_de_recovery_limpio", "proveedor_ctl"]

Fabrica = async_sessionmaker[AsyncSession]
SPEC = next((s for s in JOBS if s.name == "sign_audit"), None)
HORAS_ATRASO = 49

pytestmark = pytest.mark.usefixtures("estado_de_recovery_limpio")


class EsperaFalsa:
    """Sustituye `sign_audit.sleep`: anota las esperas y puede ejecutar un gancho en cada una."""

    def __init__(self) -> None:
        self.esperas: list[float] = []
        self.al_esperar: Any = None

    async def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)
        if self.al_esperar is not None:
            self.al_esperar(len(self.esperas))


@pytest.fixture
def espera_falsa(monkeypatch: pytest.MonkeyPatch) -> EsperaFalsa:
    falsa = EsperaFalsa()
    monkeypatch.setattr(sign_audit, "sleep", falsa)
    return falsa


@pytest.fixture(autouse=True)
def _proveedor(monkeypatch: pytest.MonkeyPatch, proveedor_ctl: ProveedorControlable) -> None:
    inyectar_proveedor(monkeypatch, proveedor_ctl)


@pytest.fixture(autouse=True)
def _ajustes(monkeypatch: pytest.MonkeyPatch, settings_prueba: Settings) -> None:
    """Error objetivo del Rojo (corregido por el Verde): el job lee `get_settings()` y la prueba no
    daba `.env`; se inyecta `settings_prueba`, igual que `test_notify_job`."""
    monkeypatch.setattr(sign_audit, "get_settings", lambda: settings_prueba)


@pytest.fixture
def custodio_sellado(proveedor_ctl: ProveedorControlable) -> ProveedorControlable:
    """El custodio sellado antes de que el job cargue su keyring."""
    proveedor_ctl.estado = "sealed"
    configure_keyring(None)
    recovery.reset()
    return proveedor_ctl


@pytest.fixture
async def base(
    session_factory: Fabrica, engine: AsyncEngine, proveedor_local: LocalFileProvider
) -> AsyncIterator[Fabrica]:
    async with llaves_de_firma(engine, proveedor_local):
        yield session_factory


async def _correr(fabrica: Fabrica, reloj: FrozenClock) -> runner.JobOutcome:
    assert SPEC is not None, "sign_audit no está en JOBS"
    return await runner.run_job(SPEC, clock=reloj, session_factory=fabrica)


async def _detalles(fabrica: Fabrica) -> dict[str, Any]:
    async with fabrica() as sesion:
        fila = await last_run(sesion, "sign_audit")
    assert fila is not None
    return {k: v for k, v in fila.details.items() if k != "attempts"}


def _de_firma(alertas: GrabadoraDeAlertas) -> list[tuple[str, dict[str, object]]]:
    return [(c, x) for c, x in alertas.enviadas if c.startswith("audit_")]


# Registro ----------------------------------------------------------------------------------------


def test_sign_audit_esta_registrado_con_sus_constantes() -> None:
    assert SPEC is not None and SPEC.run is sign_audit.run
    assert (SPEC.hour, SPEC.minute, SPEC.timeout_s) == (7, 0, 300)
    assert sign_audit.NAME == "sign_audit"
    assert sign_audit.CRYPTO_CLASSES == frozenset({"audit.signature"})
    assert sign_audit.RETRY_WAITS_S == (2, 4, 8)
    assert SPEC.crypto_classes == frozenset({"audit.signature"})
    assert sign_audit.ATTEMPT_TIMEOUT_S <= 10


def test_el_job_no_lee_el_reloj_directo() -> None:
    fuente = Path(sign_audit.__file__).read_text(encoding="utf-8")
    for prohibido in ("datetime.now", "datetime.utcnow", "func.now(", "date.today"):
        assert prohibido not in fuente, prohibido


# Camino feliz ------------------------------------------------------------------------------------


async def test_firma_la_cadena_y_cuenta_en_enteros(
    base: Fabrica,
    reloj_worker: FrozenClock,
    alertas: GrabadoraDeAlertas,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    _, ultimo = await cadena(base, 5)

    salida = await _correr(base, reloj_worker)

    (fila,) = await firmas(base)
    detalles = await _detalles(base)
    assert (salida.result, salida.error_type) == ("ok", None)
    assert fila["through_seq"] == ultimo and fila["algorithm"] == "Ed25519"
    assert detalles["firmadas"] == 1 and detalles.get("nada_nuevo", 0) == 0
    assert set(detalles) <= DETAIL_KEYS and all(type(v) is int for v in detalles.values())
    assert _de_firma(alertas) == []
    # ni la firma ni el hash de la cadena llegan a los logs ni a las alertas
    texto = caplog.text + repr(alertas.enviadas)
    assert "apx1." not in texto and fila["hash"] not in texto


async def test_sin_novedades_cuenta_nada_nuevo_y_no_alerta(
    base: Fabrica, reloj_worker: FrozenClock, alertas: GrabadoraDeAlertas
) -> None:
    await cadena(base, 4)
    await _correr(base, reloj_worker)

    segunda = await _correr(base, reloj_worker)

    detalles = await _detalles(base)
    assert segunda.result == "ok"
    assert detalles["nada_nuevo"] == 1 and detalles.get("firmadas", 0) == 0
    assert len(await firmas(base)) == 1, "dos corridas el mismo día no duplican la firma"
    assert _de_firma(alertas) == []


async def test_sin_filas_en_la_cadena_tampoco_falla(
    base: Fabrica, reloj_worker: FrozenClock, alertas: GrabadoraDeAlertas
) -> None:
    salida = await _correr(base, reloj_worker)

    assert salida.result == "ok" and await firmas(base) == []
    assert _de_firma(alertas) == []


async def test_el_keyring_del_job_contiene_solo_audit_signature_y_no_abre_ninguna_dek(
    base: Fabrica, reloj_worker: FrozenClock, proveedor_ctl: ProveedorControlable
) -> None:
    await cadena(base, 3)

    await _correr(base, reloj_worker)

    clases = {llave.data_class for llave in current_keyring().keys()}
    assert clases == {"audit.signature"}, clases
    assert proveedor_ctl.unwrap_calls == 0


# Custodio sellado --------------------------------------------------------------------------------


async def test_con_el_custodio_sellado_reintenta_2_4_8_y_falla_sin_firmar(
    base: Fabrica,
    reloj_worker: FrozenClock,
    espera_falsa: EsperaFalsa,
    custodio_sellado: ProveedorControlable,
    alertas: GrabadoraDeAlertas,
) -> None:
    await cadena(base, 4)

    salida = await _correr(base, reloj_worker)

    detalles = await _detalles(base)
    assert espera_falsa.esperas == [2, 4, 8]
    assert salida.result == "error"
    assert (detalles["reintentos"], detalles["sellado"]) == (3, 1)
    assert detalles.get("firmadas", 0) == 0 and await firmas(base) == []
    (fallo,) = [x for c, x in alertas.enviadas if c == "audit_sign_failed"]
    assert fallo["job"] == "sign_audit" and fallo["result"] == "error" and fallo["attempts"] == 3
    assert isinstance(fallo["error_type"], str) and fallo["error_type"].isidentifier()
    assert set(fallo) == {"job", "result", "error_type", "attempts"}


async def test_si_el_custodio_vuelve_durante_los_reintentos_firma_y_cuenta_los_reintentos(
    base: Fabrica,
    reloj_worker: FrozenClock,
    espera_falsa: EsperaFalsa,
    custodio_sellado: ProveedorControlable,
    alertas: GrabadoraDeAlertas,
) -> None:
    await cadena(base, 4)

    def al_esperar(n: int) -> None:
        if n == 2:
            custodio_sellado.estado = "ok"

    espera_falsa.al_esperar = al_esperar

    salida = await _correr(base, reloj_worker)

    detalles = await _detalles(base)
    assert espera_falsa.esperas == [2, 4]
    assert salida.result == "ok" and detalles["firmadas"] == 1 and detalles["reintentos"] == 2
    assert len(await firmas(base)) == 1
    assert [c for c, _ in alertas.enviadas if c == "audit_sign_failed"] == []


async def test_el_fallo_por_sello_libera_el_candado_de_la_firma(
    base: Fabrica,
    engine: AsyncEngine,
    reloj_worker: FrozenClock,
    espera_falsa: EsperaFalsa,
    custodio_sellado: ProveedorControlable,
) -> None:
    await cadena(base, 2)

    await _correr(base, reloj_worker)

    assert await candado_libre(engine)


# Firma que no verifica (S6-D100) ---------------------------------------------------------------


async def test_una_firma_que_no_verifica_falla_el_intento_sin_reintento_util(
    base: Fabrica,
    reloj_worker: FrozenClock,
    espera_falsa: EsperaFalsa,
    proveedor_ctl: ProveedorControlable,
    alertas: GrabadoraDeAlertas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def firma_mala(key_ref: str, data: bytes) -> bytes:
        return bytes(64)

    monkeypatch.setattr(proveedor_ctl, "sign", firma_mala)
    await cadena(base, 3)

    salida = await _correr(base, reloj_worker)

    assert salida.result == "error" and espera_falsa.esperas == []
    assert await firmas(base) == []
    (fallo,) = [x for c, x in alertas.enviadas if c == "audit_sign_failed"]
    assert fallo["error_type"] == "signature_unverifiable" and fallo["attempts"] == 1
    assert ("sign", "error") in await ops_de_firma(base)


# Tiempo máximo por intento y candado ------------------------------------------------------------


async def test_un_intento_colgado_vence_hace_rollback_y_libera_el_candado(
    base: Fabrica,
    engine: AsyncEngine,
    reloj_worker: FrozenClock,
    espera_falsa: EsperaFalsa,
    proveedor_ctl: ProveedorControlable,
    alertas: GrabadoraDeAlertas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def colgado(key_ref: str, data: bytes) -> bytes:
        await asyncio.sleep(30)
        return b""

    monkeypatch.setattr(proveedor_ctl, "sign", colgado)
    monkeypatch.setattr(sign_audit, "ATTEMPT_TIMEOUT_S", 0.2)
    await cadena(base, 3)

    salida = await asyncio.wait_for(_correr(base, reloj_worker), timeout=20)

    assert salida.result == "error" and await firmas(base) == []
    assert await candado_libre(engine)
    assert any(c == "audit_sign_failed" for c, _ in alertas.enviadas)


# Firma atrasada ----------------------------------------------------------------------------------


async def test_con_filas_sin_firmar_de_hace_49_horas_alerta_una_sola_vez(
    base: Fabrica,
    reloj_worker: FrozenClock,
    espera_falsa: EsperaFalsa,
    custodio_sellado: ProveedorControlable,
    alertas: GrabadoraDeAlertas,
) -> None:
    viejo = FrozenClock(reloj_worker.now_utc() - timedelta(hours=HORAS_ATRASO))
    await cadena(base, 3, reloj=viejo)

    await _correr(base, reloj_worker)

    tardes = [x for c, x in alertas.enviadas if c == "audit_sign_late"]
    assert len(tardes) == 1, "una sola alerta por corrida aunque haya tres reintentos"
    assert tardes[0]["job"] == "sign_audit"
    assert type(tardes[0]["age_h"]) is int and tardes[0]["age_h"] >= HORAS_ATRASO
    assert (await _detalles(base))["atrasada"] == 1


async def test_con_filas_sin_firmar_de_hace_47_horas_no_alerta_atraso(
    base: Fabrica,
    reloj_worker: FrozenClock,
    espera_falsa: EsperaFalsa,
    custodio_sellado: ProveedorControlable,
    alertas: GrabadoraDeAlertas,
) -> None:
    viejo = FrozenClock(reloj_worker.now_utc() - timedelta(hours=47))
    await cadena(base, 3, reloj=viejo)

    await _correr(base, reloj_worker)

    assert [c for c, _ in alertas.enviadas if c == "audit_sign_late"] == []
    assert (await _detalles(base)).get("atrasada", 0) == 0


# Cadena rota (H-1) -------------------------------------------------------------------------------


async def test_con_la_cadena_rota_no_firma_no_reintenta_y_alerta_el_seq(
    base: Fabrica,
    reloj_worker: FrozenClock,
    espera_falsa: EsperaFalsa,
    alertas: GrabadoraDeAlertas,
) -> None:
    primero, _ = await cadena(base, 6)
    roto = primero + 2
    await alterar(base, roto)

    salida = await _correr(base, reloj_worker)

    detalles = await _detalles(base)
    assert salida.result == "error" and espera_falsa.esperas == []
    assert detalles["cadena_rota"] == 1 and detalles.get("firmadas", 0) == 0
    assert await firmas(base) == []
    (rota,) = [x for c, x in alertas.enviadas if c == "audit_chain_broken"]
    assert rota["through_seq"] == roto and rota["job"] == "sign_audit"
    assert type(rota["through_seq"]) is int


# Error de base del intento (revisión de seguridad L2) ---------------------------------------------


async def test_un_error_de_base_en_el_intento_se_reintenta_y_alerta_db_timeout(
    base: Fabrica,
    reloj_worker: FrozenClock,
    espera_falsa: EsperaFalsa,
    alertas: GrabadoraDeAlertas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.exc import DBAPIError

    async def cancelada(*_a: object, **_k: object) -> None:
        raise DBAPIError(
            "SELECT 1", None, Exception("canceling statement due to statement timeout")
        )

    monkeypatch.setattr(sign_audit, "limit_statement_time", cancelada)
    await cadena(base, 3)

    salida = await _correr(base, reloj_worker)

    assert salida.result == "error" and salida.error_type is None
    assert espera_falsa.esperas == [2, 4, 8]
    (fallo,) = [x for c, x in alertas.enviadas if c == "audit_sign_failed"]
    assert fallo["error_type"] == "db_timeout" and fallo["attempts"] == 3
    assert (await _detalles(base))["reintentos"] == 3
    assert await firmas(base) == []
