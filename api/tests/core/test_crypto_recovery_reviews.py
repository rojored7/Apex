"""Revisiones de S5-B3 (S5-D198 a S5-D202): estado por proceso, pasos de arranque, forbidden,
sondeo resistente, observe de /health, jitter, ensure_keys y cancelación. Rojo primero."""

from __future__ import annotations

import asyncio
import logging

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import main as main_module
from app.core import health
from app.core.config import Settings
from app.core.crypto import recovery
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.keyring import Keyring, configure_keyring, current_keyring
from app.core.crypto.provider import configure_provider
from app.main import create_app
from app.worker import runtime
from tests.core._cripto_apoyo import (
    GrabadoraDeAlertas,
    alertas,
    base_con_llaves,
    base_sin_llaves,
    estado_de_recovery_limpio,
    proveedor_ctl,
)
from tests.factories.fake_provider import ProveedorControlable, inyectar_proveedor
from tests.factories.triggers import disable_user_sql, rearm_always_sql

__all__ = [
    "alertas",
    "base_con_llaves",
    "base_sin_llaves",
    "estado_de_recovery_limpio",
    "proveedor_ctl",
]

Fabrica = async_sessionmaker[AsyncSession]


class _Fin(BaseException):
    """Corta el bucle del sondeo."""


def _dormir(tope: int, *, en: dict[int, object] | None = None) -> object:
    esperas: list[float] = []

    async def dormir(segundos: float) -> None:
        esperas.append(segundos)
        if en and len(esperas) in en:
            en[len(esperas)]()  # type: ignore[operator]
        if len(esperas) >= tope:
            raise _Fin

    dormir.esperas = esperas  # type: ignore[attr-defined]
    return dormir


@pytest.fixture(autouse=True)
def _sin_proceso_previo() -> None:
    configure_keyring(None)


# S5-D198 ------------------------------------------------------------------------------------------


