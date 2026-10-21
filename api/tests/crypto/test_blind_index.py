"""`bus.blind_index` con llaves `index` reales (US-026 T7)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import bus
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import Keyring
from app.core.crypto.models import CryptoKey

HEX = set("0123456789abcdef")


def test_variantes_del_documento_dan_el_mismo_indice(bus_listo: Keyring) -> None:
    indices = {
        bus.blind_index("member.document", v)
        for v in ("1.020.304", "1020304", " 1020304 ", "1020-304")
    }
    assert len(indices) == 1
    [indice] = indices
    assert len(indice) == 64 and set(indice) <= HEX


def test_misma_entrada_en_clases_distintas_da_indices_distintos(bus_listo: Keyring) -> None:
    assert bus.blind_index("member.document", "3001234567") != bus.blind_index(
        "member.phone", "3001234567"
    )


def test_determinista_y_telefono_normalizado(bus_listo: Keyring) -> None:
    assert bus.blind_index("member.phone", "+57 300 123 4567") == bus.blind_index(
        "member.phone", "3001234567"
    )
    assert bus.blind_index("member.email", " Ana.Perez@Mail.com ") == bus.blind_index(
        "member.email", "ana.perez@mail.com"
    )


def test_clase_sin_indice_y_valor_vacio(bus_listo: Keyring) -> None:
    with pytest.raises(CryptoError) as sin_indice:
        bus.blind_index("member.birth_date", "2000-01-01")
    assert sin_indice.value.code == "no_index"
    with pytest.raises(CryptoError) as vacio:
        bus.blind_index("member.document", " . ")
    assert vacio.value.code == "empty_value"


async def test_arranque_crea_tres_llaves_index_envueltas(
    bus_listo: Keyring, session: AsyncSession
) -> None:
    llaves = (await session.scalars(select(CryptoKey).where(CryptoKey.purpose == "index"))).all()
    assert sorted(k.data_class for k in llaves) == [
        "member.document",
        "member.email",
        "member.phone",
    ]
    for llave in llaves:
        assert llave.algorithm == "HMAC-SHA256" and llave.state == "active"
        abierta = bus_listo.get(llave.id)
        assert abierta is not None and bytes(abierta.material) != llave.wrapped_material
