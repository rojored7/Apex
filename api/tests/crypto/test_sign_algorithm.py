"""El bus firma y verifica con el algoritmo y la clave pública de la FILA (S6-A1; D40, D62, D81).

Parametrizado por `tipo` (`local`, `fake_transit`, `openbao_real` con el marcador `openbao`):
- `bus.sign("audit.signature", ...)` etiqueta la firma con `llave.algorithm` (ya no con una
  constante del bus); la fila `sign` guarda la REFERENCIA del proveedor (`local:sign-ed25519` o
  `apex-sign-audit`), nunca material, y una referencia fuera del patrón da `bad_key_ref` (M-2b);
- `bus.verify` verifica con `crypto_keys.public_key` de la fila, en proceso: NO llama al proveedor
  (con el custodio sellado también verifica) y acepta llaves `decrypt_only` y `retired`;
- `KeyInfo.algorithm` y `KeyInfo.public_key`; `sign_public_key()` coincide con la derivada de la
  llave real; `verify_ed25519` con una pública ajena da falso; `ML-DSA-65` da `unsupported`;
- `ensure_keys` nunca crea filas `sign` (D72); `load_all(classes=...)` no hace `unwrap`; dos filas
  `active` de `(sign, audit.signature)` violan el índice único parcial (M-2e).
Rojo: `sign_key_ref`, `sign_public_key` y `verify_ed25519` son stubs; `LoadedKey.algorithm` y
`public_key` y `CryptoKey.public_key` aún no existen.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization  # noqa: TID251
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: TID251
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli import key_paths_in
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import bus
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import Keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoKey
from app.core.crypto.openbao_provider import SIGN_KEY
from app.core.crypto.signature import format_signature, verify_ed25519
from tests.crypto.conftest import CLASE_FIRMA, fila_sign
from tests.factories.fake_provider import ProveedorControlable
from tests.factories.fake_transit import FakeTransit

PAYLOAD = b"apex-audit-sig-v1\n1\n" + b"ab" * 32
REFERENCIA = {"local": "local:sign-ed25519", "fake_transit": SIGN_KEY, "openbao_real": SIGN_KEY}


def _b64_raw(privada: Ed25519PrivateKey) -> str:
    cruda = privada.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(cruda).decode("ascii")


@pytest.fixture
async def bus_firma(sin_llaves: AsyncSession, proveedor: Any) -> Any:
    """`ensure_keys` con el proveedor bajo prueba y la fila `sign` que crea `init-keys` (D72)."""
    with actor_scope(SYSTEM_USER_ID):
        keyring = await ensure_keys(sin_llaves, proveedor, lambda _n: proveedor)
        fila = await fila_sign(sin_llaves, proveedor)
        await keyring.load_all(sin_llaves, lambda _n: proveedor)
        yield keyring, fila


# Algoritmo y referencia por fila ----------------------------------------------------------------


async def test_sign_etiqueta_con_el_algoritmo_de_la_llave(bus_firma: Any) -> None:
    keyring, fila = bus_firma

    firma = await bus.sign(CLASE_FIRMA, PAYLOAD)

    llave = keyring.active_for("sign", CLASE_FIRMA)
    partes = firma.split(".")
    assert llave.algorithm == fila.algorithm == "Ed25519"
    assert partes[0] == "apx1" and partes[1] == str(fila.id) and partes[2] == llave.algorithm
    assert await bus.verify(CLASE_FIRMA, PAYLOAD, firma) is True
    assert await bus.verify(CLASE_FIRMA, PAYLOAD + b"x", firma) is False


async def test_la_fila_guarda_la_referencia_del_proveedor_no_material(
    bus_firma: Any, proveedor: Any, tipo: str
) -> None:
    _, fila = bus_firma

    assert proveedor.sign_key_ref() == REFERENCIA[tipo]
    assert fila.wrapped_material == REFERENCIA[tipo].encode("ascii")
    assert fila.provider == proveedor.name


@pytest.mark.parametrize(
    "referencia",
    [b"apex-kek", b"APEX-SIGN-AUDIT", b"apex-sign-audit/../x", b"../etc/passwd", b"", b"otra"],
    ids=["la_kek", "mayusculas", "ruta", "traversal", "vacia", "ajena"],
)
async def test_una_referencia_fuera_del_patron_es_bad_key_ref(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider, referencia: bytes
) -> None:
    """M-2b: `^apex-sign-audit[a-z0-9-]*$` (OpenBao) o exactamente `local:sign-ed25519` (local).
    Una fila `sign` con otra referencia no firma: ni la KEK, ni una ruta."""
    with actor_scope(SYSTEM_USER_ID):
        keyring = await ensure_keys(sin_llaves, proveedor_local, lambda _n: proveedor_local)
        sin_llaves.add(
            CryptoKey(
                purpose="sign",
                data_class=CLASE_FIRMA,
                algorithm="Ed25519",
                provider="local",
                version=1,
                state="active",
                wrapped_material=referencia,
                public_key=_b64_raw(Ed25519PrivateKey.generate()),
                created_by=SYSTEM_USER_ID,
            )
        )
        await sin_llaves.flush()

        with pytest.raises(CryptoError) as error:
            await keyring.load_all(sin_llaves, lambda _n: proveedor_local)
            await bus.sign(CLASE_FIRMA, PAYLOAD)

    assert error.value.code == "bad_key_ref"


# Verificación con la clave pública --------------------------------------------------------------


async def test_verify_acepta_llaves_decrypt_only_y_retired_por_key_id(
    bus_firma: Any, sin_llaves: AsyncSession, proveedor: Any
) -> None:
    keyring, fila = bus_firma
    firma = await bus.sign(CLASE_FIRMA, PAYLOAD)
    fila.state = "decrypt_only"
    fila.rotated_at = datetime(2026, 11, 11, tzinfo=UTC)
    await sin_llaves.flush()
    await keyring.refresh_if_stale(sin_llaves, proveedor)
    assert await bus.verify(CLASE_FIRMA, PAYLOAD, firma) is True

    fila.state = "retired"
    await sin_llaves.flush()
    await keyring.refresh_if_stale(sin_llaves, proveedor)

    assert await bus.verify(CLASE_FIRMA, PAYLOAD, firma) is True
    with pytest.raises(CryptoError):
        await bus.sign(CLASE_FIRMA, PAYLOAD)  # sin llave activa


async def test_verify_no_llama_al_proveedor(
    bus_firma: Any, proveedor: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D62 y D81: ni `verify` del proveedor ni, con Transit, una sola llamada a `/verify/`."""
    firma = await bus.sign(CLASE_FIRMA, PAYLOAD)
    llamadas: list[str] = []

    async def prohibido(*_a: Any, **_k: Any) -> bool:
        llamadas.append("provider.verify")
        raise AssertionError("bus.verify no debe llamar al proveedor")

    monkeypatch.setattr(proveedor, "verify", prohibido)

    assert await bus.verify(CLASE_FIRMA, PAYLOAD, firma) is True
    assert await bus.verify(CLASE_FIRMA, PAYLOAD + b"x", firma) is False
    assert llamadas == []


