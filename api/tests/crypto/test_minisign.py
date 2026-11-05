"""Verificación de firmas `minisign` en Python (S5-B13; S5-D72, H-1).

`core/crypto/minisign.py`: `parse_pubkey(texto) -> MinisignKey` (la línea `RW...` o el `.pub`
completo; `ValueError` si no es una llave) y `verify_minisign(llave, datos, firma) -> bool`:
Ed25519 sobre BLAKE2b-512 (algoritmo `ED`), más la firma del comentario de confianza con la misma
llave. Nunca lanza ante una firma mala; devuelve `False`:
- un byte alterado en los datos; la firma alterada; el comentario de confianza alterado;
- el algoritmo `Ed` heredado (dato crudo), aunque la firma sea válida para `minisign -V`;
- una llave de otro id (o el id de la firma cambiado) y una firma malformada o truncada.
Los vectores son reales (`_minisign_vectors.py`, generados con el binario de `apex-backup:local`);
el firmante de `tests/factories/minisign_signer.py` se valida contra el mismo formato.
"""

from __future__ import annotations

import base64

import pytest

from app.core.crypto.minisign import MinisignKey, parse_pubkey, verify_minisign
from tests.crypto import _minisign_vectors as v
from tests.factories.minisign_signer import (
    corrupt_signature_line,
    make_signing_key,
    sign_bytes,
)


def _llave_a() -> MinisignKey:
    return parse_pubkey(v.PUBKEY_A_LINE)


def _cambiar_linea(firma: str, indice: int, nueva: str) -> str:
    lineas = firma.split("\n")
    lineas[indice] = nueva
    return "\n".join(lineas)


def _alterar_base64(firma: str, indice: int, posicion: int, mascara: int) -> str:
    lineas = firma.split("\n")
    crudo = bytearray(base64.b64decode(lineas[indice]))
    crudo[posicion] ^= mascara
    return _cambiar_linea(firma, indice, base64.b64encode(bytes(crudo)).decode("ascii"))


# parse_pubkey -------------------------------------------------------------------------------


def test_parse_pubkey_de_la_linea_da_el_id_y_los_32_bytes() -> None:
    llave = _llave_a()

    assert llave.key_id == bytes.fromhex("2905accbc3c17979")
    assert len(llave.public) == 32


def test_parse_pubkey_del_archivo_completo_equivale_a_la_linea() -> None:
    assert parse_pubkey(v.PUBKEY_A_FILE) == _llave_a()


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "RW",
        "no es una llave",
        v.PUBKEY_A_LINE[:-4],
        v.PUBKEY_A_LINE + "AAAA",
        "RUQpBazLw8F5eWSQusHr6xq+6CZyQvhgYoCZPlnyI6w5jndJtE0E+hA0",
    ],
)
def test_parse_pubkey_rechaza_lo_que_no_es_una_llave_minisign(texto: str) -> None:
    with pytest.raises(ValueError):
        parse_pubkey(texto)


# Vectores reales -----------------------------------------------------------------------------


def test_la_firma_real_ed_de_minisign_es_valida() -> None:
    assert verify_minisign(_llave_a(), v.DATA, v.SIG_ED) is True


def test_un_byte_alterado_en_los_datos_da_falso() -> None:
    alterado = bytes([v.DATA[0] ^ 0x01]) + v.DATA[1:]

    assert verify_minisign(_llave_a(), alterado, v.SIG_ED) is False


def test_datos_con_un_byte_de_mas_o_de_menos_dan_falso() -> None:
    llave = _llave_a()

    assert verify_minisign(llave, v.DATA + b"\n", v.SIG_ED) is False
    assert verify_minisign(llave, v.DATA[:-1], v.SIG_ED) is False
    assert verify_minisign(llave, b"", v.SIG_ED) is False


def test_la_firma_alterada_da_falso() -> None:
    assert verify_minisign(_llave_a(), v.DATA, corrupt_signature_line(v.SIG_ED)) is False


def test_la_firma_global_alterada_da_falso() -> None:
    assert verify_minisign(_llave_a(), v.DATA, _alterar_base64(v.SIG_ED, 3, 5, 0x01)) is False


