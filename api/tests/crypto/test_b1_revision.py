"""Correcciones de la revisión de seguridad de S5-B1 (S5-D162, S5-D165): enfriamiento de
`refresh_current` (M2) y proveedor de creación sin fallback en producción (L3)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import keyring as keyring_mod
from app.core.crypto import service
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.keyring import Keyring, refresh_current
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.provider import configure_provider


class _Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


async def test_custodio_caido_una_consulta_y_un_warning_por_ventana(
    bus_listo: Keyring,
    session: AsyncSession,
    proveedor_local: LocalFileProvider,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_provider(proveedor_local)
    reloj = _Reloj()
    monkeypatch.setattr(keyring_mod, "_monotonic", reloj)
    monkeypatch.setattr(keyring_mod, "_proximo_intento", 0.0)
    intentos: list[int] = []

    async def caido(self: Keyring, sesion: AsyncSession, proveedor: object) -> bool:
        intentos.append(1)
        raise CryptoUnavailable("unreachable")

    monkeypatch.setattr(Keyring, "refresh_if_stale", caido)
    caplog.set_level(logging.WARNING, logger=keyring_mod.logger.name)
    try:
        for _ in range(5):
            await refresh_current(session)
        assert len(intentos) == 1
        assert [r.getMessage() for r in caplog.records if "keyring" in r.getMessage()] == [
            "keyring sin refrescar: unreachable"
        ]
        reloj.t += 31
        await refresh_current(session)
        assert len(intentos) == 2
    finally:
        configure_provider(None)


async def test_un_cryptoerror_generico_tambien_se_contiene_con_su_code(
    bus_listo: Keyring,
    session: AsyncSession,
    proveedor_local: LocalFileProvider,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_provider(proveedor_local)
    monkeypatch.setattr(keyring_mod, "_monotonic", _Reloj())
    monkeypatch.setattr(keyring_mod, "_proximo_intento", 0.0)

    async def falla(self: Keyring, sesion: AsyncSession, proveedor: object) -> bool:
        raise CryptoError("unwrap_failed", "x")

    monkeypatch.setattr(Keyring, "refresh_if_stale", falla)
    caplog.set_level(logging.WARNING, logger=keyring_mod.logger.name)
    try:
        await refresh_current(session)  # no lanza
    finally:
        configure_provider(None)
    assert "keyring sin refrescar: unwrap_failed" in caplog.text


def test_sin_proveedor_fijado_en_produccion_no_hay_fallback(
    bus_listo: Keyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_provider(None)
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(ENV="production"))
    with pytest.raises(CryptoUnavailable) as error:
        service._provider()
    assert error.value.reason == "not_loaded"


def test_sin_proveedor_fijado_fuera_de_produccion_cae_al_del_keyring(
    bus_listo: Keyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_provider(None)
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(ENV="dev"))
    assert service._provider() is bus_listo.provider
