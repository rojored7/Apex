"""Reglas puras de anular un pago (S3-B5, US-097; D17, M-7, M-8 punto 3, S3-D51).

- `normalize_void_reason(value)`: NFC y recorte; vacío, solo espacios, NUL (`Cc`), U+200B (`Cf`)
  o más de `VOID_REASON_MAX` (500) caracteres tras recortar es `InvalidVoidReason` (422
  `validation_error`, `field="reason"`), sin el valor en el mensaje. Exactamente 500 pasa.
- `VoidPaymentIn` (`extra="forbid"`, `reason: SafeText`): ausente, vacío, espacios, NUL y U+200B
  se rechazan en el esquema con `loc = ("reason",)`; el recorte lo hace `SafeText`.
- `is_previous_month(paid_at, today)`: compara meses civiles de Bogotá (UTC-5, sin horario de
  verano). Valores a mano con `today` = 2026-10-21:
  - `2026-09-30T23:30-05:00` es el 30 de septiembre en Bogotá: sí;
  - `2026-10-01T04:59Z` son las 23:59 del 30 de septiembre en Bogotá: sí;
  - `2026-10-01T05:00Z` es la medianoche del 1 de octubre en Bogotá: no;
  - `2026-10-21T10:00-05:00` (hoy): no; `2026-03-15T12:00Z` (meses antes): sí;
  - cambio de año: `2025-12-31T23:00-05:00` con `today` = 2026-01-05: sí; `2026-01-01T04:59Z`
    (31 de diciembre de 2025 en Bogotá) con `today` = 2026-01-05: sí;
  - un `paid_at` del mes siguiente (no ocurre: `paid_at` nunca va al futuro) no es "anterior".
- Catálogo de los errores nuevos y del evento `MembershipActivationReverted`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.memberships.service import MembershipActivationReverted
from app.modules.payments.exceptions import InvalidVoidReason, PaymentAlreadyVoided, PaymentError
from app.modules.payments.models import VOID_REASON_MAX_LENGTH
from app.modules.payments.rules import VOID_REASON_MAX, is_previous_month, normalize_void_reason
from app.modules.payments.schemas import VoidPaymentIn
from tests.factories.payments import MOTIVO_ANULACION

BOGOTA = timezone(timedelta(hours=-5))
HOY = date(2026, 10, 21)


# normalize_void_reason ----------------------------------------------------------------------------


def test_el_tope_del_motivo_es_500_y_coincide_con_la_tabla() -> None:
    assert VOID_REASON_MAX == 500 == VOID_REASON_MAX_LENGTH


def test_recorta_el_motivo() -> None:
    assert normalize_void_reason("  Monto mal digitado  ") == "Monto mal digitado"


def test_el_motivo_queda_en_nfc() -> None:
    descompuesto = "Cobro duplicado en café"
    assert normalize_void_reason(descompuesto) == "Cobro duplicado en café"


def test_500_caracteres_tras_recortar_pasan() -> None:
    motivo = "x" * 500
    assert normalize_void_reason(f"   {motivo}   ") == motivo


@pytest.mark.parametrize(
    "motivo",
    ["", "   ", "x" * 501, "Monto\x00mal", "Monto​mal", "​"],
    ids=["vacio", "espacios", "501", "nul", "u200b", "solo-invisible"],
)
def test_motivo_invalido_es_invalid_void_reason_en_reason(motivo: str) -> None:
    with pytest.raises(InvalidVoidReason) as capturado:
        normalize_void_reason(motivo)
    error = capturado.value
    assert (error.status, error.code, error.field) == (422, "validation_error", "reason")
    if motivo.strip():
        assert motivo not in error.message


# VoidPaymentIn ------------------------------------------------------------------------------------


def test_el_esquema_recorta_el_motivo() -> None:
    assert VoidPaymentIn(reason="  Monto mal digitado  ").reason == "Monto mal digitado"


@pytest.mark.parametrize(
    "cuerpo",
    [{}, {"reason": ""}, {"reason": "   "}, {"reason": "a\x00b"}, {"reason": "a​b"}],
    ids=["ausente", "vacio", "espacios", "nul", "u200b"],
)
def test_el_esquema_rechaza_motivos_sin_texto_visible_o_con_control(
    cuerpo: dict[str, object],
) -> None:
    with pytest.raises(ValidationError) as capturado:
        VoidPaymentIn.model_validate(cuerpo)
    assert [e["loc"] for e in capturado.value.errors()] == [("reason",)]


def test_el_esquema_rechaza_campos_desconocidos() -> None:
    with pytest.raises(ValidationError) as capturado:
        VoidPaymentIn.model_validate({"reason": "Monto mal digitado", "voided_by": "x"})
    assert [e["loc"] for e in capturado.value.errors()] == [("voided_by",)]


def test_el_esquema_rechaza_un_motivo_que_no_es_texto() -> None:
    with pytest.raises(ValidationError):
        VoidPaymentIn.model_validate({"reason": 123})


# is_previous_month (meses civiles de Bogotá) ------------------------------------------------------


@pytest.mark.parametrize(
    ("paid_at", "hoy", "esperado"),
    [
        (datetime(2026, 9, 30, 23, 30, tzinfo=BOGOTA), HOY, True),
        (datetime(2026, 10, 1, 4, 59, tzinfo=UTC), HOY, True),
        (datetime(2026, 10, 1, 5, 0, tzinfo=UTC), HOY, False),
        (datetime(2026, 10, 21, 10, 0, tzinfo=BOGOTA), HOY, False),
        (datetime(2026, 3, 15, 12, 0, tzinfo=UTC), HOY, True),
        (datetime(2025, 12, 31, 23, 0, tzinfo=BOGOTA), date(2026, 1, 5), True),
        (datetime(2026, 1, 1, 4, 59, tzinfo=UTC), date(2026, 1, 5), True),
        (datetime(2026, 1, 1, 5, 0, tzinfo=UTC), date(2026, 1, 5), False),
        (datetime(2026, 11, 2, 12, 0, tzinfo=UTC), HOY, False),
    ],
    ids=[
        "30-sep-23h30-bogota",
        "01-oct-04h59z-es-30-sep",
        "01-oct-05h00z-es-01-oct",
        "hoy",
        "marzo",
        "31-dic-2025-bogota",
        "01-ene-04h59z-es-31-dic",
        "01-ene-05h00z-es-01-ene",
        "mes-siguiente",
    ],
)
def test_is_previous_month_compara_meses_de_bogota(
    paid_at: datetime, hoy: date, esperado: bool
) -> None:
    assert is_previous_month(paid_at, hoy) is esperado


def test_el_mismo_instante_en_otra_zona_da_lo_mismo() -> None:
    """El mes sale del instante en Bogotá, no del desfase con que llega."""
    instante = datetime(2026, 10, 1, 4, 59, tzinfo=UTC)
    madrid = instante.astimezone(timezone(timedelta(hours=2)))
    assert madrid.month == 10
    assert is_previous_month(madrid, HOY) is True


# Errores y evento ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("clase", "status", "code", "field"),
    [
        (PaymentAlreadyVoided, 409, "payment_already_voided", None),
        (InvalidVoidReason, 422, "validation_error", "reason"),
    ],
)
def test_catalogo_de_errores_de_anular(
    clase: type[PaymentError], status: int, code: str, field: str | None
) -> None:
    error = clase()
    assert isinstance(error, PaymentError)
    assert (error.status, error.code, error.field) == (status, code, field)
    copia = clase(error.code, error.message, field="first_payment.x", status=error.status)
    assert (copia.code, copia.field, copia.status) == (code, "first_payment.x", status)


def test_el_evento_de_reversion_lleva_solo_ids_y_el_estado_previo() -> None:
    membresia = UUID("0000000a-0000-4000-8000-00000000b501")
    socio = UUID("0000000a-0000-4000-8000-00000000b502")
    evento = MembershipActivationReverted(
        membership_id=membresia, member_id=socio, previous_status="active"
    )
    assert (evento.membership_id, evento.member_id, evento.previous_status) == (
        membresia,
        socio,
        "active",
    )
    campos = set(MembershipActivationReverted.__dataclass_fields__)
    assert campos - {"occurred_at", "event_id"} >= {"membership_id", "member_id", "previous_status"}
    assert not {"reason", "void_reason", "amount_cop"} & campos


def test_el_motivo_de_la_fabrica_es_valido() -> None:
    assert normalize_void_reason(MOTIVO_ANULACION) == MOTIVO_ANULACION


def test_el_esquema_tiene_un_tope_holgado_de_entrada_antes_de_la_regla_de_500() -> None:
    """Revisión de seguridad de B5 (LOW-2): el esquema corta lo enorme (más de
    `VOID_REASON_INPUT_MAX` = 2000) antes de normalizar; entre 501 y 2000 decide el service."""
    from app.modules.payments.schemas import VOID_REASON_INPUT_MAX

    assert VOID_REASON_INPUT_MAX == 2000
    assert VoidPaymentIn(reason="x" * VOID_REASON_INPUT_MAX).reason == "x" * 2000
    with pytest.raises(ValidationError) as capturado:
        VoidPaymentIn.model_validate({"reason": "x" * (VOID_REASON_INPUT_MAX + 1)})
    assert [e["loc"] for e in capturado.value.errors()] == [("reason",)]
