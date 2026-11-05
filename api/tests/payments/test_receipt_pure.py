"""`payments/receipt.py`: funciones puras del recibo PDF (S5-B11, US-137, S5-D40, S5-D65).

# Rojo B11

Sin base de datos. Valores calculados a mano:
- `format_cop`: símbolo, espacio, punto de miles, sin decimales (`120000` es `$ 120.000`);
- `format_bogota`: `D mmm AAAA, h:mm a. m.|p. m.` en hora de Bogotá (UTC-5, sin horario de
  verano): `2026-10-21T15:00Z` es `21 oct 2026, 10:00 a. m.`; mediodía `12:00 p. m.`; las 00:05
  `12:05 a. m.`; el día y el mes sin ceros a la izquierda en el día (`1 nov 2026`);
- `receipt_context`: nombre (nombre + espacio + apellido) cortado a 60, referencia a 40, anulado
  con motivo y fecha, sin referencia queda `None`;
- `render_receipt`: una página con la frase fija, el monto, el socio y el plan; `ANULADO` con el
  motivo solo si está anulado; nunca el documento, el teléfono ni el correo del socio.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from io import BytesIO
from uuid import UUID

import pytest
from pypdf import PdfReader

from app.core.pdf import MAX_PDF_BYTES
from app.modules.payments.receipt import (
    NAME_MAX,
    RECEIPT_NOTICE,
    REFERENCE_MAX,
    ReceiptContext,
    format_bogota,
    format_cop,
    receipt_context,
    render_receipt,
)
from app.modules.payments.schemas import PaymentDetail
from app.modules.settings.schemas import GymView

PAGO = UUID("3f2a9c10-7b1e-4d55-9a0c-5e6f7a8b9c0d")
OTRO = UUID("11111111-2222-4333-8444-555555555555")
PAGADO = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
ANULADO_EN = datetime(2026, 10, 22, 14, 30, tzinfo=UTC)
FRASE = "Comprobante interno de pago. No es factura electrónica."
GIMNASIO = GymView(
    name="CrossFit Norte",
    nit="900123456-7",
    address="Calle 10 # 5-20",
    city="Medellín",
    phone="3001112233",
)


def detalle(**cambios: object) -> PaymentDetail:
    base: dict[str, object] = {
        "id": PAGO,
        "paid_at": PAGADO,
        "amount_cop": 120_000,
        "method": "nequi",
        "reference": "NQ-778",
        "voided": False,
        "void_reason": None,
        "registered_by": OTRO,
        "registered_by_name": "l•••@test.apex",
        "membership_id": OTRO,
        "member_id": OTRO,
        "member_first_name": "Lucía",
        "member_last_name": "Gómez",
        "plan_name": "Mensual",
        "membership_start_date": date(2026, 10, 1),
        "membership_end_date": date(2026, 10, 30),
        "backdated": False,
        "voided_by": None,
        "voided_by_name": None,
        "voided_at": None,
        "created_at": PAGADO,
    }
    base.update(cambios)
    return PaymentDetail.model_validate(base)


def texto_del_recibo(ctx: ReceiptContext) -> str:
    datos = render_receipt(ctx)
    assert len(datos) <= MAX_PDF_BYTES
    lector = PdfReader(BytesIO(datos), strict=True)
    assert len(lector.pages) == 1
    return "\n".join(p.extract_text() for p in lector.pages)


# format_cop ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("monto", "esperado"),
    [
        (0, "$ 0"),
        (999, "$ 999"),
        (1_000, "$ 1.000"),
        (60_000, "$ 60.000"),
        (120_000, "$ 120.000"),
        (1_500_000, "$ 1.500.000"),
        (12_345_678, "$ 12.345.678"),
    ],
)
def test_format_cop_usa_punto_de_miles_y_sin_decimales(monto: int, esperado: str) -> None:
    assert format_cop(monto) == esperado


# format_bogota -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("instante", "esperado"),
    [
        (datetime(2026, 10, 21, 15, 0, tzinfo=UTC), "21 oct 2026, 10:00 a. m."),
        (datetime(2026, 10, 21, 17, 0, tzinfo=UTC), "21 oct 2026, 12:00 p. m."),
        (datetime(2026, 10, 21, 20, 5, tzinfo=UTC), "21 oct 2026, 3:05 p. m."),
        (datetime(2026, 1, 9, 13, 7, tzinfo=UTC), "9 ene 2026, 8:07 a. m."),
        (datetime(2026, 12, 31, 18, 59, tzinfo=UTC), "31 dic 2026, 1:59 p. m."),
    ],
)
def test_format_bogota_da_dia_mes_abreviado_anio_y_hora_de_12_horas(
    instante: datetime, esperado: str
) -> None:
    assert format_bogota(instante) == esperado


def test_format_bogota_cruza_la_medianoche_hacia_el_dia_anterior() -> None:
    # 2026-11-01T03:30Z es 2026-10-31 22:30 en Bogotá (UTC-5).
    assert format_bogota(datetime(2026, 11, 1, 3, 30, tzinfo=UTC)) == "31 oct 2026, 10:30 p. m."


def test_format_bogota_la_medianoche_de_bogota_es_las_12_a_m() -> None:
    # 2026-11-01T05:05Z es 2026-11-01 00:05 en Bogotá.
    assert format_bogota(datetime(2026, 11, 1, 5, 5, tzinfo=UTC)) == "1 nov 2026, 12:05 a. m."


def test_format_bogota_cruza_el_fin_de_anio() -> None:
    # 2027-01-01T04:00Z es 2026-12-31 23:00 en Bogotá.
    assert format_bogota(datetime(2027, 1, 1, 4, 0, tzinfo=UTC)) == "31 dic 2026, 11:00 p. m."


# receipt_context -----------------------------------------------------------------------------


def test_el_contexto_de_un_pago_vigente_trae_los_datos_formateados() -> None:
    ctx = receipt_context(detalle(), GIMNASIO, "Nequi")
    assert ctx.gym_name == "CrossFit Norte"
    assert (ctx.gym_nit, ctx.gym_address, ctx.gym_city, ctx.gym_phone) == (
        "900123456-7",
        "Calle 10 # 5-20",
        "Medellín",
        "3001112233",
    )
    assert ctx.payment_id == PAGO
    assert ctx.member_name == "Lucía Gómez"
    assert ctx.plan_name == "Mensual"
    assert (ctx.period_start, ctx.period_end) == (date(2026, 10, 1), date(2026, 10, 30))
    assert ctx.method_label == "Nequi"
    assert ctx.reference == "NQ-778"
    assert ctx.amount_text == "$ 120.000"
    assert ctx.paid_at_text == "21 oct 2026, 10:00 a. m."
    assert (ctx.voided, ctx.void_reason, ctx.voided_at_text) == (False, None, None)


def test_el_contexto_no_tiene_campos_de_documento_telefono_ni_correo_del_socio() -> None:
    nombres = set(ReceiptContext.__dataclass_fields__)
    assert not {n for n in nombres if "document" in n or "email" in n or "phone" in n} - {
        "gym_phone"
    }
    assert "member_phone" not in nombres
    assert "member_email" not in nombres


def test_el_nombre_se_corta_a_60_caracteres() -> None:
    ctx = receipt_context(
        detalle(member_first_name="Ana", member_last_name="B" * 80), GIMNASIO, "Efectivo"
    )
    assert NAME_MAX == 60
    assert ctx.member_name == "Ana " + "B" * 56
    assert len(ctx.member_name) == 60


def test_un_nombre_de_exactamente_60_no_se_corta() -> None:
    ctx = receipt_context(
        detalle(member_first_name="Ana", member_last_name="B" * 56), GIMNASIO, "Efectivo"
    )
    assert ctx.member_name == "Ana " + "B" * 56


def test_la_referencia_se_corta_a_40_caracteres() -> None:
    ctx = receipt_context(detalle(reference="R" * 55), GIMNASIO, "Nequi")
    assert REFERENCE_MAX == 40
    assert ctx.reference == "R" * 40


def test_una_referencia_de_exactamente_40_no_se_corta() -> None:
    ctx = receipt_context(detalle(reference="R" * 40), GIMNASIO, "Nequi")
    assert ctx.reference == "R" * 40


def test_sin_referencia_el_contexto_la_deja_en_none() -> None:
    ctx = receipt_context(detalle(reference=None), GIMNASIO, "Efectivo")
    assert ctx.reference is None


def test_un_pago_anulado_trae_el_motivo_y_la_fecha_de_anulacion_en_bogota() -> None:
    ctx = receipt_context(
        detalle(voided=True, void_reason="Monto mal digitado", voided_at=ANULADO_EN),
        GIMNASIO,
        "Nequi",
    )
    assert ctx.voided is True
    assert ctx.void_reason == "Monto mal digitado"
    # 2026-10-22T14:30Z es 09:30 en Bogotá.
    assert ctx.voided_at_text == "22 oct 2026, 9:30 a. m."


def test_los_datos_opcionales_del_gimnasio_pasan_como_none() -> None:
    ctx = receipt_context(detalle(), GymView(name="APEX"), "Nequi")
    assert (ctx.gym_name, ctx.gym_nit, ctx.gym_address, ctx.gym_city, ctx.gym_phone) == (
        "APEX",
        None,
        None,
        None,
        None,
    )


# render_receipt ------------------------------------------------------------------------------


def test_el_recibo_trae_la_frase_fija_el_monto_el_socio_y_el_plan() -> None:
    assert RECEIPT_NOTICE == FRASE
    texto = texto_del_recibo(receipt_context(detalle(), GIMNASIO, "Nequi"))
    assert FRASE in texto
    for esperado in (
        "CrossFit Norte",
        "900123456-7",
        "Calle 10 # 5-20",
        "Medellín",
        "Lucía Gómez",
        "Mensual",
        "Nequi",
        "NQ-778",
        "$ 120.000",
        "21 oct 2026, 10:00 a. m.",
        str(PAGO),
    ):
        assert esperado in texto, esperado


def test_un_pago_vigente_no_dice_anulado() -> None:
    texto = texto_del_recibo(receipt_context(detalle(), GIMNASIO, "Nequi"))
    assert "ANULADO" not in texto


def test_un_pago_anulado_dice_anulado_con_el_motivo_y_la_fecha() -> None:
    ctx = receipt_context(
        detalle(voided=True, void_reason="Monto mal digitado", voided_at=ANULADO_EN),
        GIMNASIO,
        "Nequi",
    )
    texto = texto_del_recibo(ctx)
    assert "ANULADO" in texto
    assert "Monto mal digitado" in texto
    assert "22 oct 2026, 9:30 a. m." in texto
    assert FRASE in texto


def test_sin_referencia_el_recibo_no_tiene_linea_de_referencia() -> None:
    texto = texto_del_recibo(receipt_context(detalle(reference=None), GIMNASIO, "Efectivo"))
    assert "Referencia" not in texto
    assert "None" not in texto


def test_con_referencia_el_recibo_la_rotula() -> None:
    texto = texto_del_recibo(receipt_context(detalle(), GIMNASIO, "Nequi"))
    assert "Referencia" in texto


def test_el_recibo_resiste_texto_hostil_en_nombres_y_motivo() -> None:
    ctx = receipt_context(
        detalle(
            member_first_name="Ana (la \\ buena)",
            member_last_name="Pe‮ña \U0001f600",
            voided=True,
            void_reason="Error (doble) \\ cobro",
            voided_at=ANULADO_EN,
        ),
        GymView(name="Box (Norte) \\ 2"),
        "Nequi",
    )
    datos = render_receipt(ctx)
    texto = "\n".join(p.extract_text() for p in PdfReader(BytesIO(datos), strict=True).pages)
    assert "Ana (la \\ buena)" in texto
    assert "Pe?ña ?" in texto
    assert "Error (doble) \\ cobro" in texto
    assert "Box (Norte) \\ 2" in texto
    for clave in (b"/JavaScript", b"/OpenAction", b"/URI", b"/Launch", b"/Annots"):
        assert clave not in datos


def test_el_recibo_de_campos_al_maximo_cabe_en_una_pagina_y_en_el_tope() -> None:
    ctx = receipt_context(
        detalle(
            member_first_name="N" * 70,
            member_last_name="A" * 70,
            reference="R" * 90,
            plan_name="P" * 80,
            voided=True,
            void_reason="M" * 200,
            voided_at=ANULADO_EN,
        ),
        GymView(name="G" * 80, nit="123456789012345", address="D" * 120, city="C" * 60, phone="1"),
        "Nequi",
    )
    assert len(texto_del_recibo(ctx)) > 0
