"""Verificación de las firmas de la cadena (S6-A3, US-142; S6-D10, S6-D36, S6-D62, S6-D81). Rojo A3.

`run_verification` recorre la cadena y, además, `verify_signatures(session, *, through_seq)`
comprueba TODAS las firmas de `audit.signatures` con `through_seq` dentro del tramo recorrido, por
lotes de 100, en el api y con la clave pública guardada en `crypto_keys.public_key` de su `key_id`
(en cualquier estado de la llave). Contrato que fija el Rojo:
- cadena sana con tres firmas: `ok`, `signatures_checked = signatures_valid = 3`, la última válida
  es la de mayor `through_seq` (con su fecha y su algoritmo) y las seis columnas nuevas quedan
  guardadas en la fila de `audit.verifications`; sin firmas el estado es `none` y `ok` sigue siendo
  verdadero (`checked = valid = 0`);
- firma alterada (o cadena reescrita con los hashes recalculados): `invalid`, `ok = false` y, si la
  cadena estaba sana, `broken_at_seq = first_invalid_signature_seq`; una firma ilegible (basura)
  cuenta como inválida, nunca como excepción;
- firma borrada con el trigger apagado: la regla anti-retroceso (la verificación anterior dio por
  válida una firma más alta) lo detecta y marca `invalid` con `first_invalid_signature_seq` = la
  firma que faltaba; borrar todas también;
- nada de lo anterior llama al proveedor: ni `Local` (espía de métodos) ni Transit (`FakeTransit`
  sin llamadas), ni con el custodio sellado (M-1 cerrada, D81); la verificación completa con el
  custodio sellado sigue en `ok`;
- llaves `decrypt_only` y `retired` verifican por su `public_key`; con 365 firmas (mitad `local`,
  mitad `openbao`) se verifican las 365;
- una `public_key` alterada en la fila hace inválidas sus firmas;
- `payload_version` elige el constructor del payload (`audit_sign.PAYLOAD_BUILDERS`).
Todo dentro del savepoint de la prueba (`firmador`: cadena vacía, bus listo y fila `sign` `local`).
"""

from __future__ import annotations

import base64
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit_sign
from app.core.audit_verify import (
    AuditVerification,
    SignatureVerdict,
    run_verification,
    verify_signatures,
)
from app.core.context import SYSTEM_USER_ID
from app.core.crypto.keyring import Keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.provider import configure_provider
from tests.audit.conftest import CadenaDePrueba
from tests.crypto.conftest import (  # noqa: F401  (fixtures del proveedor Transit falso)
    fake_transit,
    fila_sign,
    openbao_fake,
    token_file,
)
from tests.factories.fake_provider import ProveedorControlable, inyectar_proveedor
from tests.factories.signatures import (
    borrar_firma,
    cadena_con_firmas,
    cambiar_llave,
    copiar_firma,
    escribir_firma,
    firma_de_llave_retirada,
    firmar_hasta,
    firmas,
    keyring_nuevo,
    payload_de,
)

pytestmark = pytest.mark.usefixtures("firmador")

SEGMENTOS = (3, 4, 5)  # tres firmas: through_seq 3, 7 y 12
THROUGH = (3, 7, 12)
LLAMADAS_AL_PROVEEDOR = ("sign", "verify", "unwrap", "wrap", "rewrap", "rotate", "key_info")