async def test_verify_funciona_con_el_custodio_sellado(
    sin_llaves: AsyncSession, openbao_fake: Any, fake_transit: FakeTransit
) -> None:
    """Con OpenBao sellado `bus.verify` sigue verificando (la firma era anterior al sellado)."""
    with actor_scope(SYSTEM_USER_ID):
        keyring = await ensure_keys(sin_llaves, openbao_fake, lambda _n: openbao_fake)
        await fila_sign(sin_llaves, openbao_fake)
        await keyring.load_all(sin_llaves, lambda _n: openbao_fake)
        firma = await bus.sign(CLASE_FIRMA, PAYLOAD)
        fake_transit.seal()

        assert await bus.verify(CLASE_FIRMA, PAYLOAD, firma) is True
        assert await bus.verify(CLASE_FIRMA, PAYLOAD + b"x", firma) is False

    assert fake_transit.llamadas("/verify/") == []


async def test_una_clave_publica_alterada_en_la_fila_no_verifica(
    bus_firma: Any, sin_llaves: AsyncSession, proveedor: Any
) -> None:
    """La verificación depende de `public_key`: con la de otra llave la firma no verifica."""
    keyring, fila = bus_firma
    firma = await bus.sign(CLASE_FIRMA, PAYLOAD)
    ajena = _b64_raw(Ed25519PrivateKey.generate())
    llave = keyring.get(fila.id)
    assert llave is not None
    llave.public_key = ajena  # lo que el keyring cargó de la fila

    assert await bus.verify(CLASE_FIRMA, PAYLOAD, firma) is False


async def test_ml_dsa_65_no_se_verifica_en_v03(bus_firma: Any, sin_llaves: AsyncSession) -> None:
    """EP-26: un `algorithm = ML-DSA-65` en la fila da `unsupported`, no un falso silencioso."""
    keyring, fila = bus_firma
    llave = keyring.get(fila.id)
    assert llave is not None
    llave.algorithm = "ML-DSA-65"
    firma = format_signature(fila.id, "ML-DSA-65", b"\x00" * 64)

    with pytest.raises(CryptoError) as error:
        await bus.verify(CLASE_FIRMA, PAYLOAD, firma)

    assert error.value.code == "unsupported"


# verify_ed25519 ---------------------------------------------------------------------------------


