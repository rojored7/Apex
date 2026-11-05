"""Suite de contrato del puerto `KeyProvider` (S5-B1; S5-D21, S5-D3, S5-D9; M-5a).

Parametrizada por `local`, `fake_transit` (`FakeTransit` sobre `httpx.MockTransport`) y
`openbao_real` (marcador `openbao`; se salta sin `OPENBAO_TEST_ADDR`). Las ramas que no aplican a
un proveedor se declaran con `pytest.skip` y su motivo, nunca se omiten en silencio.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.crypto.errors import CryptoError
from app.core.crypto.local_provider import SIGNING_KEY_REF
from app.core.crypto.openbao_provider import KEK_KEY, SIGN_KEY, OpenBaoProvider, parse_version
from tests.factories.fake_transit import FakeTransit

DEK = bytes(range(32))


def _firma_ref(proveedor: Any) -> str:
    return SIGNING_KEY_REF if proveedor.name == "local" else SIGN_KEY


async def test_name_identifica_al_proveedor(proveedor: Any, tipo: str) -> None:
    assert proveedor.name == ("local" if tipo == "local" else "openbao")


async def test_wrap_y_unwrap_ida_y_vuelta(proveedor: Any) -> None:
    envuelta = await proveedor.wrap(DEK)
    assert isinstance(envuelta, bytes) and envuelta != DEK
    assert await proveedor.unwrap(envuelta) == DEK


async def test_wrap_dos_veces_da_envolturas_distintas_con_la_misma_dek(proveedor: Any) -> None:
    primera, segunda = await proveedor.wrap(DEK), await proveedor.wrap(DEK)
    assert primera != segunda
    assert await proveedor.unwrap(primera) == await proveedor.unwrap(segunda) == DEK


@pytest.mark.parametrize("basura", [b"", b"basura", b"\x00" * 64, b"apxw1", b"vault:v1:"])
async def test_unwrap_de_basura_es_unwrap_failed(proveedor: Any, basura: bytes) -> None:
    with pytest.raises(CryptoError) as error:
        await proveedor.unwrap(basura)
    assert error.value.code == "unwrap_failed"


async def test_unwrap_de_una_envoltura_alterada_es_unwrap_failed(proveedor: Any) -> None:
    envuelta = bytearray(await proveedor.wrap(DEK))
    envuelta[-3] ^= 0x01
    with pytest.raises(CryptoError) as error:
        await proveedor.unwrap(bytes(envuelta))
    assert error.value.code == "unwrap_failed"


async def test_sign_y_verify(proveedor: Any) -> None:
    ref = _firma_ref(proveedor)
    firma = await proveedor.sign(ref, b"datos")
    assert isinstance(firma, bytes)
    assert await proveedor.verify(ref, b"datos", firma) is True
    assert await proveedor.verify(ref, b"otros datos", firma) is False


async def test_sign_de_una_llave_inexistente_es_key_missing(proveedor: Any, tipo: str) -> None:
    if tipo == "openbao_real":
        pytest.skip("Transit real responde 400 (no 404) al firmar con una llave inexistente")
    with pytest.raises(CryptoError) as error:
        await proveedor.sign("no-existe", b"datos")
    assert error.value.code == "key_missing"


async def test_status_ok(proveedor: Any) -> None:
    assert await proveedor.status() == "ok"


async def test_local_rewrap_no_esta_soportado(proveedor: Any, tipo: str) -> None:
    if tipo != "local":
        pytest.skip("solo el proveedor local no soporta rewrap")
    with pytest.raises(CryptoError) as error:
        await proveedor.rewrap(await proveedor.wrap(DEK))
    assert error.value.code == "unsupported"


async def test_rewrap_conserva_la_dek_y_sube_la_version(proveedor: Any, tipo: str) -> None:
    if tipo == "local":
        pytest.skip("rewrap no aplica al proveedor local (lanza unsupported)")
    if tipo == "openbao_real":
        pytest.skip("Transit real no conserva el AAD en rewrap (M-5a, S5-D55a): ver el veredicto")
    antigua = await proveedor.wrap(DEK)
    info = await proveedor.rotate(KEK_KEY)
    nueva = await proveedor.rewrap(antigua)
    assert parse_version(nueva) == info.version > parse_version(antigua)
    assert await proveedor.unwrap(nueva) == DEK
    assert await proveedor.unwrap(antigua) == DEK  # la versión anterior aún abre (sin --trim)


async def test_rotate_y_key_info_de_la_kek(proveedor: Any, tipo: str) -> None:
    if tipo == "local":
        pytest.skip("el proveedor local no rota llaves (lanza unsupported)")
    antes = await proveedor.key_info(KEK_KEY)
    despues = await proveedor.rotate(KEK_KEY)
    assert despues.version == antes.version + 1
    assert despues.key_ref == KEK_KEY and despues.provider == "openbao"
    assert (await proveedor.key_info(KEK_KEY)).version == despues.version


async def test_local_rotate_no_esta_soportado(proveedor: Any, tipo: str) -> None:
    if tipo != "local":
        pytest.skip("solo el proveedor local lanza unsupported")
    with pytest.raises(CryptoError) as error:
        await proveedor.rotate(KEK_KEY)
    assert error.value.code == "unsupported"


# AAD `apx-dek-wrap` en rewrap (M-5a) ----------------------------------------------------------


async def test_wrap_y_unwrap_van_con_el_aad_de_la_envoltura(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    """El AAD `apx-dek-wrap` (S5-D2) viaja en base64 en `associated_data` de encrypt y decrypt."""
    import base64

    esperado = base64.b64encode(b"apx-dek-wrap").decode("ascii")
    await openbao_fake.unwrap(await openbao_fake.wrap(DEK))
    for ruta in ("/encrypt/", "/decrypt/"):
        llamadas = fake_transit.llamadas(ruta)
        assert llamadas and llamadas[0].body["associated_data"] == esperado


async def test_rewrap_con_fake_que_no_acepta_aad_falla_cerrado(
    openbao_fake: OpenBaoProvider, fake_transit: FakeTransit
) -> None:
    """Si Transit ignorase el AAD en rewrap el descifrado interno falla: el proveedor lo informa
    como `unwrap_failed` y no devuelve una envoltura inservible (M-5a, decrypt+encrypt)."""
    antigua = await openbao_fake.wrap(DEK)
    fake_transit.rewrap_acepta_aad = False
    await openbao_fake.rotate(KEK_KEY)
    with pytest.raises(CryptoError) as error:
        await openbao_fake.rewrap(antigua)
    assert error.value.code == "unwrap_failed"


@pytest.mark.openbao
async def test_real_rewrap_no_conserva_el_aad_de_la_envoltura(
    openbao_real: OpenBaoProvider,
) -> None:
    """VEREDICTO M-5a (B1.7, OpenBao 2.7.2): `transit/rewrap` ignora `associated_data` y falla con
    "message authentication failed" sobre una DEK envuelta con AAD. El proveedor lo informa como
    `unwrap_failed` (falla cerrado) y S5-D55a manda: `rotate-kek` usa unwrap + wrap, no rewrap."""
    antigua = await openbao_real.wrap(DEK)
    await openbao_real.rotate(KEK_KEY)
    with pytest.raises(CryptoError) as error:
        await openbao_real.rewrap(antigua)
    assert error.value.code == "unwrap_failed"
    nueva = await openbao_real.wrap(await openbao_real.unwrap(antigua))
    assert parse_version(nueva) > parse_version(antigua)
    assert await openbao_real.unwrap(nueva) == DEK
