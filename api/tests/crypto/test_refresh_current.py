"""`keyring.refresh_current(session)` (S2-B2; S2-D11, M-3 del Sprint 1).

`current_user` la llama solo tras validar el token: sin keyring cargado no hace nada; con
keyring, recarga solo si otro proceso cambió `crypto_keys` (la marca de `refresh_if_stale`).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring, configure_keyring, current_keyring, refresh_current
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoKey
from app.core.crypto.provider import configure_provider


@pytest.fixture
def proveedor_del_proceso(proveedor_local: LocalFileProvider) -> Iterator[LocalFileProvider]:
    """`refresh_current` usa el proveedor del proceso, como el api tras el lifespan."""
    configure_provider(proveedor_local)
    try:
        yield proveedor_local
    finally:
        configure_provider(None)


class _CuentaCargas:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.cargas = 0
        original = Keyring.load_all
        cuenta = self

        async def contar(keyring: Keyring, session: AsyncSession, provider: object) -> None:
            cuenta.cargas += 1
            await original(keyring, session, provider)  # type: ignore[arg-type]

        monkeypatch.setattr(Keyring, "load_all", contar)


async def test_sin_keyring_cargado_no_hace_nada(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_keyring(None)
    cuenta = _CuentaCargas(monkeypatch)
    await refresh_current(session)
    assert cuenta.cargas == 0


async def test_sin_cambios_no_recarga(
    bus_listo: Keyring,
    session: AsyncSession,
    proveedor_del_proceso: LocalFileProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert current_keyring() is bus_listo
    cuenta = _CuentaCargas(monkeypatch)
    await refresh_current(session)
    await refresh_current(session)
    assert cuenta.cargas == 0


async def test_una_llave_nueva_de_otro_proceso_se_carga(
    bus_listo: Keyring,
    session: AsyncSession,
    proveedor_del_proceso: LocalFileProvider,
) -> None:
    nueva = CryptoKey(
        purpose="encrypt",
        data_class="member.document",
        algorithm="A256GCM",
        provider="local",
        version=2,
        state="decrypt_only",
        wrapped_material=await proveedor_del_proceso.wrap(b"\x02" * 32),
        created_by=SYSTEM_USER_ID,
    )
    with actor_scope(SYSTEM_USER_ID):
        session.add(nueva)
        await session.flush()
    assert bus_listo.get(nueva.id) is None
    await refresh_current(session)
    cargada = current_keyring().get(nueva.id)
    assert cargada is not None and bytes(cargada.material) == b"\x02" * 32
