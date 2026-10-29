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
