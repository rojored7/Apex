"""Funciones puras de la verificación de firmas (S6-A3, US-142; S6-D10, S6-D62). Rojo A3.

`signature_state(checked, valid, first_invalid_seq)`: `none` sin firmas verificadas, `invalid` si
alguna no verifica (hay `first_invalid_seq` o `valid < checked`), `ok` si todas verifican. No existe
el estado `unavailable` (D62/D81: la verificación nunca llama al proveedor).

`anti_rollback(prev_last_valid_seq, max_signed_seq, signatures_count)`: `True` si hubo RETROCESO,
es decir, la verificación anterior dio por válida una firma hasta `prev_last_valid_seq` y ahora el
mayor `through_seq` firmado es menor (o ya no hay firmas). Sin verificación anterior con firmas
(`prev_last_valid_seq` nulo) no hay con qué comparar: `False`. Pura: sin base ni red.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from typing import get_args

import pytest

from app.core.audit_verify import (
    SignatureState,
    SignatureVerdict,
    anti_rollback,
    signature_state,
)

# signature_state ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("checked", "valid", "first_invalid", "esperado"),
    [
        (0, 0, None, "none"),
        (1, 1, None, "ok"),
        (3, 3, None, "ok"),
        (365, 365, None, "ok"),
        (3, 2, 7, "invalid"),
        (1, 0, 5, "invalid"),
        (3, 0, 3, "invalid"),
        (3, 2, None, "invalid"),  # falta una válida aunque no se haya señalado cuál
        (3, 3, 12, "invalid"),  # una señal explícita de invalidez manda
    ],
    ids=[
        "sin_firmas",
        "una_valida",
        "tres_validas",
        "trescientas_sesenta_y_cinco",
        "una_invalida_de_tres",
        "la_unica_invalida",
        "ninguna_valida",
        "faltan_validas_sin_seq",
        "con_seq_invalido_explicito",
    ],
)
def test_signature_state_tabla(
    checked: int, valid: int, first_invalid: int | None, esperado: str
) -> None:
    assert signature_state(checked, valid, first_invalid) == esperado


def test_signature_state_solo_conoce_none_ok_e_invalid() -> None:
    assert set(get_args(SignatureState)) == {"none", "ok", "invalid"}


def test_signature_state_es_pura_y_repetible() -> None:
    assert signature_state(3, 3, None) == signature_state(3, 3, None) == "ok"


# anti_rollback -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("previo", "maximo", "cuenta", "retrocede"),
    [
        (None, None, 0, False),  # primera verificación, sin firmas
        (None, 50, 3, False),  # primera verificación con firmas
        (None, None, 5, False),  # sin ancla de firmas no hay con qué comparar
        (50, 50, 3, False),  # igual
        (50, 80, 4, False),  # avanzó
        (50, 49, 2, True),  # retrocedió por una
        (50, 10, 1, True),  # retrocedió mucho
        (50, None, 0, True),  # ya no hay firmas
        (50, None, 3, True),  # recuento sin máximo es inconsistente: no cuadra
        (50, 80, 0, True),  # recuento cero con máximo: inconsistente
    ],
    ids=[
        "primera_sin_firmas",
        "primera_con_firmas",
        "sin_ancla",
        "igual",
        "avanzo",
        "retrocedio_una",
        "retrocedio_mucho",
        "todas_borradas",
        "maximo_nulo_con_recuento",
        "recuento_cero_con_maximo",
    ],
)
def test_anti_rollback_tabla(
    previo: int | None, maximo: int | None, cuenta: int, retrocede: bool
) -> None:
    assert anti_rollback(previo, maximo, cuenta) is retrocede


# SignatureVerdict --------------------------------------------------------------------------------


def test_signature_verdict_tiene_los_siete_campos_del_plan_y_es_inmutable() -> None:
    assert [f.name for f in fields(SignatureVerdict)] == [
        "state",
        "checked",
        "valid",
        "first_invalid_seq",
        "last_valid_seq",
        "last_valid_at",
        "last_valid_algorithm",
    ]
    veredicto = SignatureVerdict(
        "ok", 3, 3, None, 12, datetime(2026, 11, 11, 12, 0, tzinfo=UTC), "Ed25519"
    )
    with pytest.raises(FrozenInstanceError):
        veredicto.state = "invalid"  # type: ignore[misc]
