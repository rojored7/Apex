"""`worker_runtime(settings, with_crypto=True)` (S5-B3; S5-D20, S5-D56, M-6). Rojo B3.

- carga el keyring con SOLO `member.phone` y `member.email` (M-6) y deja cifrar y descifrar;
- con el proveedor sellado no aborta: estado `sealed` y sin keyring;
- nunca ejecuta un `INSERT` en `crypto_keys` (el rol `apex_worker` no lo tiene);
- por defecto (`with_crypto=False`) no crea proveedor ni lee `crypto_keys`.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import db
from app.core.config import Settings
from app.core.crypto import bus, recovery
from app.core.crypto.errors import CryptoUnavailable
from app.core.crypto.keyring import configure_keyring, current_keyring
from app.core.crypto.provider import configure_provider
from app.worker import runtime
from tests.core._cripto_apoyo import (
    base_con_llaves,
    base_sin_llaves,
    estado_de_recovery_limpio,
    proveedor_ctl,
)
from tests.factories.fake_provider import ProveedorControlable, inyectar_proveedor

__all__ = ["base_con_llaves", "base_sin_llaves", "estado_de_recovery_limpio", "proveedor_ctl"]

Fabrica = async_sessionmaker[AsyncSession]
PHONE_Y_EMAIL = {"member.phone", "member.email"}


@pytest.fixture
def sql_vista(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Cada sentencia que ejecuta el engine que crea el runtime del worker."""
    vistas: list[str] = []
    crear = db.create_engine_from

    def con_espia(settings: Settings) -> AsyncEngine:
        motor = crear(settings)

        @event.listens_for(motor.sync_engine, "before_cursor_execute")
        def anotar(conn: object, cursor: object, statement: str, *rest: object) -> None:
            vistas.append(statement)

        return motor

    monkeypatch.setattr(db, "create_engine_from", con_espia)
    return vistas


@pytest.fixture(autouse=True)
def _procesos_limpios() -> None:
    configure_keyring(None)
    configure_provider(None)


async def test_con_crypto_carga_solo_phone_y_email_y_permite_cifrar_y_descifrar(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inyectar_proveedor(monkeypatch, proveedor_ctl)
    socio = uuid4()
    async with runtime.worker_runtime(settings_prueba, with_crypto=True):
        clases = {llave.data_class for llave in current_keyring().keys()}
        blob = bus.encrypt("member.email", b"socio@example.com", bus.aad_for(socio))
        claro = bus.decrypt(blob, bus.aad_for(socio), purpose="notify")
        assert recovery.current_state() == "ok" and recovery.is_loaded()
    assert clases == PHONE_Y_EMAIL, clases
    assert claro == b"socio@example.com"


async def test_con_crypto_las_otras_clases_no_se_pueden_usar(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inyectar_proveedor(monkeypatch, proveedor_ctl)
    async with runtime.worker_runtime(settings_prueba, with_crypto=True):
        with pytest.raises(Exception) as error:
            bus.encrypt("member.document", b"1020304417", bus.aad_for(uuid4()))
    assert getattr(error.value, "code", "") == "key_missing"


async def test_con_el_proveedor_sellado_no_aborta_y_el_estado_es_sealed(
    base_con_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proveedor_ctl.estado = "sealed"
    inyectar_proveedor(monkeypatch, proveedor_ctl)
    async with runtime.worker_runtime(settings_prueba, with_crypto=True) as fabrica:
        assert fabrica is not None
        assert recovery.current_state() == "sealed" and not recovery.is_loaded()
        with pytest.raises(CryptoUnavailable):
            current_keyring()


async def test_con_crypto_nunca_inserta_en_crypto_keys_ni_siquiera_con_la_tabla_vacia(
    base_sin_llaves: Fabrica,
    proveedor_ctl: ProveedorControlable,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    monkeypatch: pytest.MonkeyPatch,
    sql_vista: list[str],
) -> None:
    inyectar_proveedor(monkeypatch, proveedor_ctl)
    async with runtime.worker_runtime(settings_prueba, with_crypto=True):
        pass
    assert any("crypto_keys" in s for s in sql_vista), "no leyó crypto_keys: el espía no ve nada"
    escrituras = [
        s
        for s in sql_vista
        if "crypto_keys" in s and s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]
    assert escrituras == []
    assert proveedor_ctl.wrap_calls == 0


async def test_por_defecto_no_crea_proveedor_ni_lee_crypto_keys(
    base_con_llaves: Fabrica,
    settings_prueba: Settings,
    estado_de_recovery_limpio: None,
    sql_vista: list[str],
) -> None:
    async with runtime.worker_runtime(settings_prueba):
        with pytest.raises(CryptoUnavailable):
            current_keyring()
    assert [s for s in sql_vista if "crypto_keys" in s] == []
