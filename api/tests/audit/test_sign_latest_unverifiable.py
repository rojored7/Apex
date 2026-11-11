"""Autoverificación de la firma (S6-A1, ronda 4; H1/M3): `sign_latest` no guarda una firma que no
verifique con la clave pública de la fila `sign`.

Si el proveedor rotó fuera del flujo (una versión nueva de la llave en Transit, otra semilla en el
archivo local) la fila conserva la pública antigua: `bus.sign` lanza `signature_unverifiable`, deja
`crypto_ops(sign)` con `result = error` y `audit.signatures` queda sin fila nueva.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli import key_paths_in
from app.core import audit_sign
from app.core.audit_sign import AuditSignature
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.errors import CryptoError
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoOp
from app.core.crypto.openbao_provider import SIGN_KEY
from tests.audit.conftest import CadenaDePrueba
from tests.crypto.conftest import (  # noqa: F401  (fixtures del proveedor Transit falso)
    fake_transit,
    fila_sign,
    openbao_fake,
    token_file,
)


async def _firmas(session: AsyncSession) -> list[AuditSignature]:
    return list((await session.scalars(select(AuditSignature))).all())


async def _ops_error(session: AsyncSession) -> list[CryptoOp]:
    await session.flush()
    return list(
        (
            await session.scalars(
                select(CryptoOp).where(CryptoOp.verb == "sign", CryptoOp.result == "error")
            )
        ).all()
    )


async def test_transit_rotado_fuera_del_flujo_no_firma(
    sin_llaves: AsyncSession,
    audit_chain_factory: CadenaDePrueba,
    openbao_fake: Any,  # noqa: F811
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        keyring = await ensure_keys(sin_llaves, openbao_fake, lambda _n: openbao_fake)
        await fila_sign(sin_llaves, openbao_fake)
        await keyring.load_all(sin_llaves, lambda _n: openbao_fake)
        await audit_chain_factory.make(3)
        await openbao_fake.rotate(SIGN_KEY)  # `bao write -f transit/keys/.../rotate` a mano

        with pytest.raises(CryptoError) as error:
            await audit_sign.sign_latest(sin_llaves)

    assert error.value.code == "signature_unverifiable"
    assert await _firmas(sin_llaves) == []
    await sin_llaves.commit()
    assert len(await _ops_error(sin_llaves)) == 1


async def test_semilla_local_cambiada_no_firma(
    sin_llaves: AsyncSession,
    audit_chain_factory: CadenaDePrueba,
    proveedor_local: LocalFileProvider,
    claves_prueba: Path,
    tmp_path: Path,
) -> None:
    otra = tmp_path / "otra-semilla.key"
    otra.write_bytes(os.urandom(32))
    otra.chmod(0o600)
    cambiado = LocalFileProvider(key_paths_in(claves_prueba).kek, otra)
    with actor_scope(SYSTEM_USER_ID):
        keyring = await ensure_keys(sin_llaves, proveedor_local, lambda _n: proveedor_local)
        await fila_sign(sin_llaves, proveedor_local)  # la pública es la de la semilla original
        await keyring.load_all(sin_llaves, lambda _n: cambiado)  # el archivo ahora trae otra
        await audit_chain_factory.make(3)

        with pytest.raises(CryptoError) as error:
            await audit_sign.sign_latest(sin_llaves)

    assert error.value.code == "signature_unverifiable"
    assert await _firmas(sin_llaves) == []
    await sin_llaves.commit()
    assert len(await _ops_error(sin_llaves)) == 1
