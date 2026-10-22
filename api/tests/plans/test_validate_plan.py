"""`plans.service.validate_plan` y el contrato de `PlanCreate` (S2-B9; US-078 criterios de tipo,
duración y clases; DECISIÓN 32, S2-D32).

Pura: `validate_plan(kind, duration_days, class_count)` lanza `PlanValidationError` (422,
`validation_error`) con `field` y sin repetir el valor:
- `days` con `class_count` (cualquiera, también 0) da `field="class_count"`;
- `classes` sin `class_count`, con 0, negativo o por encima de 1.000 da `field="class_count"`;
- `duration_days` 0, negativo o por encima de 3.650 da `field="duration_days"`;
- los bordes (1 y 3.650 días; 1 y 1.000 clases) son válidos.
`PlanCreate`: `StrictInt` en los tres enteros, topes de S2-D32, nombre recortado de 1 a 80 y
`extra="forbid"`.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.plans.exceptions import PlanValidationError
from app.modules.plans.schemas import (
    CLASS_COUNT_MAX,
    DURATION_DAYS_MAX,
    NAME_MAX_LENGTH,
    PRICE_COP_MAX,
    PlanCreate,
)
from app.modules.plans.service import validate_plan
from tests.plans._apoyo import cuerpo


def _falla(kind: str, duration_days: int, class_count: int | None) -> PlanValidationError:
    with pytest.raises(PlanValidationError) as error:
        validate_plan(kind, duration_days, class_count)
    return error.value


# validate_plan ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "duration_days", "class_count"),
    [
        ("days", 30, None),
        ("days", 1, None),
        ("days", DURATION_DAYS_MAX, None),
        ("classes", 60, 12),
        ("classes", 30, 1),
        ("classes", 365, CLASS_COUNT_MAX),
    ],
    ids=["mensual", "un-dia", "tope-dias", "tiquetera-12", "una-clase", "tope-clases"],
)
def test_los_planes_validos_no_lanzan(
    kind: str, duration_days: int, class_count: int | None
) -> None:
    validate_plan(kind, duration_days, class_count)


@pytest.mark.parametrize("class_count", [5, 1, 0])
def test_days_con_class_count_da_422_en_class_count(class_count: int) -> None:
    error = _falla("days", 30, class_count)
    assert error.status == 422 and error.code == "validation_error"
    assert error.field == "class_count"


@pytest.mark.parametrize(
    "class_count", [None, 0, -1, CLASS_COUNT_MAX + 1], ids=["sin", "cero", "negativo", "tope"]
)
def test_classes_sin_class_count_valido_da_422_en_class_count(class_count: int | None) -> None:
    error = _falla("classes", 60, class_count)
    assert error.status == 422 and error.field == "class_count"


@pytest.mark.parametrize("kind", ["days", "classes"])
@pytest.mark.parametrize(
    "duration_days", [0, -30, DURATION_DAYS_MAX + 1], ids=["cero", "negativo", "tope"]
)
def test_duration_days_fuera_de_rango_da_422_en_duration_days(
    kind: str, duration_days: int
) -> None:
    error = _falla(kind, duration_days, 12 if kind == "classes" else None)
    assert error.status == 422 and error.field == "duration_days"


def test_el_mensaje_no_repite_el_valor() -> None:
    error = _falla("classes", 60, 1001)
    assert error.message
    assert "1001" not in error.message and "1.001" not in error.message


# PlanCreate (contrato del cuerpo) -----------------------------------------------------------


def _campo(**cambios: Any) -> str:
    with pytest.raises(ValidationError) as error:
        PlanCreate.model_validate(cuerpo(**cambios))
    return str(error.value.errors()[0]["loc"][0])


def test_el_cuerpo_minimo_es_valido_y_recorta_el_nombre() -> None:
    plan = PlanCreate.model_validate(cuerpo(name="  Mensual  "))
    assert plan.name == "Mensual"
    assert plan.price_cop == 120_000 and type(plan.price_cop) is int
    assert plan.kind == "days" and plan.duration_days == 30 and plan.class_count is None


def test_los_topes_exactos_son_validos() -> None:
    plan = PlanCreate.model_validate(
        cuerpo(
            name="x" * NAME_MAX_LENGTH,
            price_cop=PRICE_COP_MAX,
            kind="classes",
            duration_days=DURATION_DAYS_MAX,
            class_count=CLASS_COUNT_MAX,
        )
    )
    assert (plan.price_cop, plan.duration_days, plan.class_count) == (1_000_000_000, 3_650, 1_000)
    assert PlanCreate.model_validate(cuerpo(price_cop=1, duration_days=1)).price_cop == 1


@pytest.mark.parametrize(
    "valor",
    [120000.5, 120000.0, -1, 0, "120000", True, PRICE_COP_MAX + 1, None],
    ids=["decimal", "float-entero", "negativo", "cero", "texto", "booleano", "tope", "nulo"],
)
def test_price_cop_invalido_falla_en_price_cop(valor: Any) -> None:
    assert _campo(price_cop=valor) == "price_cop"


@pytest.mark.parametrize(
    "valor",
    [0, -1, DURATION_DAYS_MAX + 1, "30", 30.5, True],
    ids=["cero", "negativo", "tope", "texto", "decimal", "booleano"],
)
def test_duration_days_invalido_falla_en_duration_days(valor: Any) -> None:
    assert _campo(duration_days=valor) == "duration_days"


@pytest.mark.parametrize(
    "valor",
    [0, -1, CLASS_COUNT_MAX + 1, "12", 12.5, False],
    ids=["cero", "negativo", "tope", "texto", "decimal", "booleano"],
)
def test_class_count_invalido_falla_en_class_count(valor: Any) -> None:
    assert _campo(kind="classes", class_count=valor) == "class_count"


@pytest.mark.parametrize(
    "valor", ["", "   ", "x" * (NAME_MAX_LENGTH + 1), None], ids=["vacio", "blanco", "81", "nulo"]
)
def test_name_invalido_falla_en_name(valor: Any) -> None:
    assert _campo(name=valor) == "name"


@pytest.mark.parametrize("valor", ["weeks", "DAYS", "", None])
def test_kind_fuera_del_catalogo_falla_en_kind(valor: Any) -> None:
    assert _campo(kind=valor) == "kind"


@pytest.mark.parametrize("extra", ["is_active", "id", "created_by", "deleted_at", "notes"])
def test_un_campo_que_el_cliente_no_envia_falla_por_extra_forbid(extra: str) -> None:
    with pytest.raises(ValidationError) as error:
        PlanCreate.model_validate({**cuerpo(), extra: "x"})
    (detalle,) = error.value.errors()
    assert detalle["type"] == "extra_forbidden" and detalle["loc"] == (extra,)
