"""`validation_field` convierte el `loc` de Pydantic en una ruta legible (US-017, T2 y T6)."""

from __future__ import annotations

import pytest

from app.core.errors import validation_field


@pytest.mark.parametrize(
    ("loc", "esperado"),
    [
        (("body", "first_payment", "amount_cop"), "first_payment.amount_cop"),
        (("query", "limit"), "limit"),
        (("path", "id"), "id"),
        (("header", "x-device-token"), "x-device-token"),
        (("body", "items", 0, "amount_cop"), "items[0].amount_cop"),
        (("body",), None),
    ],
)
def test_validation_field(loc: tuple[object, ...], esperado: str | None) -> None:
    assert validation_field([{"loc": loc, "msg": "x", "type": "t"}]) == esperado


def test_lista_vacia_da_none() -> None:
    assert validation_field([]) is None


def test_toma_el_primer_error() -> None:
    errores = [
        {"loc": ("body", "a"), "msg": "x", "type": "t"},
        {"loc": ("body", "b"), "msg": "y", "type": "t"},
    ]
    assert validation_field(errores) == "a"