def test_el_comentario_de_confianza_alterado_da_falso() -> None:
    mala = _cambiar_linea(v.SIG_ED, 2, "trusted comment: timestamp:1700000001 file:data.json")

    assert verify_minisign(_llave_a(), v.DATA, mala) is False


def test_el_comentario_de_no_confianza_no_esta_firmado_y_cambiarlo_no_invalida() -> None:
    otra = _cambiar_linea(v.SIG_ED, 0, "untrusted comment: otra cosa")

    assert verify_minisign(_llave_a(), v.DATA, otra) is True


def test_el_algoritmo_ed_heredado_da_falso_aunque_la_firma_sea_valida() -> None:
    assert verify_minisign(_llave_a(), v.DATA, v.SIG_LEGACY) is False


def test_una_llave_de_otro_id_da_falso() -> None:
    assert verify_minisign(parse_pubkey(v.PUBKEY_B_LINE), v.DATA, v.SIG_ED) is False


def test_el_id_de_la_firma_cambiado_da_falso() -> None:
    mala = _alterar_base64(v.SIG_ED, 1, 2, 0xFF)  # primer byte del id (tras los 2 del algoritmo)

    assert verify_minisign(_llave_a(), v.DATA, mala) is False


@pytest.mark.parametrize(
    "firma",
    [
        "",
        "basura",
        "untrusted comment: x\n",
        "untrusted comment: x\nno-es-base64!!\ntrusted comment: y\nAAAA\n",
        "untrusted comment: x\nQUJD\ntrusted comment: y\nQUJD\n",
        v.SIG_ED.split("trusted comment:")[0],
        v.SIG_ED.rsplit("\n", 2)[0] + "\n",
        v.SIG_ED.replace("trusted comment:", "comment:"),
    ],
)
def test_una_firma_malformada_o_truncada_da_falso_sin_lanzar(firma: str) -> None:
    assert verify_minisign(_llave_a(), v.DATA, firma) is False


# El firmante de prueba produce el mismo formato -----------------------------------------------


def test_el_firmante_de_prueba_firma_en_el_formato_real() -> None:
    llave = make_signing_key(7)
    firma = sign_bytes(llave, b"manifiesto\n", trusted_comment="file:latest.json")

    assert verify_minisign(parse_pubkey(llave.pubkey), b"manifiesto\n", firma) is True
    assert verify_minisign(parse_pubkey(llave.pubkey_file), b"manifiesto\n", firma) is True
    assert verify_minisign(parse_pubkey(llave.pubkey), b"manifiesto!\n", firma) is False


def test_el_firmante_de_prueba_en_modo_heredado_se_rechaza() -> None:
    llave = make_signing_key(7)
    firma = sign_bytes(llave, b"x\n", legacy=True)

    assert verify_minisign(parse_pubkey(llave.pubkey), b"x\n", firma) is False


def test_dos_llaves_de_prueba_no_se_verifican_entre_si() -> None:
    uno, dos = make_signing_key(7), make_signing_key(8)
    firma = sign_bytes(uno, b"x\n")

    assert verify_minisign(parse_pubkey(dos.pubkey), b"x\n", firma) is False


# Forma estricta de la firma (S5-D177 a D178, revisión de seguridad B13: LOW) --------------------


@pytest.mark.parametrize(
    "firma",
    [
        v.SIG_ED.replace("\n", "\r\n"),
        v.SIG_ED + "otra linea\n",
        v.SIG_ED + "\n\n",
        v.SIG_ED.rstrip("\n") + "\r\n",
        "\n" + v.SIG_ED,
    ],
)
def test_la_firma_con_lineas_de_mas_o_con_retorno_de_carro_da_falso(firma: str) -> None:
    assert verify_minisign(_llave_a(), v.DATA, firma) is False


def test_la_firma_sin_el_salto_de_linea_final_sigue_siendo_valida() -> None:
    assert verify_minisign(_llave_a(), v.DATA, v.SIG_ED.rstrip("\n")) is True