class EspiaDelProveedorLocal:
    """Anota cada método asíncrono de `LocalFileProvider` que alguien llame."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.llamadas: list[str] = []
        for nombre in (*LLAMADAS_AL_PROVEEDOR, "sign_public_key", "status"):
            original = getattr(LocalFileProvider, nombre)
            monkeypatch.setattr(LocalFileProvider, nombre, self._envolver(nombre, original))

    def _envolver(self, nombre: str, original: Any) -> Any:
        async def envuelto(proveedor: Any, *args: Any, **kwargs: Any) -> Any:
            self.llamadas.append(nombre)
            return await original(proveedor, *args, **kwargs)

        return envuelto


@pytest.fixture
def espia(monkeypatch: pytest.MonkeyPatch) -> EspiaDelProveedorLocal:
    """El espía se instala DESPUÉS de firmar: cada prueba lo pide al terminar de armar la cadena."""
    return EspiaDelProveedorLocal(monkeypatch)


@pytest.fixture
def proveedor_del_proceso() -> Iterator[None]:
    yield
    configure_provider(None)


async def _verificar(session: AsyncSession) -> Any:
    return await run_verification(session, source="cli", by=SYSTEM_USER_ID)


async def _ultima_fila(session: AsyncSession) -> AuditVerification:
    fila = await session.scalar(
        select(AuditVerification).order_by(
            AuditVerification.finished_at.desc(), AuditVerification.created_at.desc()
        )
    )
    assert fila is not None
    return fila


# Cadena sana -------------------------------------------------------------------------------------


async def test_cadena_sana_con_tres_firmas_da_ok_checked_3_valid_3(
    session: AsyncSession, espia: EspiaDelProveedorLocal
) -> None:
    await cadena_con_firmas(session, SEGMENTOS)
    espia.llamadas.clear()

    vista = await _verificar(session)

    assert vista.ok is True and vista.broken_at_seq is None
    assert (vista.signatures_checked, vista.signatures_valid) == (3, 3)
    assert vista.first_invalid_signature_seq is None
    assert vista.last_valid_signature_seq == THROUGH[-1]
    assert vista.last_valid_signature_algorithm == "Ed25519"
    ultima = (await firmas(session))[-1]
    assert vista.last_valid_signature_at == ultima["signed_at"]
    assert espia.llamadas == []  # verificar firmas nunca llama al proveedor (D62, D81)


async def test_verify_signatures_directo_devuelve_el_veredicto_ok(session: AsyncSession) -> None:
    await cadena_con_firmas(session, SEGMENTOS)

    veredicto = await verify_signatures(session, through_seq=THROUGH[-1])

    assert isinstance(veredicto, SignatureVerdict)
    assert veredicto.state == "ok"
    assert (veredicto.checked, veredicto.valid) == (3, 3)
    assert veredicto.first_invalid_seq is None
    assert veredicto.last_valid_seq == THROUGH[-1]
    assert veredicto.last_valid_algorithm == "Ed25519"
    assert veredicto.last_valid_at is not None


async def test_el_tope_through_seq_deja_fuera_las_firmas_posteriores(
    session: AsyncSession,
) -> None:
    await cadena_con_firmas(session, SEGMENTOS)

    veredicto = await verify_signatures(session, through_seq=8)

    assert (veredicto.state, veredicto.checked, veredicto.valid) == ("ok", 2, 2)
    assert veredicto.last_valid_seq == 7


async def test_la_fila_guardada_lleva_las_seis_columnas(session: AsyncSession) -> None:
    await cadena_con_firmas(session, SEGMENTOS)
    vista = await _verificar(session)
    await session.flush()

    fila = await _ultima_fila(session)

    assert fila.id == vista.id
    assert (fila.signatures_checked, fila.signatures_valid) == (3, 3)
    assert fila.first_invalid_signature_seq is None
    assert fila.last_valid_signature_seq == THROUGH[-1]
    assert fila.last_valid_signature_algorithm == "Ed25519"
    assert fila.last_valid_signature_at is not None


async def test_sin_firmas_el_estado_es_none_y_la_cadena_sigue_ok(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    await audit_chain_factory.make(5)

    vista = await _verificar(session)
    veredicto = await verify_signatures(session, through_seq=5)

    assert vista.ok is True
    assert (vista.signatures_checked, vista.signatures_valid) == (0, 0)
    assert vista.first_invalid_signature_seq is None and vista.last_valid_signature_seq is None
    assert (veredicto.state, veredicto.checked, veredicto.valid) == ("none", 0, 0)
    assert veredicto.last_valid_seq is None and veredicto.last_valid_at is None


# Firmas alteradas --------------------------------------------------------------------------------


async def test_cadena_reescrita_con_hashes_recalculados_deja_la_firma_invalida(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    await cadena_con_firmas(session, SEGMENTOS)
    await audit_chain_factory.tamper(5, "after", {"n": 5, "alterado": True}, rehash=True)

    vista = await _verificar(session)

    # La cadena es internamente válida, pero las firmas 7 y 12 cubren el tramo reescrito.
    assert vista.ok is False
    assert (vista.signatures_checked, vista.signatures_valid) == (3, 1)
    assert vista.first_invalid_signature_seq == 7
    assert vista.broken_at_seq == 7  # cadena sana: manda la primera firma inválida
    assert vista.last_valid_signature_seq == 3


async def test_firma_alterada_en_su_fila_da_invalid_y_broken_at_igual_a_first_invalid(
    session: AsyncSession,
) -> None:
    await cadena_con_firmas(session, SEGMENTOS)
    await copiar_firma(session, de_seq=3, a_seq=7)  # base64 válido, firma equivocada

    vista = await _verificar(session)
    veredicto = await verify_signatures(session, through_seq=12)

    assert vista.ok is False
    assert (vista.signatures_checked, vista.signatures_valid) == (3, 2)
    assert vista.first_invalid_signature_seq == 7 and vista.broken_at_seq == 7
    assert (veredicto.state, veredicto.first_invalid_seq) == ("invalid", 7)


async def test_firma_ilegible_cuenta_como_invalida_y_no_lanza(session: AsyncSession) -> None:
    await cadena_con_firmas(session, SEGMENTOS)
    await escribir_firma(session, 7, "esto-no-es-una-firma")

    veredicto = await verify_signatures(session, through_seq=12)

    assert (veredicto.state, veredicto.checked, veredicto.valid) == ("invalid", 3, 2)
    assert veredicto.first_invalid_seq == 7


async def test_si_la_cadena_esta_rota_manda_su_broken_at_seq(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    await cadena_con_firmas(session, SEGMENTOS)
    await audit_chain_factory.tamper(2, "after", {"n": 2, "alterado": True})  # sin recalcular

    vista = await _verificar(session)

    assert vista.ok is False
    assert vista.broken_at_seq == 2


# Anti-retroceso (firma borrada) ------------------------------------------------------------------


async def test_firma_borrada_con_el_trigger_apagado_la_detecta_el_anti_retroceso_sin_proveedor(
    session: AsyncSession, espia: EspiaDelProveedorLocal
) -> None:
    await cadena_con_firmas(session, SEGMENTOS)
    primera = await _verificar(session)
    assert primera.ok is True and primera.last_valid_signature_seq == 12
    await borrar_firma(session, 12)
    espia.llamadas.clear()

    vista = await _verificar(session)

    assert vista.ok is False
    assert (vista.signatures_checked, vista.signatures_valid) == (2, 2)  # las que quedan valen
    assert vista.first_invalid_signature_seq == 12  # la firma que faltaba
    assert vista.broken_at_seq == 12
    assert espia.llamadas == []  # sin ninguna llamada al proveedor


async def test_firma_borrada_con_transit_no_hace_ninguna_llamada_a_transit(
    session: AsyncSession,
    fake_transit: Any,  # noqa: F811
    openbao_fake: Any,  # noqa: F811
    proveedor_local: LocalFileProvider,
) -> None:
    """La misma regla con la firma de `openbao`: el contador del `FakeTransit` no se mueve."""
    await _rotar_a_openbao(session, proveedor_local, openbao_fake)
    await cadena_con_firmas(session, SEGMENTOS)
    await _verificar(session)
    await borrar_firma(session, 12)
    llamadas = len(fake_transit.calls)

    vista = await _verificar(session)

    assert vista.ok is False and vista.first_invalid_signature_seq == 12
    assert len(fake_transit.calls) == llamadas
    assert fake_transit.llamadas("verify") == []


async def test_borrar_todas_las_firmas_tambien_se_detecta(session: AsyncSession) -> None:
    await cadena_con_firmas(session, (3, 4))
    assert (await _verificar(session)).ok is True
    for seq in (3, 7):
        await borrar_firma(session, seq)

    vista = await _verificar(session)

    assert vista.ok is False
    assert vista.signatures_checked == 0
    assert vista.first_invalid_signature_seq == 7  # la última que la verificación anterior dio


async def test_una_verificacion_previa_sobre_un_tramo_mayor_no_cuenta_como_retroceso(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    """El anti-retroceso se acota al tramo de esta corrida (`last_valid <= through_seq`)."""
    await cadena_con_firmas(session, SEGMENTOS)
    previa = await _verificar(session)
    assert previa.last_valid_signature_seq == 12
    veredicto = await verify_signatures(session, through_seq=8)
    from app.core.audit_verify import _with_anti_rollback

    resultado = await _with_anti_rollback(session, veredicto, 8)

    assert resultado.state == "ok" and resultado.first_invalid_seq is None


async def test_sin_verificacion_anterior_no_hay_retroceso_que_detectar(
    session: AsyncSession,
) -> None:
    await cadena_con_firmas(session, SEGMENTOS)
    await borrar_firma(session, 12)  # nadie había visto la firma 12

    vista = await _verificar(session)

    assert vista.ok is True
    assert (vista.signatures_checked, vista.signatures_valid) == (2, 2)


# Llaves en cualquier estado ----------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["decrypt_only", "retired"])
async def test_firma_de_llave_no_activa_verifica_por_su_public_key(
    session: AsyncSession,
    audit_chain_factory: CadenaDePrueba,
    proveedor_local: LocalFileProvider,
    estado: str,
) -> None:
    await audit_chain_factory.make(3)
    vieja = await firma_de_llave_retirada(session, proveedor_local, 3, estado=estado)
    await audit_chain_factory.make(3)
    await firmar_hasta(session, 6)  # con la versión 2, activa

    vista = await _verificar(session)

    llaves = {fila["key_id"] for fila in await firmas(session)}
    assert len(llaves) == 2 and vieja in llaves
    assert vista.ok is True
    assert (vista.signatures_checked, vista.signatures_valid) == (2, 2)
    assert vista.last_valid_signature_seq == 6


# Custodio sellado (M-1, D81) ---------------------------------------------------------------------


async def test_con_el_custodio_sellado_la_verificacion_completa_sigue_ok(
    session: AsyncSession,
    firmador: Keyring,
    proveedor_local: LocalFileProvider,
    monkeypatch: pytest.MonkeyPatch,
    proveedor_del_proceso: None,
) -> None:
    await cadena_con_firmas(session, SEGMENTOS)
    sellado = ProveedorControlable(proveedor_local)
    inyectar_proveedor(monkeypatch, sellado)
    await firmador.load_all(session, lambda _n: sellado)
    sellado.estado = "sealed"

    vista = await _verificar(session)

    assert vista.ok is True
    assert (vista.signatures_checked, vista.signatures_valid) == (3, 3)
    assert (sellado.status_calls, sellado.wrap_calls, sellado.unwrap_calls) == (0, 0, 0)


# 365 firmas, mitad local y mitad openbao ---------------------------------------------------------


async def _rotar_a_openbao(
    session: AsyncSession, proveedor_local: LocalFileProvider, openbao: Any
) -> None:
    """Pasa la firma activa a `openbao`: la versión 1 (`local`) queda `decrypt_only` y nace la 2."""
    activa = (await _llaves_sign(session))[0]
    await cambiar_llave(session, activa, state="decrypt_only")
    await fila_sign(session, openbao, version=2)
    await keyring_nuevo(session, _resolver(proveedor_local, openbao))


def _resolver(proveedor_local: LocalFileProvider, openbao: Any) -> Any:
    return lambda nombre: openbao if nombre == "openbao" else proveedor_local


async def _llaves_sign(session: AsyncSession) -> list[Any]:
    from app.core.crypto.models import CryptoKey

    filas = await session.scalars(
        select(CryptoKey.id).where(CryptoKey.purpose == "sign").order_by(CryptoKey.version)
    )
    return list(filas)


async def test_365_firmas_mitad_local_mitad_openbao_se_verifican_todas_sin_transit(
    session: AsyncSession,
    fake_transit: Any,  # noqa: F811
    openbao_fake: Any,  # noqa: F811
    proveedor_local: LocalFileProvider,
) -> None:
    await cadena_con_firmas(session, [1] * 183)  # firmadas con `local`
    await _rotar_a_openbao(session, proveedor_local, openbao_fake)
    await cadena_con_firmas(session, [1] * 182)  # firmadas con `openbao` (Transit falso)
    assert {f["algorithm"] for f in await firmas(session)} == {"Ed25519"}
    antes = len(fake_transit.calls)

    vista = await _verificar(session)

    assert vista.ok is True
    assert vista.signatures_checked == 365 and vista.signatures_valid == 365
    assert vista.last_valid_signature_seq == 365
    assert len(fake_transit.calls) == antes
    assert fake_transit.llamadas("verify") == []


# public_key alterada -----------------------------------------------------------------------------


async def test_una_public_key_alterada_en_la_fila_hace_invalidas_sus_firmas(
    session: AsyncSession, proveedor_local: LocalFileProvider
) -> None:
    await cadena_con_firmas(session, (3, 4))
    llave = (await firmas(session))[0]["key_id"]
    otra = base64.b64encode(bytes(range(1, 33))).decode("ascii")
    await cambiar_llave(session, llave, public_key=otra)
    await keyring_nuevo(session, lambda _n: proveedor_local)  # como tras reiniciar el api

    vista = await _verificar(session)

    assert vista.ok is False
    assert (vista.signatures_checked, vista.signatures_valid) == (2, 0)
    assert vista.first_invalid_signature_seq == 3
    assert vista.last_valid_signature_seq is None


# payload_version ---------------------------------------------------------------------------------


async def test_payload_version_elige_el_constructor_del_payload(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    await audit_chain_factory.make(3)
    await firmar_hasta(session, 3, version=2)  # firmó `apex-audit-sig-v2\n3\n<hash>`
    monkeypatch.setitem(audit_sign.PAYLOAD_BUILDERS, 2, lambda seq, h: payload_de(seq, h, 2))

    veredicto = await verify_signatures(session, through_seq=3)

    assert (veredicto.state, veredicto.checked, veredicto.valid) == ("ok", 1, 1)


async def test_el_constructor_registrado_manda_sobre_el_payload_de_la_fila(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    await audit_chain_factory.make(3)
    await firmar_hasta(session, 3, version=2)
    monkeypatch.setitem(audit_sign.PAYLOAD_BUILDERS, 2, lambda seq, h: payload_de(seq, h, 2) + b"!")

    veredicto = await verify_signatures(session, through_seq=3)

    assert (veredicto.state, veredicto.valid, veredicto.first_invalid_seq) == ("invalid", 0, 3)


async def test_una_version_sin_constructor_es_invalida_y_no_lanza(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    await audit_chain_factory.make(3)
    await firmar_hasta(session, 3, version=2)  # nadie registró el constructor v2

    veredicto = await verify_signatures(session, through_seq=3)

    assert (veredicto.state, veredicto.valid, veredicto.first_invalid_seq) == ("invalid", 0, 3)


async def test_la_version_1_sigue_verificando_con_su_constructor(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    await audit_chain_factory.make(3)
    await firmar_hasta(session, 3, version=1)

    veredicto = await verify_signatures(session, through_seq=3)

    assert (veredicto.state, veredicto.valid) == ("ok", 1)
    assert 1 in audit_sign.PAYLOAD_BUILDERS
