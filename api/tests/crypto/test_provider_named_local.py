"""`get_provider_named(settings, "local")` con `CRYPTO_PROVIDER=openbao` (S5-D3, D50 punto 3).

El resolver es por fila: una fila `sign` `local` se resuelve aunque el proveedor de arranque sea
OpenBao y la KEK local ya se haya retirado; la KEK solo se pide al primer `wrap`/`unwrap`. En modo
`local` el control de arranque (KEK presente) no cambia.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cli import init_keys_files, key_paths_in
from app.core.config import Settings
from app.core.crypto import provider as provider_mod
from app.core.crypto.errors import CryptoError
from app.core.crypto.local_provider import SIGNING_KEY_REF, LocalFileProvider


def _ajustes(rutas_kek: Path | None, firma: Path, proveedor: str) -> Settings:
    return Settings.model_construct(
        CRYPTO_PROVIDER=proveedor,
        CRYPTO_LOCAL_KEK_PATH=rutas_kek,
        CRYPTO_LOCAL_SIGNING_KEY_PATH=firma,
    )


async def test_local_con_openbao_se_construye_sin_la_kek_y_firma(tmp_path: Path) -> None:
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    rutas.kek.unlink()  # tras retire-local-kek
    ajustes = _ajustes(rutas.kek, rutas.signing_key, "openbao")

    proveedor = provider_mod.get_provider_named(ajustes, "local", with_signing=True)

    assert isinstance(proveedor, LocalFileProvider)
    firma = await proveedor.sign(SIGNING_KEY_REF, b"datos")
    assert await proveedor.verify(SIGNING_KEY_REF, b"datos", firma)
    assert await proveedor.sign_public_key()


async def test_local_con_openbao_pide_la_kek_solo_al_envolver(tmp_path: Path) -> None:
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    rutas.kek.unlink()
    proveedor = provider_mod.get_provider_named(
        _ajustes(rutas.kek, rutas.signing_key, "openbao"), "local"
    )

    with pytest.raises(CryptoError) as envolver:
        await proveedor.wrap(b"x" * 32)
    with pytest.raises(CryptoError) as abrir:
        await proveedor.unwrap(b"apxw1" + b"0" * 40)

    assert envolver.value.code == "kek_missing"
    assert abrir.value.code == "kek_missing"


async def test_local_con_openbao_y_la_kek_presente_envuelve_y_abre(tmp_path: Path) -> None:
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    proveedor = provider_mod.get_provider_named(
        _ajustes(rutas.kek, rutas.signing_key, "openbao"), "local"
    )

    envuelta = await proveedor.wrap(b"d" * 32)

    assert await proveedor.unwrap(envuelta) == b"d" * 32


def test_local_con_openbao_sin_la_ruta_de_la_kek_sigue_siendo_kek_missing(tmp_path: Path) -> None:
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    with pytest.raises(CryptoError) as error:
        provider_mod.get_provider_named(_ajustes(None, rutas.signing_key, "openbao"), "local")
    assert error.value.code == "kek_missing"


def test_local_con_openbao_sin_la_llave_de_firma_falla_con_kek_missing(tmp_path: Path) -> None:
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    rutas.signing_key.unlink()
    with pytest.raises(CryptoError) as error:
        provider_mod.get_provider_named(
            _ajustes(rutas.kek, rutas.signing_key, "openbao"), "local", with_signing=True
        )
    assert error.value.code == "kek_missing"


def test_en_modo_local_la_kek_ausente_sigue_fallando_al_construir(tmp_path: Path) -> None:
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    rutas.kek.unlink()
    ajustes = _ajustes(rutas.kek, rutas.signing_key, "local")

    with pytest.raises(CryptoError) as nombrado:
        provider_mod.get_provider_named(ajustes, "local")
    with pytest.raises(CryptoError) as arranque:
        provider_mod.get_key_provider(ajustes)

    assert nombrado.value.code == arranque.value.code == "kek_missing"


def test_get_key_provider_con_openbao_sigue_sin_construir_local(tmp_path: Path) -> None:
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    with pytest.raises(CryptoError) as error:
        provider_mod.get_key_provider(_ajustes(rutas.kek, rutas.signing_key, "openbao"))
    assert error.value.code == "unknown_provider"


async def test_el_resolver_del_worker_resuelve_la_fila_sign_local_en_modo_local(
    tmp_path: Path,
) -> None:
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    ajustes = _ajustes(rutas.kek, rutas.signing_key, "local")
    resolver = provider_mod.make_resolver(ajustes)

    proveedor = resolver("local")

    assert proveedor.name == "local"
    assert resolver("local") is proveedor
    assert proveedor.sign_key_ref() == SIGNING_KEY_REF