def test_verify_ed25519_acepta_la_firma_y_rechaza_datos_o_clave_ajenos() -> None:
    privada, ajena = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    firma = privada.sign(PAYLOAD)

    assert verify_ed25519(_b64_raw(privada), PAYLOAD, firma) is True
    assert verify_ed25519(_b64_raw(privada), PAYLOAD + b"x", firma) is False
    assert verify_ed25519(_b64_raw(ajena), PAYLOAD, firma) is False
    assert verify_ed25519(_b64_raw(privada), PAYLOAD, firma[:-1] + bytes([firma[-1] ^ 1])) is False
    assert verify_ed25519(_b64_raw(privada), PAYLOAD, b"corta") is False


# KeyInfo y sign_public_key ----------------------------------------------------------------------


async def test_key_info_de_la_llave_de_firma_trae_algoritmo_y_clave_publica(proveedor: Any) -> None:
    info = await proveedor.key_info(proveedor.sign_key_ref())

    assert info.algorithm == "Ed25519"  # Transit dice `ed25519`; el puerto normaliza (D81)
    assert info.public_key is not None
    assert len(base64.b64decode(info.public_key, validate=True)) == 32
    assert info.public_key == await proveedor.sign_public_key()


async def test_sign_public_key_local_coincide_con_la_derivada_del_archivo(
    proveedor_local: LocalFileProvider, claves_prueba: Any
) -> None:
    semilla = key_paths_in(claves_prueba).signing_key.read_bytes()

    esperada = _b64_raw(Ed25519PrivateKey.from_private_bytes(semilla))

    assert await proveedor_local.sign_public_key() == esperada
    assert proveedor_local.sign_key_ref() == "local:sign-ed25519"


async def test_sign_public_key_de_transit_coincide_con_key_info_y_con_la_llave_del_fake(
    openbao_fake: Any, fake_transit: FakeTransit
) -> None:
    privada = fake_transit._material[SIGN_KEY][0]

    publica = await openbao_fake.sign_public_key()

    assert publica == (await openbao_fake.key_info(SIGN_KEY)).public_key == _b64_raw(privada)
    assert openbao_fake.sign_key_ref() == SIGN_KEY


async def test_key_info_de_un_tipo_de_firma_no_soportado_es_unsupported(
    token_file: Any,
) -> None:
    """`ed25519 -> Ed25519`; otro tipo asimétrico (por ejemplo `ecdsa-p256`) -> `unsupported`."""
    from app.core.crypto.openbao_provider import OpenBaoProvider
    from tests.factories.fake_transit import ADDR_FAKE

    fake = FakeTransit(llaves={"apex-kek": "aes256-gcm96", "firma-p256": "ecdsa-p256"})
    proveedor = OpenBaoProvider(ADDR_FAKE, token_file, timeout_s=2.0, client=fake.cliente())

    with pytest.raises(CryptoError) as error:
        await proveedor.key_info("firma-p256")

    assert error.value.code == "unsupported"


# Bootstrap, keyring e índice único --------------------------------------------------------------


async def test_ensure_keys_no_crea_filas_sign_aunque_el_registro_tenga_la_clase(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> None:
    """D72: solo `init-keys --data-class audit.signature` crea la fila `sign`."""
    with actor_scope(SYSTEM_USER_ID):
        await ensure_keys(sin_llaves, proveedor_local, lambda _n: proveedor_local)
    filas = (await sin_llaves.scalars(select(CryptoKey).where(CryptoKey.purpose == "sign"))).all()

    assert list(filas) == []


async def test_load_all_con_classes_de_firma_no_hace_unwrap(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> None:
    """D42 (worker `sign_audit`): el keyring de la firma no abre ninguna DEK."""
    with actor_scope(SYSTEM_USER_ID):
        await ensure_keys(sin_llaves, proveedor_local, lambda _n: proveedor_local)
        await fila_sign(sin_llaves, proveedor_local)
    espia = ProveedorControlable(proveedor_local)
    nuevo = Keyring()

    with actor_scope(SYSTEM_USER_ID):
        await nuevo.load_all(sin_llaves, lambda _n: espia, classes=frozenset({CLASE_FIRMA}))

    assert espia.unwrap_calls == 0
    assert [(k.purpose, k.data_class) for k in nuevo.keys()] == [("sign", CLASE_FIRMA)]
    llave = nuevo.active_for("sign", CLASE_FIRMA)
    assert llave.algorithm == "Ed25519" and llave.public_key is not None


async def test_dos_filas_active_de_la_misma_clase_de_firma_violan_el_indice_unico(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> None:
    """M-2e: `uq_crypto_keys_active` sobre `(purpose, data_class) WHERE state = 'active'`."""
    await fila_sign(sin_llaves, proveedor_local)

    with pytest.raises(IntegrityError) as error:
        async with sin_llaves.begin_nested():
            await fila_sign(sin_llaves, proveedor_local, version=2)

    assert "uq_crypto_keys_active" in str(error.value)
