"""Medios de pago en settings, sin base (S3-B3, US-056; D24, S3-D55, L-3).

- `PAYMENT_METHOD_CODES` es `("cash", "nequi", "breb")` y la sección tiene exactamente esas claves.
- `decorate_methods(codes, labels)` (pura): un `PaymentMethodInfo` por código, en el orden de
  `codes` aunque `labels` venga en otro orden; la etiqueta guardada o la por defecto si falta;
  ignora claves ajenas (`tarjeta`).
- `validate_section(payment_methods, ...)`: clave extra `tarjeta` → `value.tarjeta`; sin `nequi`
  → `value.nequi`; `label` vacía → `value.cash.label`; `label` de 31 → `value.cash.label`; `hint`
  de 121 → `value.cash.hint`; `label` con U+200B (`SafeText`) → `value.cash.label`; dos etiquetas
  iguales sin distinguir mayúsculas ("Nequi" en `cash` y "nequi" en `nequi`) →
  `value.nequi.label`. El mensaje nunca repite el valor.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.settings.exceptions import SettingsValidationError
from app.modules.settings.schemas import (
    PAYMENT_METHOD_CODES,
    MethodLabel,
    PaymentMethodInfo,
    PaymentMethodsSettings,
    SectionKey,
)
from app.modules.settings.service import decorate_methods, validate_section
from tests.settings._apoyo import PAYMENT_METHODS_OK

POR_DEFECTO = (
    PaymentMethodInfo(code="cash", label="Efectivo", hint=""),
    PaymentMethodInfo(code="nequi", label="Nequi", hint=""),
    PaymentMethodInfo(code="breb", label="Bre-B", hint=""),
)


def _etiquetas(valor: dict[str, Any]) -> dict[str, MethodLabel]:
    return {codigo: MethodLabel.model_validate(dato) for codigo, dato in valor.items()}


def test_los_codigos_son_fijos_y_son_las_claves_de_la_seccion() -> None:
    assert PAYMENT_METHOD_CODES == ("cash", "nequi", "breb")
    assert tuple(PaymentMethodsSettings.model_fields) == PAYMENT_METHOD_CODES


# decorate_methods -------------------------------------------------------------------------------


def test_decorate_methods_con_etiquetas_por_defecto() -> None:
    etiquetas = _etiquetas(
        {
            "cash": {"label": "Efectivo"},
            "nequi": {"label": "Nequi"},
            "breb": {"label": "Bre-B"},
        }
    )
    assert decorate_methods(PAYMENT_METHOD_CODES, etiquetas) == POR_DEFECTO


def test_decorate_methods_con_etiquetas_personalizadas_en_orden_fijo() -> None:
    """El JSON guardado puede venir en cualquier orden: la salida sigue el de los códigos."""
    desordenado = {codigo: PAYMENT_METHODS_OK[codigo] for codigo in ("breb", "nequi", "cash")}
    salida = decorate_methods(PAYMENT_METHOD_CODES, _etiquetas(desordenado))
    assert salida == (
        PaymentMethodInfo(code="cash", label="Caja", hint="Billetes y monedas"),
        PaymentMethodInfo(code="nequi", label="Nequi", hint="Número de comprobante"),
        PaymentMethodInfo(code="breb", label="Bre-B (Bancolombia)", hint=""),
    )


def test_decorate_methods_usa_el_default_si_falta_un_codigo_e_ignora_los_ajenos() -> None:
    etiquetas = _etiquetas({"cash": {"label": "Caja"}, "tarjeta": {"label": "Tarjeta"}})
    salida = decorate_methods(PAYMENT_METHOD_CODES, etiquetas)
    assert [m.code for m in salida] == ["cash", "nequi", "breb"]
    assert [m.label for m in salida] == ["Caja", "Nequi", "Bre-B"]


def test_decorate_methods_sin_etiquetas_da_los_defaults() -> None:
    assert decorate_methods(PAYMENT_METHOD_CODES, {}) == POR_DEFECTO


# validate_section -------------------------------------------------------------------------------


def test_validate_section_acepta_las_tres_y_recorta() -> None:
    valor = {
        "cash": {"label": "  Caja  ", "hint": "  Billetes y monedas "},
        "nequi": {"label": "Nequi"},
        "breb": {"label": "Bre-B (Bancolombia)", "hint": "   "},
    }
    modelo = validate_section(SectionKey.payment_methods, valor)
    assert modelo.model_dump(mode="json") == {
        "cash": {"label": "Caja", "hint": "Billetes y monedas"},
        "nequi": {"label": "Nequi", "hint": ""},
        "breb": {"label": "Bre-B (Bancolombia)", "hint": ""},
    }


def _campo(valor: dict[str, Any]) -> str | None:
    with pytest.raises(SettingsValidationError) as error:
        validate_section(SectionKey.payment_methods, valor)
    assert (error.value.status, error.value.code) == (422, "validation_error")
    return error.value.field


def _con(codigo: str, **dato: Any) -> dict[str, Any]:
    return {**PAYMENT_METHODS_OK, codigo: {**PAYMENT_METHODS_OK[codigo], **dato}}


def test_un_codigo_ajeno_da_value_tarjeta() -> None:
    assert _campo({**PAYMENT_METHODS_OK, "tarjeta": {"label": "Tarjeta"}}) == "value.tarjeta"


def test_sin_nequi_da_value_nequi() -> None:
    sin_nequi = {k: v for k, v in PAYMENT_METHODS_OK.items() if k != "nequi"}
    assert _campo(sin_nequi) == "value.nequi"


@pytest.mark.parametrize(
    "etiqueta",
    ["", "   ", "x" * 31, "​Caja", "Caja‮"],
    ids=["vacia", "espacios", "31", "u200b", "u202e"],
)
def test_una_etiqueta_invalida_da_value_cash_label(etiqueta: str) -> None:
    assert _campo(_con("cash", label=etiqueta)) == "value.cash.label"


def test_la_etiqueta_de_30_y_la_pista_de_120_pasan() -> None:
    valor = _con("cash", label="x" * 30, hint="y" * 120)
    modelo = validate_section(SectionKey.payment_methods, valor)
    assert modelo.model_dump()["cash"] == {"label": "x" * 30, "hint": "y" * 120}


@pytest.mark.parametrize("pista", ["y" * 121, "​"], ids=["121", "u200b"])
def test_una_pista_invalida_da_value_cash_hint(pista: str) -> None:
    assert _campo(_con("cash", hint=pista)) == "value.cash.hint"


def test_un_campo_extra_en_un_medio_da_su_ruta() -> None:
    assert _campo(_con("breb", color="azul")) == "value.breb.color"


@pytest.mark.parametrize(
    ("valor", "campo"),
    [
        (
            {
                "cash": {"label": "Nequi"},
                "nequi": {"label": "nequi"},
                "breb": {"label": "Bre-B"},
            },
            "value.nequi.label",
        ),
        (
            {
                "cash": {"label": "Efectivo"},
                "nequi": {"label": "Nequi"},
                "breb": {"label": "EFECTIVO"},
            },
            "value.breb.label",
        ),
    ],
    ids=["nequi-repite-cash", "breb-repite-cash"],
)
def test_dos_etiquetas_iguales_sin_distinguir_mayusculas(valor: dict[str, Any], campo: str) -> None:
    assert _campo(valor) == campo


def test_el_mensaje_no_repite_la_etiqueta_rechazada() -> None:
    etiqueta = "Etiqueta-Secreta-7731" * 2
    with pytest.raises(SettingsValidationError) as error:
        validate_section(SectionKey.payment_methods, _con("cash", label=etiqueta))
    assert etiqueta not in error.value.message and etiqueta not in str(error.value)