async def test_dos_apps_seguidas_la_segunda_sellada_vuelve_a_emitir_crypto_sealed(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    alertas: GrabadoraDeAlertas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proveedor_ctl.estado = "sealed"
    inyectar_proveedor(monkeypatch, proveedor_ctl)
    for _ in range(2):
        app = create_app(settings_prueba, run_migrations_on_startup=False)
        async with app.router.lifespan_context(app):
            pass
        assert recovery.current_state() == "unknown"
    assert alertas.codigos == ["crypto_sealed", "crypto_sealed"]


async def test_con_el_keyring_en_none_y_estado_ok_el_sondeo_recarga(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
) -> None:
    configure_provider(proveedor_ctl)
    assert await recovery.try_load(base_con_llaves, settings_prueba, create_missing=True) == "ok"
    configure_keyring(None)
    assert recovery.current_state() == "ok" and not recovery.is_loaded()
    with pytest.raises(_Fin):
        await recovery.poll_forever(
            base_con_llaves,
            settings_prueba,
            create_missing=True,
            sleep=_dormir(2),  # type: ignore[arg-type]
            jitter=lambda: 0.0,
        )
    assert recovery.is_loaded()


# S5-D199 ------------------------------------------------------------------------------------------


async def test_un_paso_de_arranque_no_corre_sellado_y_corre_una_vez_al_recuperar(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corridas: list[str] = []

    async def paso(settings: Settings) -> None:
        corridas.append("paso")

    main_module.clear_startup_steps()
    main_module.register_startup_step("prueba", paso)
    try:
        proveedor_ctl.estado = "sealed"
        inyectar_proveedor(monkeypatch, proveedor_ctl)
        ajustes = settings_prueba.model_copy(update={"CRYPTO_RECOVERY_POLL_S": 1})
        app = create_app(ajustes, run_migrations_on_startup=False)
        async with app.router.lifespan_context(app):
            assert corridas == []
            proveedor_ctl.estado = "ok"
            for _ in range(80):
                if corridas:
                    break
                await asyncio.sleep(0.1)
            await asyncio.sleep(0.3)
            assert corridas == ["paso"]
    finally:
        main_module.clear_startup_steps()


async def test_on_loaded_corre_una_sola_vez_en_la_primera_recuperacion(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
) -> None:
    llamadas: list[int] = []

    async def alcargar() -> None:
        llamadas.append(1)

    proveedor_ctl.estado = "sealed"
    configure_provider(proveedor_ctl)
    with pytest.raises(_Fin):
        await recovery.poll_forever(
            base_con_llaves,
            settings_prueba,
            create_missing=True,
            sleep=_dormir(5, en={2: lambda: setattr(proveedor_ctl, "estado", "ok")}),  # type: ignore[arg-type]
            jitter=lambda: 0.0,
            on_loaded=alcargar,
        )
    assert llamadas == [1]


async def test_una_guarda_de_keyring_ausente_cuenta_como_sealed(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_provider(proveedor_ctl)

    async def no_carga(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(recovery, "_load", no_carga)
    assert await recovery.try_load(base_con_llaves, settings_prueba, create_missing=True) == (
        "sealed"
    )


# S5-D200 ------------------------------------------------------------------------------------------


async def test_forbidden_en_el_arranque_aborta_sin_crear_llaves(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    estado_de_recovery_limpio: None,
) -> None:
    proveedor_ctl.estado = "unreachable"
    proveedor_ctl.last_reason = "forbidden"
    inyectar_proveedor(monkeypatch, proveedor_ctl)
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    with pytest.raises(CryptoUnavailable) as error:
        async with app.router.lifespan_context(app):
            pass
    assert error.value.reason == "forbidden"
    assert proveedor_ctl.wrap_calls == 0


@pytest.mark.parametrize(
    ("falla", "codigo"),
    [
        (CryptoError("unwrap_failed", "no abre"), "crypto_unwrap_failed"),
        (CryptoError("key_missing", "falta"), "crypto_unwrap_failed"),
        (CryptoUnavailable("forbidden"), "crypto_forbidden"),
    ],
    ids=["unwrap_failed", "key_missing", "forbidden"],
)
async def test_el_sondeo_alerta_una_vez_por_racha_y_sigue(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    alertas: GrabadoraDeAlertas,
    falla: CryptoError,
    codigo: str,
) -> None:
    proveedor_ctl.error = falla
    configure_provider(proveedor_ctl)
    dormir = _dormir(5)
    with pytest.raises(_Fin):
        await recovery.poll_forever(
            base_con_llaves,
            settings_prueba,
            create_missing=True,
            sleep=dormir,  # type: ignore[arg-type]
            jitter=lambda: 0.0,
        )
    assert alertas.codigos == [codigo]
    assert len(dormir.esperas) == 5  # type: ignore[attr-defined]


async def test_un_runtime_error_a_mitad_del_sondeo_no_lo_mata_y_la_vuelta_siguiente_recupera(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    proveedor_ctl.fallos_unicos = [RuntimeError("resolver roto")]
    configure_provider(proveedor_ctl)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(_Fin):
        await recovery.poll_forever(
            base_con_llaves,
            settings_prueba,
            create_missing=True,
            sleep=_dormir(3),  # type: ignore[arg-type]
            jitter=lambda: 0.0,
        )
    assert recovery.is_loaded() and recovery.current_state() == "ok"
    con_traza = [
        r
        for r in caplog.records
        if r.name == "app.core.crypto.recovery" and r.levelno == logging.ERROR and r.exc_info
    ]
    assert len(con_traza) == 1


# S5-D202 ------------------------------------------------------------------------------------------


async def test_el_check_de_health_observa_el_resellado_con_el_keyring_en_memoria(
    app_http: AsyncClient,
    proveedor_ctl: ProveedorControlable,
    estado_de_recovery_limpio: None,
    alertas: GrabadoraDeAlertas,
) -> None:
    configure_provider(proveedor_ctl)
    health.clear_health_cache()
    assert (await app_http.get("/health")).json()["crypto"] == "ok"
    proveedor_ctl.estado = "sealed"
    for _ in range(2):
        health.clear_health_cache()
        assert (await app_http.get("/health")).json()["crypto"] == "sealed"
    assert alertas.codigos == ["crypto_sealed"]
    proveedor_ctl.estado = "ok"
    health.clear_health_cache()
    assert (await app_http.get("/health")).json()["crypto"] == "ok"
    assert alertas.codigos == ["crypto_sealed", "crypto_recovered"]


# jitter, transiciones, ensure_keys, cancelación, worker -------------------------------------------


async def test_el_sondeo_suma_jitter_de_0_a_2_segundos_por_omision(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
) -> None:
    proveedor_ctl.estado = "sealed"
    configure_provider(proveedor_ctl)
    dormir = _dormir(20)
    with pytest.raises(_Fin):
        await recovery.poll_forever(
            base_con_llaves,
            settings_prueba,
            create_missing=True,
            sleep=dormir,  # type: ignore[arg-type]
        )
    esperas = dormir.esperas  # type: ignore[attr-defined]
    assert all(20 <= e <= 22 for e in esperas) and len(set(esperas)) > 1


async def test_sealed_unreachable_ok_emite_una_alerta_de_cada_tipo(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    alertas: GrabadoraDeAlertas,
) -> None:
    proveedor_ctl.estado = "sealed"
    configure_provider(proveedor_ctl)
    dormir = _dormir(
        6,
        en={
            2: lambda: setattr(proveedor_ctl, "estado", "unreachable"),
            4: lambda: setattr(proveedor_ctl, "estado", "ok"),
        },
    )
    with pytest.raises(_Fin):
        await recovery.poll_forever(
            base_con_llaves,
            settings_prueba,
            create_missing=True,
            sleep=dormir,  # type: ignore[arg-type]
            jitter=lambda: 0.0,
        )
    assert alertas.codigos == ["crypto_sealed", "crypto_recovered"]


async def test_ensure_keys_aborta_si_hay_filas_pero_ninguna_dek_abre(
    base_con_llaves: Fabrica, proveedor_ctl: ProveedorControlable
) -> None:
    async with base_con_llaves() as sesion, sesion.begin():
        await sesion.execute(text(disable_user_sql("crypto.crypto_keys")))
        await sesion.execute(text("DELETE FROM crypto.crypto_keys WHERE purpose = 'encrypt'"))
        await sesion.execute(text(rearm_always_sql("crypto.crypto_keys")))
    async with base_con_llaves() as sesion:
        with pytest.raises(CryptoError) as error:
            await ensure_keys(sesion, proveedor_ctl, lambda _n: proveedor_ctl)
    assert error.value.code == "unwrap_failed" and proveedor_ctl.wrap_calls == 0


async def test_cancelar_dentro_de_session_begin_no_deja_keyring_parcial(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
) -> None:
    proveedor_ctl.bloqueo = asyncio.Event()
    configure_provider(proveedor_ctl)
    tarea = asyncio.create_task(
        recovery.try_load(base_con_llaves, settings_prueba, create_missing=True)
    )
    for _ in range(100):
        if proveedor_ctl.unwrap_calls:
            break
        await asyncio.sleep(0.05)
    assert proveedor_ctl.unwrap_calls
    tarea.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tarea
    with pytest.raises(CryptoUnavailable):
        current_keyring()
    assert not recovery.is_loaded()


async def test_el_worker_sellado_sale_limpio_sin_tareas_ni_estado(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proveedor_ctl.estado = "sealed"
    inyectar_proveedor(monkeypatch, proveedor_ctl)
    async with runtime.worker_runtime(settings_prueba, with_crypto=True):
        vivas = [t for t in asyncio.all_tasks() if t.get_coro().__name__ == "poll_forever"]  # type: ignore[union-attr]
        assert len(vivas) == 1
    assert [t for t in asyncio.all_tasks() if t.get_coro().__name__ == "poll_forever"] == []  # type: ignore[union-attr]
    assert recovery.current_state() == "unknown"


def test_keyring_vacio_cuenta_como_cargado() -> None:
    configure_keyring(Keyring())
    assert recovery.is_loaded()
    configure_keyring(None)
    assert isinstance(FastAPI(), FastAPI)
