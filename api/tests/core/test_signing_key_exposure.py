"""El api no arranca si ve la llave de firma bajo `/run/apex/keys` (S7-D23 (2), H-1)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.crypto import exposure
from app.core.security import StartupError
from app.main import _startup

SEMILLA = b"semilla-de-prueba-" + b"x" * 14


def _volumen(raiz: Path, *, con_firma_en: str | None) -> Path:
    for sub in ("custody", "jwt", "sign"):
        (raiz / sub).mkdir(parents=True, exist_ok=True)
    (raiz / "custody" / "kek.bin").write_bytes(b"k" * 32)
    if con_firma_en is not None:
        destino = raiz / con_firma_en / "sign-ed25519.key"
        destino.write_bytes(SEMILLA)
    return raiz


def test_sin_llave_de_firma_no_hay_exposicion(tmp_path: Path) -> None:
    raiz = _volumen(tmp_path / "keys", con_firma_en=None)

    assert exposure.signing_key_exposed(raiz) is False


@pytest.mark.parametrize("subcarpeta", ["custody", "sign", "jwt", "."])
def test_la_llave_en_cualquier_subcarpeta_es_exposicion(tmp_path: Path, subcarpeta: str) -> None:
    raiz = _volumen(tmp_path / "keys", con_firma_en=subcarpeta)

    assert exposure.signing_key_exposed(raiz) is True


def test_un_volumen_inexistente_no_es_exposicion(tmp_path: Path) -> None:
    assert exposure.signing_key_exposed(tmp_path / "no-existe") is False


async def test_el_api_no_arranca_si_ve_sign_ed25519_en_sus_montajes(
    settings_prueba: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raiz = _volumen(tmp_path / "keys-api", con_firma_en="custody")
    monkeypatch.setattr(exposure, "KEYS_ROOT", raiz)

    with pytest.raises(StartupError, match="signing_key_exposed"):
        await _startup(
            settings_prueba, run_migrations_on_startup=False, migrations_script_location=None
        )


async def test_el_log_no_lleva_contenido(
    settings_prueba: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raiz = _volumen(tmp_path / "keys-api", con_firma_en="custody")
    monkeypatch.setattr(exposure, "KEYS_ROOT", raiz)

    with caplog.at_level(logging.DEBUG), pytest.raises(StartupError):
        await _startup(
            settings_prueba, run_migrations_on_startup=False, migrations_script_location=None
        )

    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert "signing_key_exposed" in texto
    assert SEMILLA.decode() not in texto
    assert str(raiz) not in texto
