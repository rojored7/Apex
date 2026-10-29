"""`plans.service.merge_plan` y `PlanPatch` (S4A-B7; US-080; S4A-D22). Pura: sin base de datos.

- Solo lo enviado cambia (`model_fields_set`): un `PlanPatch` vacío deja el plan igual; un campo
  ausente no es lo mismo que `null`.
- Pasar a `classes` exige `class_count` (si no, `PlanValidationError` con `field="class_count"`);
  pasar a `days` desde `classes` exige `class_count: null` explícito (S4A-D22).
- Luego corre `validate_plan` sobre el resultado: `classes` con `class_count: null` explícito da
  el mismo error.
- `PlanPatch` (`extra="forbid"`, `str_strip_whitespace`, `StrictInt` con los topes de
  `PlanCreate`): precio negativo, cero, decimal, texto o booleano; `is_active` y `deleted_at` en
  el cuerpo; nombre vacío o de 81 caracteres: `ValidationError`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.plans.exceptions import PlanValidationError
from app.modules.plans.schemas import PlanPatch, PlanSnapshot, PlanState
from app.modules.plans.service import merge_plan
from tests.plans._apoyo import parche

ID = UUID("0000000b-0000-4000-8000-00000000b007")

MENSUAL = PlanSnapshot(
    id=ID,
    name="Mensual",
    price_cop=120_000,
    kind="days",
    duration_days=30,
    class_count=None,
    is_active=True,
    deleted_at=None,
)
TIQUETERA = PlanSnapshot(
    id=ID,
    name="Tiquetera 12",
    price_cop=150_000,
    kind="classes",
    duration_days=60,
    class_count=12,
    is_active=True,
    deleted_at=None,
)


def estado(plan: PlanSnapshot, **cambios: Any) -> PlanState:
    valores: dict[str, Any] = {
        "name": plan.name,
        "price_cop": plan.price_cop,
        "kind": plan.kind,
        "duration_days": plan.duration_days,
        "class_count": plan.class_count,
    }
    valores.update(cambios)
    return PlanState(**valores)


# Lo enviado y lo no enviado -----------------------------------------------------------------


def test_solo_el_precio_cambia_el_precio() -> None:
    assert merge_plan(MENSUAL, parche(price_cop=135_000)) == estado(MENSUAL, price_cop=135_000)


def test_un_parche_vacio_deja_el_plan_igual() -> None:
    assert merge_plan(MENSUAL, parche()) == estado(MENSUAL)
    assert merge_plan(TIQUETERA, parche()) == estado(TIQUETERA)


def test_model_fields_set_distingue_no_enviado_de_null() -> None:
    assert parche().model_fields_set == set()
    assert parche(class_count=None).model_fields_set == {"class_count"}
    assert parche(price_cop=1).model_fields_set == {"price_cop"}


def test_cambia_nombre_duracion_y_clases_a_la_vez() -> None:
    salida = merge_plan(TIQUETERA, parche(name="Tiquetera 20", duration_days=90, class_count=20))
    assert salida == estado(TIQUETERA, name="Tiquetera 20", duration_days=90, class_count=20)


def test_el_nombre_llega_recortado() -> None:
    salida = merge_plan(MENSUAL, parche(name="  Mensual Plus  "))
    assert salida.name == "Mensual Plus"


def test_merge_plan_devuelve_un_plan_state_y_no_toca_el_snapshot() -> None:
    salida = merge_plan(MENSUAL, parche(price_cop=99_000))
    assert isinstance(salida, PlanState)
    assert MENSUAL.price_cop == 120_000


# Cambio de tipo (S4A-D22) --------------------------------------------------------------------


def test_a_classes_sin_class_count_da_error_de_class_count() -> None:
    with pytest.raises(PlanValidationError) as error:
        merge_plan(MENSUAL, parche(kind="classes"))
    assert (error.value.status, error.value.code) == (422, "validation_error")
    assert error.value.field == "class_count"


def test_a_classes_con_12_clases_es_valido() -> None:
    salida = merge_plan(MENSUAL, parche(kind="classes", class_count=12))
    assert salida == estado(MENSUAL, kind="classes", class_count=12)


def test_a_days_sin_class_count_null_explicito_da_error_de_class_count() -> None:
    with pytest.raises(PlanValidationError) as error:
        merge_plan(TIQUETERA, parche(kind="days"))
    assert error.value.field == "class_count"


def test_a_days_con_class_count_null_explicito_es_valido() -> None:
    salida = merge_plan(TIQUETERA, parche(kind="days", class_count=None))
    assert salida == estado(TIQUETERA, kind="days", class_count=None)


def test_classes_con_class_count_null_explicito_da_error() -> None:
    """Sin cambiar `kind`, borrar las clases de un plan por clases lo invalida (`validate_plan`)."""
    with pytest.raises(PlanValidationError) as error:
        merge_plan(TIQUETERA, parche(class_count=None))
    assert error.value.field == "class_count"


def test_days_con_clases_da_error() -> None:
    with pytest.raises(PlanValidationError) as error:
        merge_plan(MENSUAL, parche(class_count=8))
    assert error.value.field == "class_count"


def test_days_con_class_count_null_explicito_no_cambia_nada() -> None:
    assert merge_plan(MENSUAL, parche(class_count=None)) == estado(MENSUAL)


def test_el_mensaje_del_error_no_repite_el_valor() -> None:
    with pytest.raises(PlanValidationError) as error:
        merge_plan(MENSUAL, parche(class_count=987))
    assert "987" not in error.value.message


# `PlanPatch` --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("price_cop", -1),
        ("price_cop", 0),
        ("price_cop", 120_000.5),
        ("price_cop", "120000"),
        ("price_cop", True),
        ("price_cop", 1_000_000_001),
        ("duration_days", 0),
        ("duration_days", 3_651),
        ("class_count", 0),
        ("class_count", 1_001),
        ("kind", "weeks"),
        ("name", ""),
        ("name", "   "),
        ("name", "x" * 81),
        ("name", "Mensual\x00"),
        ("is_active", False),
        ("deleted_at", datetime(2026, 10, 21).isoformat()),
        ("id", str(ID)),
    ],
)
def test_plan_patch_rechaza_lo_invalido(campo: str, valor: object) -> None:
    with pytest.raises(ValidationError):
        PlanPatch.model_validate({campo: valor})


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("price_cop", 1),
        ("price_cop", 1_000_000_000),
        ("duration_days", 3_650),
        ("class_count", 1_000),
        ("name", "x" * 80),
        ("kind", "classes"),
    ],
)
def test_plan_patch_acepta_los_topes(campo: str, valor: object) -> None:
    assert getattr(PlanPatch.model_validate({campo: valor}), campo) == valor


@pytest.mark.parametrize("campo", ["name", "price_cop", "kind", "duration_days"])
def test_null_explicito_en_un_campo_obligatorio_da_error_con_su_field(campo: str) -> None:
    """S4A-D114 (Verde de B7): solo `class_count` es anulable; los demás con `null` dan 422."""
    with pytest.raises(PlanValidationError) as error:
        merge_plan(MENSUAL, PlanPatch.model_validate({campo: None}))
    assert (error.value.status, error.value.field) == (422, campo)
