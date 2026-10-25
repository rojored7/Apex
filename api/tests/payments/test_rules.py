"""Reglas puras, esquemas y errores de pagos (S3-B3, US-095; D17, H-1, H-2, M-4, M-7, M-8).

"Ahora" es `T0` = 2026-10-21T15:00:00Z (D33). Valores a mano:
- futuro: tolerancia de 5 minutos: 15:04:59Z pasa, 15:05:01Z da `PaidAtInFuture`;
- retroactividad del coach con `max_retroactive_days = 7`: 2026-10-14T15:00:00Z (justo 7 días)
  pasa, 2026-10-14T14:59:59Z y 2026-10-13T15:00:00Z (8 días) dan `PaidAtTooRetroactive`; el admin
  acepta 400 días atrás (2025-09-16T15:00:00Z);
- piso `PAID_AT_FLOOR` = 2020-01-01T00:00:00Z: 2019-12-31T23:59:59Z da `PaidAtInvalid` para los
  dos roles; `0001-01-01T00:00:00+05:00` también (y nunca `OverflowError`);
- duplicado (ventana de 120 s, solo piso): registrado a las 14:58:01Z (119 s) sí, a las 14:58:00Z
  (120 s) sí, a las 14:57:59Z (121 s) no;
- tope de 60 pagos no anulados: con 59 se registra el 60; con 60, el 61 da `PaymentLimitReached`;
- `MAX_AMOUNT_COP` = 1.000.000.000: ese monto pasa y 1.000.000.001 no.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.errors import DomainError
from app.modules.payments.exceptions import (
    MembershipCancelled,
    MembershipGateNotRegistered,
    PaidAtInFuture,
    PaidAtInvalid,
    PaidAtTooRetroactive,
    PaymentError,
    PaymentExceedsBalance,
    PaymentLimitReached,
    PaymentMembershipNotFound,
    PaymentNotFound,
    PossibleDuplicatePayment,
)
from app.modules.payments.models import MAX_AMOUNT_COP, PAYMENT_METHODS
from app.modules.payments.rules import (
    DUPLICATE_WINDOW,
    MAX_PAYMENTS_PER_MEMBERSHIP,
    PAID_AT_FLOOR,
    PAID_AT_FUTURE_TOLERANCE,
    REFERENCE_PATTERN,
    PaymentFingerprint,
    check_balance,
    check_payment_count,
    is_possible_duplicate,
    normalize_reference,
    validate_paid_at,
)
from app.modules.payments.schemas import PaymentIn, PaymentOut
from app.modules.payments.service import PaymentRegistered, PaymentVoided
from tests.payments._apoyo import CAMPOS_PAYMENT

AHORA = datetime(2026, 10, 21, 15, 0, 0, tzinfo=UTC)
ACTOR = UUID("0000000a-0000-4000-8000-00000000b001")
OTRO = UUID("0000000a-0000-4000-8000-00000000b002")


def _validar(paid_at: datetime, *, role: str = "coach", dias: int = 7) -> None:
    validate_paid_at(paid_at, AHORA, role=role, max_retroactive_days=dias)


# Constantes ---------------------------------------------------------------------------------


def test_constantes_de_las_reglas() -> None:
    assert datetime(2020, 1, 1, tzinfo=UTC) == PAID_AT_FLOOR
    assert timedelta(minutes=5) == PAID_AT_FUTURE_TOLERANCE
    assert timedelta(seconds=120) == DUPLICATE_WINDOW
    assert MAX_PAYMENTS_PER_MEMBERSHIP == 60
    assert MAX_AMOUNT_COP == 1_000_000_000
    assert PAYMENT_METHODS == ("cash", "nequi", "breb")


# validate_paid_at (M-4, M-8) -------------------------------------------------------------------


@pytest.mark.parametrize("role", ["coach", "admin"])
@pytest.mark.parametrize(
    "paid_at",
    [AHORA, AHORA + timedelta(minutes=4, seconds=59), AHORA - timedelta(days=1)],
    ids=["ahora", "mas-4-min-59-s", "ayer"],
)
def test_ahora_y_dentro_de_la_tolerancia_pasan(paid_at: datetime, role: str) -> None:
    _validar(paid_at, role=role)


@pytest.mark.parametrize("role", ["coach", "admin"])
def test_mas_de_5_minutos_en_el_futuro_es_paid_at_in_future(role: str) -> None:
    with pytest.raises(PaidAtInFuture) as error:
        _validar(AHORA + timedelta(minutes=5, seconds=1), role=role)
    assert (error.value.status, error.value.code, error.value.field) == (
        422,
        "validation_error",
        "paid_at",
    )


def test_un_paid_at_sin_zona_es_paid_at_invalid() -> None:
    with pytest.raises(PaidAtInvalid) as error:
        _validar(datetime(2026, 10, 21, 10, 0, 0))  # sin zona: el caso es justo ese
    assert (error.value.status, error.value.code, error.value.field) == (
        422,
        "validation_error",
        "paid_at",
    )


def test_el_coach_registra_hasta_siete_dias_atras() -> None:
    _validar(AHORA - timedelta(days=7))  # 2026-10-14T15:00:00Z


@pytest.mark.parametrize(
    "paid_at",
    [AHORA - timedelta(days=7, seconds=1), AHORA - timedelta(days=8)],
    ids=["7-dias-y-1-s", "8-dias"],
)
def test_el_coach_mas_atras_es_paid_at_too_retroactive(paid_at: datetime) -> None:
    with pytest.raises(PaidAtTooRetroactive) as error:
        _validar(paid_at)
    assert (error.value.status, error.value.code, error.value.field) == (
        422,
        "paid_at_too_retroactive",
        "paid_at",
    )


def test_el_tope_del_coach_sale_de_max_retroactive_days() -> None:
    _validar(AHORA - timedelta(days=3), dias=3)
    with pytest.raises(PaidAtTooRetroactive):
        _validar(AHORA - timedelta(days=3, minutes=1), dias=3)


def test_el_admin_no_tiene_tope_retroactivo() -> None:
    _validar(AHORA - timedelta(days=400), role="admin")  # 2025-09-16T15:00:00Z
    _validar(PAID_AT_FLOOR, role="admin")


@pytest.mark.parametrize("role", ["coach", "admin"])
@pytest.mark.parametrize(
    "paid_at",
    [
        datetime(2019, 12, 31, 23, 59, 59, tzinfo=UTC),
        datetime(1, 1, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=5))),
    ],
    ids=["2019-12-31T23-59-59Z", "anio-1-con-desfase-positivo"],
)
def test_antes_del_piso_es_paid_at_invalid_sin_overflow(paid_at: datetime, role: str) -> None:
    with pytest.raises(PaidAtInvalid) as error:
        _validar(paid_at, role=role, dias=30)
    assert not isinstance(error.value, PaidAtInFuture)
    assert (error.value.status, error.value.field) == (422, "paid_at")


def test_un_futuro_extremo_es_paid_at_in_future_sin_overflow() -> None:
    with pytest.raises(PaidAtInFuture):
        _validar(datetime(9999, 12, 31, 23, 59, 59, tzinfo=UTC), role="admin")


# normalize_reference y REFERENCE_PATTERN (M-7) -----------------------------------------------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("  NEQ-00123  ", "NEQ-00123"),
        ("", None),
        ("   ", None),
        (None, None),
        ("A" * 64, "A" * 64),
    ],
    ids=["recorta", "vacia", "solo-espacios", "nula", "64"],
)
def test_normalize_reference(valor: str | None, esperado: str | None) -> None:
    assert normalize_reference(valor) == esperado


def test_normalize_reference_con_65_es_value_error_sin_el_valor() -> None:
    valor = "Z" * 65
    with pytest.raises(ValueError) as error:
        normalize_reference(valor)
    assert "ZZZZ" not in str(error.value)


@pytest.mark.parametrize("referencia", ["NEQ-00123", "12/10 #4", "A", "a.b_c", "Z" * 64])
def test_el_patron_acepta_comprobantes(referencia: str) -> None:
    assert re.fullmatch(REFERENCE_PATTERN, referencia)


@pytest.mark.parametrize(
    "referencia",
    ["mi correo a@b.co", "3001234567 mamá", "ñ", "​123", "-123", "Z" * 65],
    ids=["correo", "telefono-y-nombre", "enie", "u200b", "empieza-con-guion", "65"],
)
def test_el_patron_rechaza_frases_correos_y_no_ascii(referencia: str) -> None:
    assert re.fullmatch(REFERENCE_PATTERN, referencia) is None


# check_balance (H-1) ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pagado", "monto", "confirmado"),
    [(60_000, 60_000, False), (60_000, 59_999, False), (60_000, 60_001, True), (0, 120_000, False)],
    ids=["igual-al-saldo", "menor", "mayor-confirmado", "todo-de-una"],
)
def test_check_balance_acepta(pagado: int, monto: int, confirmado: bool) -> None:
    check_balance(120_000, pagado, monto, confirmed=confirmado)


@pytest.mark.parametrize(
    ("pagado", "monto"),
    [(60_000, 60_001), (120_000, 1), (130_000, 1)],
    ids=["mayor-sin-confirmar", "saldo-cero", "ya-sobrepagada"],
)
def test_check_balance_sin_confirmar_es_payment_exceeds_balance(pagado: int, monto: int) -> None:
    with pytest.raises(PaymentExceedsBalance) as error:
        check_balance(120_000, pagado, monto, confirmed=False)
    assert (error.value.status, error.value.code, error.value.field) == (
        409,
        "payment_exceeds_balance",
        "amount_cop",
    )
    check_balance(120_000, pagado, monto, confirmed=True)


# is_possible_duplicate (H-1) --------------------------------------------------------------------


def _huella(hace: timedelta = timedelta(seconds=119), **cambios: Any) -> PaymentFingerprint:
    datos: dict[str, Any] = {
        "registered_by": ACTOR,
        "amount_cop": 30_000,
        "method": "cash",
        "reference": "REC-1",
        "voided": False,
        "registered_at": AHORA - hace,
    }
    datos.update(cambios)
    return PaymentFingerprint(**datos)


CANDIDATO = _huella(timedelta(0))


@pytest.mark.parametrize(
    "previa",
    [
        _huella(timedelta(seconds=119)),
        _huella(timedelta(seconds=120)),
        _huella(timedelta(seconds=-30)),
    ],
    ids=["119-s", "120-s", "reloj-de-la-base-adelantado"],
)
def test_un_pago_igual_reciente_es_duplicado(previa: PaymentFingerprint) -> None:
    assert is_possible_duplicate([previa], CANDIDATO, AHORA) is True


@pytest.mark.parametrize(
    "previa",
    [
        _huella(timedelta(seconds=121)),
        _huella(reference="REC-2"),
        _huella(reference=None),
        _huella(voided=True),
        _huella(registered_by=OTRO),
        _huella(amount_cop=30_001),
        _huella(method="nequi"),
    ],
    ids=[
        "121-s",
        "otra-referencia",
        "sin-referencia",
        "anulado",
        "otro-usuario",
        "otro-monto",
        "otro-medio",
    ],
)
def test_un_pago_que_difiere_o_es_viejo_no_es_duplicado(previa: PaymentFingerprint) -> None:
    assert is_possible_duplicate([previa], CANDIDATO, AHORA) is False


def test_dos_referencias_nulas_son_iguales() -> None:
    candidato = _huella(timedelta(0), reference=None)
    assert is_possible_duplicate([_huella(reference=None)], candidato, AHORA) is True


def test_sin_pagos_recientes_no_hay_duplicado_y_basta_uno_que_coincida() -> None:
    assert is_possible_duplicate([], CANDIDATO, AHORA) is False
    varios = [_huella(voided=True), _huella(registered_by=OTRO), _huella()]
    assert is_possible_duplicate(varios, CANDIDATO, AHORA) is True


# check_payment_count (H-2) ----------------------------------------------------------------------


def test_check_payment_count_59_pasa_y_60_es_payment_limit_reached() -> None:
    check_payment_count(0)
    check_payment_count(59)
    with pytest.raises(PaymentLimitReached) as error:
        check_payment_count(60)
    assert (error.value.status, error.value.code, error.value.field) == (
        409,
        "payment_limit_reached",
        None,
    )


def test_check_payment_count_respeta_el_limite_dado() -> None:
    check_payment_count(1, limit=2)
    with pytest.raises(PaymentLimitReached):
        check_payment_count(2, limit=2)


# PaymentIn (D17, S3-D41, S3-D50) ------------------------------------------------------------------


def _pago(**cambios: Any) -> PaymentIn:
    return PaymentIn.model_validate({"amount_cop": 120_000, "method": "nequi", **cambios})


def _campo_del_error(**cambios: Any) -> str:
    with pytest.raises(ValidationError) as error:
        _pago(**cambios)
    return ".".join(str(p) for p in error.value.errors()[0]["loc"])


def test_payment_in_por_defecto() -> None:
    pago = _pago()
    assert (pago.amount_cop, pago.method, pago.reference, pago.paid_at) == (
        120_000,
        "nequi",
        None,
        None,
    )
    assert (pago.confirm_overpayment, pago.confirm_duplicate) == (False, False)


@pytest.mark.parametrize("monto", [1, 120_000, 1_000_000_000])
def test_montos_enteros_validos(monto: int) -> None:
    pago = _pago(amount_cop=monto)
    assert pago.amount_cop == monto and type(pago.amount_cop) is int


@pytest.mark.parametrize(
    "monto",
    [0, -1, 120_000.5, "120000", True, 1_000_000_001],
    ids=["cero", "negativo", "decimal", "texto", "booleano", "mil-millones-y-uno"],
)
def test_montos_invalidos_dan_422_en_amount_cop(monto: object) -> None:
    assert _campo_del_error(amount_cop=monto) == "amount_cop"


@pytest.mark.parametrize("medio", ["cash", "nequi", "breb"])
def test_los_tres_medios(medio: str) -> None:
    assert _pago(method=medio).method == medio


def test_medio_desconocido_da_422_en_method() -> None:
    assert _campo_del_error(method="tarjeta") == "method"


@pytest.mark.parametrize("valor", ["yes", "true", 1])
@pytest.mark.parametrize("campo", ["confirm_overpayment", "confirm_duplicate"])
def test_las_confirmaciones_son_booleanos_estrictos(campo: str, valor: object) -> None:
    assert _campo_del_error(**{campo: valor}) == campo
    assert getattr(_pago(**{campo: True}), campo) is True


def test_un_campo_desconocido_da_422() -> None:
    assert _campo_del_error(extra=1) == "extra"


@pytest.mark.parametrize(
    ("enviada", "guardada"),
    [("  NEQ-00123  ", "NEQ-00123"), ("12/10 #4", "12/10 #4"), ("", None), ("   ", None)],
)
def test_la_referencia_se_recorta_y_vacia_pasa_a_none(enviada: str, guardada: str | None) -> None:
    assert _pago(reference=enviada).reference == guardada


@pytest.mark.parametrize(
    "referencia",
    ["mi correo a@b.co", "3001234567 mamá", "ñ", "​123", "Z" * 65],
    ids=["correo", "telefono-y-nombre", "enie", "u200b", "65"],
)
def test_una_referencia_fuera_del_patron_da_422_en_reference(referencia: str) -> None:
    assert _campo_del_error(reference=referencia) == "reference"


def test_paid_at_exige_zona() -> None:
    assert _campo_del_error(paid_at="2026-10-21T10:00:00") == "paid_at"
    pago = _pago(paid_at="2026-10-21T10:00:00-05:00")
    assert pago.paid_at == AHORA


def test_payment_out_tiene_exactamente_los_campos_de_la_fila() -> None:
    assert set(PaymentOut.model_fields) == CAMPOS_PAYMENT
    assert not {"confirm_overpayment", "confirm_duplicate"} & set(PaymentOut.model_fields)


# Errores y eventos (D34, D1) ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("clase", "status", "code", "field"),
    [
        (PaymentMembershipNotFound, 404, "membership_not_found", None),
        (MembershipCancelled, 409, "membership_cancelled", None),
        (PaidAtInvalid, 422, "validation_error", "paid_at"),
        (PaidAtInFuture, 422, "validation_error", "paid_at"),
        (PaidAtTooRetroactive, 422, "paid_at_too_retroactive", "paid_at"),
        (PaymentExceedsBalance, 409, "payment_exceeds_balance", "amount_cop"),
        (PossibleDuplicatePayment, 409, "payment_possible_duplicate", None),
        (PaymentLimitReached, 409, "payment_limit_reached", None),
        (PaymentNotFound, 404, "payment_not_found", None),
    ],
)
def test_catalogo_de_errores(
    clase: type[PaymentError], status: int, code: str, field: str | None
) -> None:
    error = clase()
    assert isinstance(error, PaymentError)
    assert (error.status, error.code, error.field) == (status, code, field)
    copia = clase(error.code, error.message, field="first_payment.x", status=error.status)
    assert (copia.code, copia.field, copia.status) == (code, "first_payment.x", status)


def test_sin_gate_es_un_runtime_error_y_no_un_error_de_dominio() -> None:
    assert issubclass(MembershipGateNotRegistered, RuntimeError)
    assert not issubclass(MembershipGateNotRegistered, DomainError)


def test_los_eventos_llevan_solo_ids_y_monto() -> None:
    registrado = PaymentRegistered(membership_id=ACTOR, payment_id=OTRO, amount_cop=60_000)
    assert (registrado.membership_id, registrado.payment_id, registrado.amount_cop) == (
        ACTOR,
        OTRO,
        60_000,
    )
    anulado = PaymentVoided(membership_id=ACTOR, payment_id=OTRO)
    assert (anulado.membership_id, anulado.payment_id) == (ACTOR, OTRO)
