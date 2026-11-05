"""Proveedor por fila del keyring (S5-B1; S5-D3, S5-D50 H-2.3, S5-D131).

Cada fila de `crypto_keys` se abre con el proveedor que nombra su columna `provider`; `local` solo
se construye si hay filas `encrypt|index` `local`; las filas `sign` `local` guardan una
referencia y no piden la KEK; las llaves nuevas nacen en el proveedor de creación (`name`).
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import provider as provider_mod
from app.core.crypto import service
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.crypto.local_provider import SIGNING_KEY_REF, LocalFileProvider
from app.core.crypto.models import CryptoKey
from app.core.crypto.openbao_provider import OpenBaoProvider
from app.core.crypto.provider import KeyProvider, ProviderResolver, configure_provider
from app.core.crypto.registry import encrypting_specs, indexing_specs
from tests.factories.fake_transit import FakeTransit

DOC, TEL, MAIL = "member.document", "member.phone", "member.email"
ALGORITMO = {"encrypt": "A256GCM", "index": "HMAC-SHA256", "sign": "Ed25519"}


def _resolver(**proveedores: KeyProvider) -> tuple[ProviderResolver, list[str]]:
    """Resolver que anota cada nombre pedido y falla con `kek_missing` si no hay proveedor."""
    pedidos: list[str] = []

    def resolver(nombre: str) -> KeyProvider:
        pedidos.append(nombre)
        if nombre not in proveedores:
            raise CryptoError("kek_missing", f"no hay proveedor {nombre} en esta prueba")
        return proveedores[nombre]

    return resolver, pedidos


async def _fila(
    session: AsyncSession,
    proveedor: KeyProvider | None,
    nombre: str,
    clase: str,
    *,
    purpose: str = "encrypt",
    envuelta: bytes | None = None,
) -> tuple[CryptoKey, bytes]:
    """Inserta una fila `active`: la DEK envuelta con `proveedor` (o `envuelta` tal cual)."""
    dek = os.urandom(32)
    if envuelta is None:
        assert proveedor is not None
        envuelta = await proveedor.wrap(dek)
    fila = CryptoKey(
        id=uuid4(),
        purpose=purpose,
        data_class=clase,
        algorithm=ALGORITMO[purpose],
        provider=nombre,
        version=1,
        state="active",
        wrapped_material=envuelta,
        created_by=SYSTEM_USER_ID,
    )
    with actor_scope(SYSTEM_USER_ID):
        session.add(fila)
        await session.flush()
    return fila, dek


# Filas mixtas ----------------------------------------------------------------------------------


async def test_filas_mixtas_se_abren_cada_una_con_su_proveedor(
    sin_llaves: AsyncSession,
    proveedor_local: LocalFileProvider,
    openbao_fake: OpenBaoProvider,
    fake_transit: FakeTransit,
) -> None:
    local, dek_local = await _fila(sin_llaves, proveedor_local, "local", DOC)
    remota, dek_remota = await _fila(sin_llaves, openbao_fake, "openbao", TEL)
    fake_transit.calls.clear()
    resolver, pedidos = _resolver(local=proveedor_local, openbao=openbao_fake)

    with actor_scope(SYSTEM_USER_ID):
        llavero = Keyring()
        await llavero.load_all(sin_llaves, resolver)

    cargada_local, cargada_remota = llavero.get(local.id), llavero.get(remota.id)
    assert cargada_local is not None and bytes(cargada_local.material) == dek_local
    assert cargada_remota is not None and bytes(cargada_remota.material) == dek_remota
    assert set(pedidos) == {"local", "openbao"}
    assert len(fake_transit.llamadas("/decrypt/")) == 1  # solo la fila `openbao` fue a Transit


async def test_local_no_se_construye_si_no_hay_filas_local(
    sin_llaves: AsyncSession, openbao_fake: OpenBaoProvider
) -> None:
    await _fila(sin_llaves, openbao_fake, "openbao", DOC)
    await _fila(sin_llaves, openbao_fake, "openbao", TEL, purpose="index")
    resolver, pedidos = _resolver(openbao=openbao_fake)  # `local` falla si se pide (sin kek.bin)

    with actor_scope(SYSTEM_USER_ID):
        await Keyring().load_all(sin_llaves, resolver)

    assert "local" not in pedidos


async def test_el_api_arranca_sin_kek_con_una_fila_sign_local(
    sin_llaves: AsyncSession, openbao_fake: OpenBaoProvider
) -> None:
    """H-2.3: una fila `sign` `local` guarda una referencia, no material envuelto; cargar el
    keyring no necesita la KEK local."""
    await _fila(sin_llaves, openbao_fake, "openbao", DOC)
    firma, _ = await _fila(
        sin_llaves,
        None,
        "local",
        "audit.chain",
        purpose="sign",
        envuelta=SIGNING_KEY_REF.encode("ascii"),
    )
    resolver, pedidos = _resolver(openbao=openbao_fake)

    with actor_scope(SYSTEM_USER_ID):
        llavero = Keyring()
        await llavero.load_all(sin_llaves, resolver)

    assert "local" not in pedidos
    cargada = llavero.get(firma.id)
    assert cargada is not None and bytes(cargada.material) == SIGNING_KEY_REF.encode("ascii")


# Creación --------------------------------------------------------------------------------------


async def test_create_missing_escribe_provider_name(
    sin_llaves: AsyncSession, openbao_fake: OpenBaoProvider
) -> None:
    resolver, pedidos = _resolver(openbao=openbao_fake)

    with actor_scope(SYSTEM_USER_ID):
        llavero = await ensure_keys(sin_llaves, openbao_fake, resolver)
    configure_keyring(None)

    filas = list((await sin_llaves.scalars(select(CryptoKey))).all())
    esperadas = len(encrypting_specs()) + len(indexing_specs())
    assert len(filas) == esperadas and esperadas > 0
    assert {f.provider for f in filas if f.purpose != "sign"} == {"openbao"}
    assert all(f.wrapped_material.startswith(b"vault:v1:") for f in filas if f.purpose != "sign")
    assert "local" not in pedidos
    assert len(llavero.keys()) == esperadas


async def test_swap_key_envuelve_con_el_proveedor_de_creacion(
    sin_llaves: AsyncSession,
    proveedor_local: LocalFileProvider,
    openbao_fake: OpenBaoProvider,
    fake_transit: FakeTransit,
) -> None:
    """Las llaves viejas siguen `local`; la rotación nace en el proveedor de creación
    (`CRYPTO_PROVIDER`, el configurado en el proceso), no en `old.provider` ni en el keyring."""
    with actor_scope(SYSTEM_USER_ID):
        await ensure_keys(sin_llaves, proveedor_local, lambda _n: proveedor_local)
    previo = provider_mod._provider
    configure_provider(openbao_fake)
    try:
        vieja = (
            await sin_llaves.scalars(
                select(CryptoKey).where(
                    CryptoKey.purpose == "encrypt",
                    CryptoKey.data_class == DOC,
                    CryptoKey.state == "active",
                )
            )
        ).one()
        with actor_scope(SYSTEM_USER_ID):
            nueva, _dek = await service._swap_key(sin_llaves, vieja, SYSTEM_USER_ID)
    finally:
        configure_provider(previo)
        configure_keyring(None)

    assert nueva.provider == "openbao"
    assert nueva.wrapped_material.startswith(b"vault:v1:")
    assert fake_transit.llamadas("/encrypt/")
    assert vieja.state == "decrypt_only" and vieja.provider == "local"


# Filtro por clase ------------------------------------------------------------------------------


async def test_load_all_con_classes_abre_solo_esas_clases(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider, openbao_fake: OpenBaoProvider
) -> None:
    doc, _ = await _fila(sin_llaves, proveedor_local, "local", DOC)
    await _fila(sin_llaves, openbao_fake, "openbao", MAIL)
    resolver, pedidos = _resolver(local=proveedor_local)  # `openbao` fallaría si se pidiera

    with actor_scope(SYSTEM_USER_ID):
        llavero = Keyring()
        await llavero.load_all(sin_llaves, resolver, classes=frozenset({DOC}))

    assert {k.data_class for k in llavero.keys()} == {DOC}
    assert llavero.get(doc.id) is not None
    assert "openbao" not in pedidos


async def test_load_all_con_classes_vacio_no_abre_nada(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> None:
    await _fila(sin_llaves, proveedor_local, "local", DOC)
    resolver, _ = _resolver(local=proveedor_local)

    with actor_scope(SYSTEM_USER_ID):
        llavero = Keyring()
        await llavero.load_all(sin_llaves, resolver, classes=frozenset())

    assert llavero.keys() == []


# Prefijo y columna no coinciden ----------------------------------------------------------------


async def test_columna_openbao_con_envoltura_local_es_unwrap_failed(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider, openbao_fake: OpenBaoProvider
) -> None:
    envuelta_local = await proveedor_local.wrap(os.urandom(32))
    await _fila(sin_llaves, None, "openbao", DOC, envuelta=envuelta_local)
    resolver, _ = _resolver(local=proveedor_local, openbao=openbao_fake)

    with pytest.raises(CryptoError) as error, actor_scope(SYSTEM_USER_ID):
        await Keyring().load_all(sin_llaves, resolver)

    assert error.value.code == "unwrap_failed"
    assert not isinstance(error.value, CryptoUnavailable)


async def test_columna_local_con_envoltura_de_transit_es_unwrap_failed(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider, openbao_fake: OpenBaoProvider
) -> None:
    envuelta_remota = await openbao_fake.wrap(os.urandom(32))
    await _fila(sin_llaves, None, "local", DOC, envuelta=envuelta_remota)
    resolver, _ = _resolver(local=proveedor_local, openbao=openbao_fake)

    with pytest.raises(CryptoError) as error, actor_scope(SYSTEM_USER_ID):
        await Keyring().load_all(sin_llaves, resolver)

    assert error.value.code == "unwrap_failed"


# Resolver por nombre ---------------------------------------------------------------------------


def test_get_provider_named_desconocido_es_unknown_provider() -> None:
    from app.core.config import Settings

    with pytest.raises(CryptoError) as error:
        provider_mod.get_provider_named(Settings.model_construct(), "nube")
    assert error.value.code == "unknown_provider"


# S5-D192: `keyring.provider` solo cambia tras un unwrap exitoso ----------------------------------


async def test_el_proveedor_del_keyring_no_cambia_si_el_unwrap_falla(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider, openbao_fake: OpenBaoProvider
) -> None:
    envuelta_local = await proveedor_local.wrap(os.urandom(32))
    await _fila(sin_llaves, None, "openbao", DOC, envuelta=envuelta_local)  # no abre con openbao
    resolver, _ = _resolver(local=proveedor_local, openbao=openbao_fake)
    llavero = Keyring()
    llavero.provider = proveedor_local

    with pytest.raises(CryptoError), actor_scope(SYSTEM_USER_ID):
        await llavero.load_all(sin_llaves, resolver)

    assert llavero.provider is proveedor_local


async def test_el_proveedor_del_keyring_es_el_ultimo_que_abrio_una_fila(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider, openbao_fake: OpenBaoProvider
) -> None:
    await _fila(sin_llaves, openbao_fake, "openbao", DOC)
    resolver, _ = _resolver(local=proveedor_local, openbao=openbao_fake)
    llavero = Keyring()
    llavero.provider = proveedor_local

    with actor_scope(SYSTEM_USER_ID):
        await llavero.load_all(sin_llaves, resolver)

    assert llavero.provider is openbao_fake
