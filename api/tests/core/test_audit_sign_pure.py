"""Funciones puras de `core/audit_sign.py` (S6-A1, US-140; S6-D4, S6-D34; ADR-006).

- `signature_payload`: prefijo, `through_seq` y `chain_hash` en ASCII separados por saltos de línea;
  cualquier otra entrada lanza `CanonicalError` (de `core.audit`).
- `needs_signature(last_seq, last_signed_seq)`: hay filas posteriores a la última firmada.
- `is_signature_late(...)`: «Firma atrasada» a las 48 h con filas sin firmar (S6-D40).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.audit import CanonicalError
from app.core.audit_sign import is_signature_late, needs_signature, signature_payload

H = "0123456789abcdef" * 4
AHORA = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def horas(n: float) -> datetime:
    """Un instante `n` horas antes de `AHORA`."""
    return AHORA - timedelta(hours=n)


# signature_payload ------------------------------------------------------------------------------


def test_payload_byte_a_byte() -> None:
    assert signature_payload(1, H) == b"apex-audit-sig-v1\n1\n" + H.encode("ascii")
    assert signature_payload(1, H, version=1) == signature_payload(1, H)


def test_payload_decimal_sin_signo_ni_ceros_a_la_izquierda() -> None:
    assert signature_payload(10, H).split(b"\n")[1] == b"10"
    assert signature_payload(9_007_199_254_740_993, H).split(b"\n")[1] == b"9007199254740993"


def test_payload_es_ascii_y_tiene_exactamente_tres_campos() -> None:
    payload = signature_payload(42, H)
    assert payload.isascii() and payload.count(b"\n") == 2
    assert not payload.endswith(b"\n")


def test_payload_cambia_con_el_seq_y_con_el_hash() -> None:
    assert (
        len({signature_payload(1, H), signature_payload(2, H), signature_payload(1, "a" * 64)}) == 3
    )


@pytest.mark.parametrize("seq", [0, -1, -9999])
def test_payload_rechaza_through_seq_menor_que_1(seq: int) -> None:
    with pytest.raises(CanonicalError):
        signature_payload(seq, H)


@pytest.mark.parametrize(
    "hash_malo",
    [
        "a" * 63,
        "a" * 65,
        "",
        "A" * 64,
        "0123456789ABCDEF" * 4,
        "g" * 64,
        " " + "a" * 63,
        "a" * 63 + "\n",
    ],
    ids=["63", "65", "vacio", "mayusculas", "mayusculas-mixtas", "no-hex", "espacio", "salto"],
)
def test_payload_rechaza_hash_que_no_son_64_hex_en_minuscula(hash_malo: str) -> None:
    with pytest.raises(CanonicalError):
        signature_payload(1, hash_malo)


@pytest.mark.parametrize("version", [0, -1, 99])
def test_payload_rechaza_versiones_desconocidas(version: int) -> None:
    with pytest.raises(CanonicalError):
        signature_payload(1, H, version=version)


@pytest.mark.parametrize("seq", [True, 1.0, "1", None], ids=["bool", "float", "str", "none"])
def test_payload_rechaza_through_seq_que_no_es_entero(seq: object) -> None:
    with pytest.raises(CanonicalError):
        signature_payload(seq, H)  # type: ignore[arg-type]


# needs_signature --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("last_seq", "last_signed_seq", "esperado"),
    [
        (0, 0, False),  # cadena vacía
        (5, 0, True),  # nunca firmada
        (5, 5, False),  # al día
        (8, 5, True),  # filas nuevas
        (5, 8, False),  # retroceso: no hay nada que firmar (lo detecta la verificación)
    ],
)
def test_needs_signature(last_seq: int, last_signed_seq: int, esperado: bool) -> None:
    assert needs_signature(last_seq, last_signed_seq) is esperado


# is_signature_late ------------------------------------------------------------------------------


def test_sin_filas_nuevas_no_esta_atrasada_aunque_la_firma_sea_vieja() -> None:
    assert is_signature_late(horas(500), 5, 5, None, AHORA) is False


def test_gimnasio_sin_actividad_no_esta_atrasado() -> None:
    assert is_signature_late(None, 0, 0, None, AHORA) is False
    assert is_signature_late(horas(2000), 7, 7, None, AHORA) is False


def test_nunca_firmada_con_filas_de_hace_49_h_esta_atrasada() -> None:
    assert is_signature_late(None, 5, 0, horas(49), AHORA) is True


def test_nunca_firmada_con_filas_de_hace_47_h_no_esta_atrasada() -> None:
    assert is_signature_late(None, 5, 0, horas(47), AHORA) is False


def test_firmada_con_filas_sin_firmar_de_hace_49_h_esta_atrasada() -> None:
    assert is_signature_late(horas(100), 9, 5, horas(49), AHORA) is True


def test_firmada_con_filas_sin_firmar_de_hace_47_h_no_esta_atrasada() -> None:
    assert is_signature_late(horas(100), 9, 5, horas(47), AHORA) is False


def test_el_umbral_exacto_de_48_h_no_cuenta_como_atrasado() -> None:
    """«A las 48 h» se alerta pasadas las 48 h (estrictamente mayor)."""
    assert is_signature_late(None, 5, 0, horas(48), AHORA) is False
    assert is_signature_late(None, 5, 0, horas(48) - timedelta(seconds=1), AHORA) is True


def test_el_umbral_es_configurable() -> None:
    assert is_signature_late(None, 5, 0, horas(13), AHORA, threshold_h=12) is True
    assert is_signature_late(None, 5, 0, horas(11), AHORA, threshold_h=12) is False


def test_filas_sin_firmar_sin_fecha_de_la_primera_no_se_pueden_dar_por_atrasadas() -> None:
    """Sin `first_unsigned_at` (dato ausente) no hay edad que medir: no se alerta."""
    assert is_signature_late(horas(100), 9, 5, None, AHORA) is False
