"""Recibo de pago en PDF (S5-D40, S5-D241, US-137). Privado de `payments`.

Funciones puras, sin base de datos: `format_cop`, `format_bogota`, `receipt_context` (arma
cadenas ya formateadas; nombre a 60, referencia a 40) y `render_receipt` (solo dibuja con
`core.pdf`). Nunca recibe documento, teléfono ni correo del socio: no usa el bus de cripto.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Final
from uuid import UUID

from app.core.pdf import PdfLine, render_text_pdf
from app.modules.payments.schemas import PaymentDetail
from app.modules.settings.schemas import GymView

NAME_MAX = 60
REFERENCE_MAX = 40
RECEIPT_NOTICE = "Comprobante interno de pago. No es factura electrónica."

_BOGOTA: Final = timezone(timedelta(hours=-5))
_MONTHS: Final = "ene feb mar abr may jun jul ago sep oct nov dic".split()
_LEFT_MM: Final = 20.0
_TOP_MM: Final = 270.0
_TEXT_WIDTH_PT: Final = 482.0
_COURIER_ADVANCE: Final = 0.6
_REASON_LINES: Final = 3


@dataclass(frozen=True, slots=True)
class ReceiptContext:
    gym_name: str
    gym_nit: str | None
    gym_address: str | None
    gym_city: str | None
    gym_phone: str | None
    payment_id: UUID
    member_name: str
    plan_name: str
    period_start: date
    period_end: date
    method_label: str
    reference: str | None
    amount_text: str
    paid_at_text: str
    voided: bool
    void_reason: str | None
    voided_at_text: str | None


def format_cop(amount: int) -> str:
    """`120000` es `$ 120.000` (punto de miles, sin decimales)."""
    return "$ " + f"{amount:,}".replace(",", ".")


def format_bogota(moment: datetime) -> str:
    """`21 oct 2026, 10:00 a. m.` en hora de Bogotá (UTC-5, sin horario de verano)."""
    local = moment.astimezone(_BOGOTA)
    hora = local.hour % 12 or 12
    sufijo = "a. m." if local.hour < 12 else "p. m."
    return (
        f"{local.day} {_MONTHS[local.month - 1]} {local.year}, {hora}:{local.minute:02d} {sufijo}"
    )


def _format_date(day: date) -> str:
    return f"{day.day} {_MONTHS[day.month - 1]} {day.year}"


def receipt_context(detail: PaymentDetail, gym: GymView, method_label: str) -> ReceiptContext:
    nombre = f"{detail.member_first_name} {detail.member_last_name}"[:NAME_MAX]
    referencia = (detail.reference or "")[:REFERENCE_MAX] or None
    anulado_en = detail.voided_at if detail.voided and detail.voided_at else None
    return ReceiptContext(
        gym_name=gym.name,
        gym_nit=gym.nit,
        gym_address=gym.address,
        gym_city=gym.city,
        gym_phone=gym.phone,
        payment_id=detail.id,
        member_name=nombre,
        plan_name=detail.plan_name,
        period_start=detail.membership_start_date,
        period_end=detail.membership_end_date,
        method_label=method_label,
        reference=referencia,
        amount_text=format_cop(detail.amount_cop),
        paid_at_text=format_bogota(detail.paid_at),
        voided=detail.voided,
        void_reason=detail.void_reason if detail.voided else None,
        voided_at_text=None if anulado_en is None else format_bogota(anulado_en),
    )


def _fit(text: str, size: float) -> str:
    """Corta la línea al ancho útil de la página (Courier: 0,6 · tamaño por carácter)."""
    return text[: int(_TEXT_WIDTH_PT / (_COURIER_ADVANCE * size))]


def _gym_lines(ctx: ReceiptContext) -> list[tuple[str, float, bool]]:
    filas: list[tuple[str, float, bool]] = [(ctx.gym_name, 14, True)]
    if ctx.gym_nit:
        filas.append((f"NIT {ctx.gym_nit}", 10, False))
    lugar = ", ".join(p for p in (ctx.gym_address, ctx.gym_city) if p)
    if lugar:
        filas.append((lugar, 10, False))
    if ctx.gym_phone:
        filas.append((f"Tel. {ctx.gym_phone}", 10, False))
    return filas


def _body_lines(ctx: ReceiptContext) -> list[tuple[str, float, bool]]:
    filas: list[tuple[str, float, bool]] = [
        ("", 10, False),
        ("RECIBO DE PAGO", 12, True),
        (f"Pago: {ctx.payment_id}", 10, False),
        (f"Fecha: {ctx.paid_at_text}", 10, False),
        (f"Socio: {ctx.member_name}", 10, False),
        (f"Plan: {ctx.plan_name}", 10, False),
        (f"Vigencia: {_format_date(ctx.period_start)} a {_format_date(ctx.period_end)}", 10, False),
        (f"Medio: {ctx.method_label}", 10, False),
    ]
    if ctx.reference:
        filas.append((f"Referencia: {ctx.reference}", 10, False))
    filas.append((f"Monto: {ctx.amount_text}", 12, True))
    return filas


def _void_lines(ctx: ReceiptContext) -> list[tuple[str, float, bool]]:
    if not ctx.voided:
        return []
    filas: list[tuple[str, float, bool]] = [("", 10, False), ("ANULADO", 12, True)]
    if ctx.voided_at_text:
        filas.append((f"Anulado el: {ctx.voided_at_text}", 10, False))
    ancho = int(_TEXT_WIDTH_PT / (_COURIER_ADVANCE * 10)) - len("Motivo: ")
    motivo = textwrap.wrap(ctx.void_reason or "", width=ancho)[:_REASON_LINES]
    for numero, parte in enumerate(motivo):
        filas.append((("Motivo: " if numero == 0 else "        ") + parte, 10, False))
    return filas


def render_receipt(ctx: ReceiptContext) -> bytes:
    """Una página A4 con los datos del gimnasio, del pago y la frase fija."""
    filas = [*_gym_lines(ctx), *_body_lines(ctx), *_void_lines(ctx)]
    filas += [("", 10, False), (RECEIPT_NOTICE, 9, False)]
    lineas: list[PdfLine] = []
    y = _TOP_MM
    for texto, tamano, negrita in filas:
        lineas.append(PdfLine(_fit(texto, tamano), _LEFT_MM, y, tamano, negrita))
        y -= tamano * 0.5
    return render_text_pdf(lineas, title="Recibo de pago")
