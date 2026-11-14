"""`format_verify_message(result) -> (texto, código)` (S4A-B3, US-105; S4A-D15, S4A-D43).

Contrato fijado por el Rojo:
- íntegra con ancla: empieza por `Cadena íntegra`, nombra `rows_checked` y `through_seq`; código 0;
- íntegra sin ancla (primera vez): además dice `sin verificación anterior que comparar`; código 0;
- rota en la cadena: empieza por `Cadena rota en el registro seq <N>`; código 1;
- rota por el ancla (`anchor_broken`): lo mismo y además `no coincide con la verificación
  anterior`; código 1.
El texto nunca lleva `before`, `after`, hashes ni ids (sale en la CLI y en los logs).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from app.core.audit_verify import VerificationView, format_verify_message

INICIO = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
FIN = datetime(2026, 10, 21, 15, 0, 3, tzinfo=UTC)
ID = UUID("6d1f6a52-5a4e-4b55-9b0a-1f3c2b8d9e01")
POR = UUID("00000000-0000-0000-0000-000000000001")
HASH = "ab" * 32

INTEGRA = VerificationView(
    id=ID,
    ok=True,
    rows_checked=4504,
    through_seq=4504,
    through_hash=HASH,
    broken_at_seq=None,
    started_at=INICIO,
    finished_at=FIN,
    triggered_by=POR,
    source="cli",
    anchor_seq=4400,
)


def _sin_secretos(texto: str) -> None:
    for prohibido in (HASH, str(ID), str(POR), "before", "after"):
        assert prohibido not in texto, prohibido


def test_integra_con_ancla() -> None:
    texto, codigo = format_verify_message(INTEGRA)
    assert codigo == 0
    assert texto.startswith("Cadena íntegra")
    assert "4504" in texto or "4.504" in texto
    assert "sin verificación anterior" not in texto
    _sin_secretos(texto)


def test_integra_por_primera_vez_lo_dice() -> None:
    texto, codigo = format_verify_message(replace(INTEGRA, anchor_seq=None))
    assert codigo == 0
    assert texto.startswith("Cadena íntegra")
    assert "sin verificación anterior que comparar" in texto
    _sin_secretos(texto)


def test_rota_en_el_seq_42() -> None:
    rota = replace(INTEGRA, ok=False, rows_checked=42, broken_at_seq=42)
    texto, codigo = format_verify_message(rota)
    assert codigo == 1
    assert texto.startswith("Cadena rota en el registro seq 42")
    assert "no coincide con la verificación anterior" not in texto
    _sin_secretos(texto)


def test_rota_por_el_ancla() -> None:
    rota = replace(
        INTEGRA, ok=False, rows_checked=48, broken_at_seq=49, anchor_seq=50, anchor_broken=True
    )
    texto, codigo = format_verify_message(rota)
    assert codigo == 1
    assert texto.startswith("Cadena rota en el registro seq 49")
    assert "no coincide con la verificación anterior" in texto
    _sin_secretos(texto)


# Firmas (S6-A3, US-142; S6-D10) -------------------------------------------------------------------
# Contrato fijado por el Rojo:
# - sin datos de firmas (verificación vieja, campos nulos) el texto no menciona firmas;
# - con `signatures_checked = 0` dice `Sin firmas que verificar` y el código sigue siendo 0;
# - todas válidas: `Firmas: N de N válidas` y el último `seq` válido; código 0;
# - alguna inválida: `Firma inválida` con el `seq` de `first_invalid_signature_seq`, `V de C
#   válidas`, código 1 también con la cadena sana (`broken_at_seq` lo fija el servicio);
# - nunca lleva el algoritmo ni ids, hashes o el blob `apx1.` de la firma.

FIRMA_EN = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
CON_FIRMAS = replace(
    INTEGRA,
    signatures_checked=3,
    signatures_valid=3,
    last_valid_signature_seq=4504,
    last_valid_signature_at=FIRMA_EN,
    last_valid_signature_algorithm="Ed25519",
)


def _sin_blobs(texto: str) -> None:
    _sin_secretos(texto)
    assert "apx1." not in texto and "Ed25519" not in texto


def test_sin_datos_de_firmas_el_texto_no_las_menciona() -> None:
    texto, codigo = format_verify_message(INTEGRA)
    assert codigo == 0
    assert "irma" not in texto  # ni «firma» ni «Firmas»


def test_sin_firmas_que_verificar_lo_dice_y_sale_0() -> None:
    texto, codigo = format_verify_message(
        replace(INTEGRA, signatures_checked=0, signatures_valid=0)
    )
    assert codigo == 0
    assert texto.startswith("Cadena íntegra")
    assert "Sin firmas que verificar" in texto
    _sin_blobs(texto)


def test_firmas_validas_dicen_cuantas_y_hasta_donde() -> None:
    texto, codigo = format_verify_message(CON_FIRMAS)
    assert codigo == 0
    assert texto.startswith("Cadena íntegra")
    assert "Firmas: 3 de 3 válidas" in texto
    assert "4504" in texto
    _sin_blobs(texto)


def test_firma_invalida_con_la_cadena_sana_sale_1_y_dice_cual() -> None:
    invalida = replace(
        CON_FIRMAS,
        ok=False,
        broken_at_seq=3000,
        signatures_valid=1,
        first_invalid_signature_seq=3000,
        last_valid_signature_seq=1200,
    )
    texto, codigo = format_verify_message(invalida)
    assert codigo == 1
    assert "Firma inválida" in texto and "3000" in texto
    assert "1 de 3 válidas" in texto
    _sin_blobs(texto)


def test_cadena_rota_y_firma_invalida_conserva_el_aviso_de_la_cadena() -> None:
    ambas = replace(
        CON_FIRMAS,
        ok=False,
        rows_checked=42,
        broken_at_seq=42,
        signatures_valid=2,
        first_invalid_signature_seq=100,
    )
    texto, codigo = format_verify_message(ambas)
    assert codigo == 1
    assert "Cadena rota en el registro seq 42" in texto
    assert "Firma inválida" in texto and "100" in texto
    _sin_blobs(texto)


def test_las_verificaciones_rotas_sin_firmas_conservan_el_texto_de_antes() -> None:
    rota = replace(INTEGRA, ok=False, rows_checked=42, broken_at_seq=42)
    texto, codigo = format_verify_message(rota)
    assert (texto, codigo) == ("Cadena rota en el registro seq 42.", 1)


def test_cadena_rota_en_el_mismo_seq_de_la_primera_firma_invalida_sigue_diciendo_cadena_rota() -> (
    None
):
    """V11: `broken_at_seq` fusiona cadena y firma; con `chain_broken` el aviso de la cadena no se
    oculta aunque coincida con `first_invalid_signature_seq`."""
    ambas = replace(
        CON_FIRMAS,
        ok=False,
        rows_checked=100,
        broken_at_seq=100,
        chain_broken=True,
        signatures_valid=2,
        first_invalid_signature_seq=100,
    )
    texto, codigo = format_verify_message(ambas)
    assert codigo == 1
    assert "Cadena rota en el registro seq 100" in texto
    assert "Firma inválida" in texto
