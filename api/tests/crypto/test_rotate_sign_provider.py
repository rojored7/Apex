"""Efectos del cambio de proveedor de la llave de firma sobre la firma, la verificación y el retiro
(S6-A2, D81, M-2a). Rojo A2.

El estado posterior a `rotate-key audit.signature --provider openbao` se construye a mano
(`rotar_a_mano`: v1 `decrypt_only` `local`, v2 `active` `openbao`); la parte del comando va en
`tests/cli/test_rotate_sign_provider.py`. Aquí:
- `sign_latest` siguiente firma con la v2 y `crypto_ops(sign)` lleva su `key_id`;
- una firma de la v1 verifica por `key_id` con su clave pública, SIN llamar a ningún proveedor;
- retirar la v1 mientras existan firmas con su `key_id`: `ValueError` `signatures_reference_key`
  y ninguna transición; sin firmas que la referencien, el retiro sigue como hoy.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.audit_sign import latest_signature
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import bus
from app.core.crypto.models import CryptoKey, CryptoOp
from app.core.crypto.service import retire_key
from tests.crypto._firma_proveedor import (
    agregar_y_firmar,
    cargar_keyring,
    instantanea_firmas,
    rotar_a_mano,
    sembrar_firmas,
)
from tests.crypto._migracion import Entorno, migracion_lista
from tests.crypto._rotacion import rotacion_lista
from tests.crypto.conftest import fila_sign
from tests.factories.audit_chain import hash_of
from tests.factories.signatures import payload_de

pytestmark = pytest.mark.usefixtures("reloj")
__all__ = ["migracion_lista", "rotacion_lista"]


async def _estados(e: Entorno) -> list[tuple[int, str, str]]:
    async with e.fabrica() as sesion:
        filas = await sesion.scalars(
            select(CryptoKey).where(CryptoKey.purpose == "sign").order_by(CryptoKey.version)
        )
        return [(k.version, k.state, k.provider) for k in filas]


async def test_la_siguiente_firma_usa_la_llave_nueva_y_crypto_ops_lleva_su_key_id(
    migracion_lista: Entorno,
) -> None:
    e = migracion_lista
    sembrado = await sembrar_firmas(e)
    v2 = await rotar_a_mano(e, sembrado.v1)
    await cargar_keyring(e)

    salida = await agregar_y_firmar(e, 2)

    assert salida.kind == "signed"
    async with e.fabrica() as sesion:
        ultima = await latest_signature(sesion)
        ops = list(
            await sesion.scalars(
                select(CryptoOp).where(CryptoOp.verb == "sign", CryptoOp.key_id == v2)
            )
        )
    assert ultima is not None and ultima.key_id == v2
    assert len(ops) == 1 and ops[0].result == "ok"
    assert [f[4] for f in await instantanea_firmas(e.fabrica)] == [sembrado.v1, sembrado.v1, v2]


async def test_una_firma_de_la_llave_anterior_verifica_por_key_id_sin_llamar_al_proveedor(
    migracion_lista: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = migracion_lista
    sembrado = await sembrar_firmas(e)
    await rotar_a_mano(e, sembrado.v1)
    await cargar_keyring(e)

    def prohibido(*_a: object, **_k: object) -> None:
        raise AssertionError("verificar no debe llamar al proveedor")

    for proveedor in (e.local, e.openbao):
        for metodo in ("sign", "verify", "unwrap", "key_info"):
            monkeypatch.setattr(proveedor, metodo, prohibido)
    seguidas = 0
    async with e.fabrica() as sesion:
        for _, through_seq, _hash, firma, key_id, *_ in sembrado.firmas:
            hash_ = await hash_of(sesion, through_seq)
            assert hash_ is not None and key_id == sembrado.v1
            assert await bus.verify("audit.signature", payload_de(through_seq, hash_), firma)
            seguidas += 1
    assert seguidas == 2


async def test_retirar_la_v1_con_firmas_que_la_referencian_sale_con_signatures_reference_key(
    migracion_lista: Entorno,
) -> None:
    e = migracion_lista
    sembrado = await sembrar_firmas(e)
    await rotar_a_mano(e, sembrado.v1)
    antes = await _estados(e)

    with actor_scope(SYSTEM_USER_ID):
        async with e.fabrica() as sesion:
            with pytest.raises(ValueError, match="signatures_reference_key"):
                async with sesion.begin():
                    await retire_key(
                        sesion, sembrado.v1, confirmed_audit_blobs=0, actor=SYSTEM_USER_ID
                    )

    assert await _estados(e) == antes == [(1, "decrypt_only", "local"), (2, "active", "openbao")]
    assert await instantanea_firmas(e.fabrica) == sembrado.firmas


async def test_retirar_una_llave_sign_sin_firmas_sigue_como_hoy(migracion_lista: Entorno) -> None:
    e = migracion_lista
    async with e.fabrica() as sesion:
        with actor_scope(SYSTEM_USER_ID):
            vieja = await fila_sign(sesion, e.local, state="decrypt_only")
            await fila_sign(sesion, e.openbao, version=2)
            await sesion.commit()
        vieja_id: UUID = vieja.id

    with actor_scope(SYSTEM_USER_ID):
        async with e.fabrica() as sesion, sesion.begin():
            await retire_key(sesion, vieja_id, confirmed_audit_blobs=0, actor=SYSTEM_USER_ID)

    assert await _estados(e) == [(1, "retired", "local"), (2, "active", "openbao")]


# S5-D50: con CRYPTO_PROVIDER=openbao el worker no monta `keys` -----------------------------------

SIN_VOLUMEN = "el worker no monta el volumen keys"


async def test_switch_provider_a_local_con_openbao_se_rechaza_antes_de_tocar_la_base(
    migracion_lista: Entorno, settings_prueba: Settings
) -> None:
    from app.core.crypto.sign_rotation import SignRotationError, switch_provider

    e = migracion_lista
    await sembrar_firmas(e)
    v2 = await rotar_a_mano(e, (await _estados_ids(e))[0])
    antes = await _estados(e)
    ajustes = settings_prueba.model_copy(update={"CRYPTO_PROVIDER": "openbao"})

    with actor_scope(SYSTEM_USER_ID):
        async with e.fabrica() as sesion:
            with pytest.raises(SignRotationError, match=SIN_VOLUMEN):
                await switch_provider(
                    sesion, ajustes, "audit.signature", "local", "x", SYSTEM_USER_ID
                )

    assert await _estados(e) == antes
    assert v2 is not None


async def _estados_ids(e: Entorno) -> list[UUID]:
    async with e.fabrica() as sesion:
        return list(
            await sesion.scalars(
                select(CryptoKey.id).where(CryptoKey.purpose == "sign").order_by(CryptoKey.version)
            )
        )


def test_provider_rejection_solo_rechaza_local_con_openbao(settings_prueba: Settings) -> None:
    from app.core.crypto.sign_rotation import provider_rejection

    openbao = settings_prueba.model_copy(update={"CRYPTO_PROVIDER": "openbao"})

    assert provider_rejection(openbao, "local") is not None
    assert SIN_VOLUMEN in (provider_rejection(openbao, "local") or "")
    assert provider_rejection(openbao, "openbao") is None
    assert provider_rejection(settings_prueba, "local") is None
    assert provider_rejection(settings_prueba, "openbao") is None
