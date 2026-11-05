"""Sondeo y recuperación del keyring (S5-B3, US-136; S5-D16, S5-D70, M-4, M-6). Rojo B3.

- `try_load` con el proveedor sano, sellado o inalcanzable; sin `INSERT` cuando `create_missing` es
  falso (worker); `unwrap_failed` se propaga y no crea llaves; `classes` limita lo que se abre;
- `poll_forever`: espera `CRYPTO_RECOVERY_POLL_S` (20 s) entre intentos, recupera sin reiniciar,
  una línea de log y una alerta por transición (`crypto_sealed`, `crypto_recovered`);
- el `lifespan` lanza el sondeo cuando arranca sellado y lo cancela en su `finally`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.crypto import recovery
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.keyring import configure_keyring, current_keyring
from app.core.crypto.provider import configure_provider
from app.core.crypto.registry import encrypting_specs, indexing_specs, signing_specs
from app.main import create_app
from tests.core._cripto_apoyo import (
    GrabadoraDeAlertas,
    alertas,
    base_con_llaves,
    base_sin_llaves,
    contar_llaves,
    estado_de_recovery_limpio,
    proveedor_ctl,
)
from tests.factories.fake_provider import ProveedorControlable, inyectar_proveedor

__all__ = [
    "alertas",
    "base_con_llaves",
    "base_sin_llaves",
    "estado_de_recovery_limpio",
    "proveedor_ctl",
]

Fabrica = async_sessionmaker[AsyncSession]
POLL_S = 20
LLAVES_DEL_BUS = len(encrypting_specs()) + len(indexing_specs()) + len(signing_specs())
PHONE_Y_EMAIL = frozenset({"member.phone", "member.email"})


@pytest.fixture(autouse=True)
def _sin_proceso_previo() -> None:
    configure_keyring(None)


# try_load ---------------------------------------------------------------------------------------


async def test_try_load_del_api_con_proveedor_sano_crea_carga_y_devuelve_ok(
    base_sin_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
) -> None:
    configure_provider(proveedor_ctl)
    estado = await recovery.try_load(base_sin_llaves, settings_prueba, create_missing=True)
    assert estado == "ok"
    assert recovery.is_loaded() and recovery.current_state() == "ok"
    assert await contar_llaves(base_sin_llaves) == LLAVES_DEL_BUS
    assert current_keyring().keys()


@pytest.mark.parametrize("estado_proveedor", ["sealed", "unreachable"])
async def test_try_load_con_proveedor_caido_devuelve_el_estado_sin_crear_nada(
    base_sin_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    estado_proveedor: str,
) -> None:
    proveedor_ctl.estado = estado_proveedor  # type: ignore[assignment]
    configure_provider(proveedor_ctl)
    estado = await recovery.try_load(base_sin_llaves, settings_prueba, create_missing=True)
    assert estado == estado_proveedor
    assert not recovery.is_loaded() and recovery.current_state() == estado_proveedor
    assert await contar_llaves(base_sin_llaves) == 0
    with pytest.raises(CryptoUnavailable):
        current_keyring()


async def test_try_load_sin_create_missing_nunca_inserta_en_crypto_keys(
    base_sin_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
) -> None:
    """El worker (`apex_worker` no tiene INSERT) solo abre lo que ya existe."""
    configure_provider(proveedor_ctl)
    await recovery.try_load(base_sin_llaves, settings_prueba, create_missing=False)
    assert await contar_llaves(base_sin_llaves) == 0
    assert proveedor_ctl.wrap_calls == 0


async def test_try_load_con_classes_abre_solo_las_clases_pedidas(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
) -> None:
    """M-6: el worker no abre `member.document` ni `member.birth_date`."""
    configure_provider(proveedor_ctl)
    estado = await recovery.try_load(
        base_con_llaves, settings_prueba, create_missing=False, classes=PHONE_Y_EMAIL
    )
    assert estado == "ok"
    clases = {llave.data_class for llave in current_keyring().keys()}
    assert clases == PHONE_Y_EMAIL, clases


async def test_try_load_sin_classes_abre_todas_las_llaves_del_bus(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
) -> None:
    configure_provider(proveedor_ctl)
    await recovery.try_load(base_con_llaves, settings_prueba, create_missing=False)
    clases = {llave.data_class for llave in current_keyring().keys()}
    assert clases > PHONE_Y_EMAIL and "member.document" in clases


async def test_try_load_propaga_unwrap_failed_y_no_crea_llaves(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
) -> None:
    """M-4: una KEK ajena no degrada: el error sube y `ensure_keys` no llega a envolver."""
    proveedor_ctl.error = CryptoError("unwrap_failed", "la envoltura no abre")
    configure_provider(proveedor_ctl)
    antes = await contar_llaves(base_con_llaves)
    with pytest.raises(CryptoError) as error:
        await recovery.try_load(base_con_llaves, settings_prueba, create_missing=True)
    assert error.value.code == "unwrap_failed"
    assert await contar_llaves(base_con_llaves) == antes
    assert proveedor_ctl.wrap_calls == 0


async def test_try_load_recupera_sin_reiniciar_cuando_el_proveedor_vuelve(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
) -> None:
    proveedor_ctl.estado = "sealed"
    configure_provider(proveedor_ctl)
    assert await recovery.try_load(base_con_llaves, settings_prueba, create_missing=True) == (
        "sealed"
    )
    assert not recovery.is_loaded()
    proveedor_ctl.estado = "ok"
    assert await recovery.try_load(base_con_llaves, settings_prueba, create_missing=True) == "ok"
    assert recovery.is_loaded() and recovery.current_state() == "ok"


# poll_forever -----------------------------------------------------------------------------------


class _FinDeLaPrueba(BaseException):
    """Corta el bucle del sondeo (no es `Exception`: ningún `except Exception` la traga)."""


class _Reloj:
    """`sleep` falso: anota cada espera, mueve el `FrozenClock` y ejecuta el guion por tick."""

    def __init__(
        self, reloj: FrozenClock, proveedor: ProveedorControlable, desellar_en: int, tope: int
    ) -> None:
        self.reloj, self.proveedor = reloj, proveedor
        self.desellar_en, self.tope = desellar_en, tope
        self.esperas: list[float] = []

    async def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.reloj.set(self.reloj.now_utc() + timedelta(seconds=segundos))
        if len(self.esperas) == self.desellar_en:
            self.proveedor.estado = "ok"
        if len(self.esperas) >= self.tope:
            raise _FinDeLaPrueba


async def test_el_sondeo_espera_20_segundos_recupera_y_avisa_una_vez_por_transicion(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    alertas: GrabadoraDeAlertas,
    reloj: FrozenClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert settings_prueba.CRYPTO_RECOVERY_POLL_S == POLL_S
    proveedor_ctl.estado = "sealed"
    configure_provider(proveedor_ctl)
    dormir = _Reloj(reloj, proveedor_ctl, desellar_en=2, tope=6)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(_FinDeLaPrueba):
        await recovery.poll_forever(
            base_con_llaves, settings_prueba, create_missing=True, sleep=dormir, jitter=lambda: 0.0
        )
    assert dormir.esperas and set(dormir.esperas) == {POLL_S}
    assert recovery.is_loaded() and recovery.current_state() == "ok"
    assert alertas.codigos == ["crypto_sealed", "crypto_recovered"]
    propios = [r for r in caplog.records if r.name == "app.core.crypto.recovery"]
    assert len(propios) == 2, [r.getMessage() for r in propios]
    for registro in propios:
        assert "http" not in registro.getMessage()


async def test_un_sondeo_que_sigue_sellado_no_repite_el_aviso(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    alertas: GrabadoraDeAlertas,
    reloj: FrozenClock,
) -> None:
    proveedor_ctl.estado = "sealed"
    configure_provider(proveedor_ctl)
    dormir = _Reloj(reloj, proveedor_ctl, desellar_en=99, tope=5)
    with pytest.raises(_FinDeLaPrueba):
        await recovery.poll_forever(
            base_con_llaves, settings_prueba, create_missing=True, sleep=dormir, jitter=lambda: 0.0
        )
    assert len(dormir.esperas) == 5
    assert alertas.codigos == ["crypto_sealed"]
    assert not recovery.is_loaded()


# lifespan ---------------------------------------------------------------------------------------


def _tareas_de_sondeo() -> list[asyncio.Task[object]]:
    return [
        t
        for t in asyncio.all_tasks()
        if getattr(t.get_coro(), "__name__", "") == "poll_forever"  # type: ignore[arg-type]
    ]


async def test_el_lifespan_lanza_el_sondeo_si_arranca_sellado_y_lo_cancela_al_salir(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proveedor_ctl.estado = "sealed"
    inyectar_proveedor(monkeypatch, proveedor_ctl)
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    async with app.router.lifespan_context(app):
        tareas = _tareas_de_sondeo()
        assert len(tareas) == 1 and not tareas[0].done()
    assert tareas[0].done() and tareas[0].cancelled()
    assert _tareas_de_sondeo() == []


async def test_el_lifespan_recupera_el_keyring_sin_reiniciar(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proveedor_ctl.estado = "sealed"
    inyectar_proveedor(monkeypatch, proveedor_ctl)
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    async with app.router.lifespan_context(app):
        assert not recovery.is_loaded()
        proveedor_ctl.estado = "ok"
        estado = await recovery.try_load(base_con_llaves, settings_prueba, create_missing=True)
        assert estado == "ok" and recovery.is_loaded()
