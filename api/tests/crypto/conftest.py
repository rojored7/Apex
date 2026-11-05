"""Ayudas del bus para las pruebas de `tests/crypto`.

`proveedor_local`, `sin_llaves` y `bus_listo` viven en `tests/conftest.py` desde S2-B1
(S2-D19): las usan también `tests/core`, `tests/settings` y los módulos siguientes.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import LIMPIAR_LLAVES


async def limpiar_llaves_con_commit(engine: AsyncEngine) -> None:
    """Solo en pruebas: borra las llaves con los triggers apagados y confirma."""
    async with engine.begin() as conn:
        for sql in LIMPIAR_LLAVES:
            await conn.execute(text(sql))


# Respaldo de la KEK (S4B-B3a; S4B-D89) -----------------------------------------------------------

import os  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from app.core.crypto import archive  # noqa: E402
from app.core.crypto.kek_backup import WrappedDek  # noqa: E402
from app.core.crypto.local_provider import LocalFileProvider  # noqa: E402
from tests.factories.fake_age import fake_age  # noqa: E402

DEK_ACTIVAS = 2
"""`wrapped_de_prueba`: índices 0 y 1 `active`, 2 `decrypt_only`, 3 `retired` (otra KEK)."""


@pytest.fixture
def kek_tmp(tmp_path: Path) -> Path:
    """32 bytes aleatorios en `tmp_path/keys/kek.bin` (0o600); `keys/` es "la KEK viva"."""
    carpeta = tmp_path / "keys"
    carpeta.mkdir()
    ruta = carpeta / "kek.bin"
    ruta.write_bytes(os.urandom(32))
    ruta.chmod(0o600)
    return ruta


@pytest.fixture
async def wrapped_de_prueba(kek_tmp: Path, tmp_path: Path) -> list[WrappedDek]:
    """Cuatro DEK envueltas: dos `active` y una `decrypt_only` con `kek_tmp`; una `retired`
    envuelta con OTRA KEK (si `verify_wrapped` la contara, fallaría)."""
    semilla = tmp_path / "keys" / "sign.key"
    semilla.write_bytes(os.urandom(32))
    semilla.chmod(0o600)
    propia = LocalFileProvider(kek_tmp, semilla)
    otra_kek = tmp_path / "otra" / "kek.bin"
    otra_kek.parent.mkdir()
    otra_kek.write_bytes(os.urandom(32))
    otra_kek.chmod(0o600)
    ajena = LocalFileProvider(otra_kek, semilla)
    estados = ["active", "active", "decrypt_only", "retired"]
    salida: list[WrappedDek] = []
    for n, estado in enumerate(estados):
        proveedor = ajena if estado == "retired" else propia
        salida.append(
            WrappedDek(
                key_id=f"00000000-0000-0000-0000-00000000000{n + 1}",
                version=1,
                state=estado,
                wrapped_material=await proveedor.wrap(os.urandom(32)),
            )
        )
    return salida


@pytest.fixture
def age_falso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`age` falso como binario de `archive`: parchea `AGE_BINARY` y los `age_binary=` por
    defecto de las tres funciones (el valor por defecto se evalúa al definir la función)."""
    if sys.platform == "win32" and not os.environ.get("APEX_FAKE_AGE_FORZAR"):
        pytest.skip(
            "cmd.exe no arranca con env={} (el hijo de archive.py no hereda entorno); el age "
            "falso corre en CI/Linux. APEX_FAKE_AGE_FORZAR=1 lo fuerza (solo para ver el Rojo)."
        )
    ejecutable = fake_age(tmp_path)
    monkeypatch.setattr(archive, "AGE_BINARY", str(ejecutable))
    for nombre in ("export_kek_file", "restore_kek_file", "verify_kek_backup"):
        valores = getattr(archive, nombre).__kwdefaults__
        if valores is not None and "age_binary" in valores:
            monkeypatch.setitem(valores, "age_binary", str(ejecutable))
    return ejecutable


def entorno_visto(llamada: dict[str, object]) -> dict[str, str]:
    """Entorno que vio el hijo, sin las variables que `cmd.exe` inyecta en Windows (`=C:`...)."""
    entorno = {str(k): str(v) for k, v in dict(llamada["env"]).items()}  # type: ignore[call-overload]
    if sys.platform == "win32":
        entorno = {k: v for k, v in entorno.items() if not k.startswith("=")}
    return entorno


# Rotación de llave y retiro (S4B-B3b): las fixtures viven en `_rotacion.py` (también las usa cli)
# Proveedor de OpenBao (S5-B1; S5-D21) ------------------------------------------------------------
from collections.abc import Iterator  # noqa: E402

from app.core.crypto.openbao_provider import OpenBaoProvider  # noqa: E402
from tests.crypto._rotacion import (  # noqa: E402,F401
    candado_rotacion_tomado,
    manifiesto_reciente,
    rotacion_lista,
)
from tests.factories.fake_transit import ADDR_FAKE, TOKEN_FAKE, FakeTransit  # noqa: E402


@pytest.fixture
def token_file(tmp_path: Path) -> Path:
    """Archivo del token del servicio (0o600) con `TOKEN_FAKE` y salto de línea final."""
    carpeta = tmp_path / "openbao"
    carpeta.mkdir()
    ruta = carpeta / "token"
    ruta.write_text(TOKEN_FAKE + "\n", encoding="utf-8")
    ruta.chmod(0o600)
    return ruta


@pytest.fixture
def fake_transit() -> FakeTransit:
    return FakeTransit()


@pytest.fixture
def openbao_fake(fake_transit: FakeTransit, token_file: Path) -> OpenBaoProvider:
    """`OpenBaoProvider` sobre `FakeTransit` (cliente inyectado)."""
    return OpenBaoProvider(ADDR_FAKE, token_file, timeout_s=2.0, client=fake_transit.cliente())


@pytest.fixture
def openbao_real() -> OpenBaoProvider:
    """OpenBao real: se salta sin `OPENBAO_TEST_ADDR` y `OPENBAO_TEST_TOKEN_FILE` (B1.7)."""
    addr = os.environ.get("OPENBAO_TEST_ADDR")
    token = os.environ.get("OPENBAO_TEST_TOKEN_FILE")
    if not addr or not token:
        pytest.skip(
            "sin OPENBAO_TEST_ADDR / OPENBAO_TEST_TOKEN_FILE: la prueba con OpenBao real corre en "
            "el contenedor Linux de validacion (B1.7) y en la CI"
        )
    return OpenBaoProvider(addr, Path(token), timeout_s=5.0)


@pytest.fixture(
    params=["local", "fake_transit", pytest.param("openbao_real", marks=pytest.mark.openbao)]
)
def tipo(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def proveedor(tipo: str, request: pytest.FixtureRequest) -> Iterator[object]:
    """El proveedor bajo la suite de contrato: `local`, `fake_transit` u `openbao_real`."""
    destino = {
        "local": "proveedor_local",
        "fake_transit": "openbao_fake",
        "openbao_real": "openbao_real",
    }[tipo]
    yield request.getfixturevalue(destino)


# Migración de proveedor y rotación de la KEK (S5-B2)
from tests.crypto._migracion import migracion_lista, sembrada  # noqa: E402,F401
