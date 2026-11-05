"""`payments.service.receipt_pdf` con PostgreSQL real (S5-B11, US-137, S5-D40, S5-D65, Q5).

# Rojo B11

Hoy es 2026-10-21 (`reloj`). Datos a mano: la membresía "Mensual" de Lucía Gómez del 2026-10-01 al
2026-10-30; el gimnasio "Box (Norte) \\ 2" (paréntesis y barra a propósito); un pago de 60.000 en
efectivo con referencia `EF-001` pagado el 2026-10-10T15:00Z (10:00 a. m. en Bogotá) y otro de
40.000 por Nequi anulado con el motivo "Monto mal digitado".

- el PDF trae la frase fija, el id del pago, el socio, el plan, el medio (etiqueta de
  `payment_methods`), la referencia y el monto;
- NUNCA el documento, el teléfono, el correo ni el contacto de emergencia del socio, y no usa el bus
  de cripto: con el keyring descargado (sistema sellado) funciona y no escribe en `crypto_ops`;
- auditoría: exactamente UNA fila `download` por descarga (dos descargas, dos filas) sobre
  `payments.payments` con `record_id` = el pago, `subject_member_id` = el socio y `user_id` = quien
  descarga; ni `update` ni otra acción sobre el pago (los pagos son inmutables);
- un pago inexistente lanza `PaymentNotFound` y no audita.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import pytest
from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring, configure_keyring
from app.modules.payments import service
from app.modules.payments.exceptions import PaymentNotFound
from app.modules.settings import service as settings_service
from tests.factories.members import KNOWN, KNOWN_NORMALIZED, make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.factories.users import make_user
from tests.members._apoyo import operaciones
from tests.payments._apoyo import leer_auditoria_de_pagos

FRASE = "Comprobante interno de pago. No es factura electrónica."
GIMNASIO = "Box (Norte) \\ 2"
PAGADO = datetime(2026, 10, 10, 15, tzinfo=UTC)
MOTIVO = "Monto mal digitado"
TABLA = "payments.payments"


@dataclass(frozen=True)
class Datos:
    vigente: UUID
    anulado: UUID
    socio: UUID
    admin: UUID
    coach: UUID


@pytest.fixture
async def datos(session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock) -> Datos:
    plan = await make_plan(session, name="Mensual")
    socio = await make_member(session)
    membresia = await make_membership(
        session, socio, plan, status="active", start=date(2026, 10, 1), end=date(2026, 10, 30)
    )
    admin = await make_user(session, role="admin", email="mario.admin@test.apex")
    coach = await make_user(session, role="coach", email="laura.cajera@test.apex")
    with actor_scope(admin.id):
        await settings_service.update_section(
            session, "gym", {"name": GIMNASIO, "city": "Bogotá"}, 0, admin.id
        )
        await session.commit()
    vigente = await make_payment(
        session,
        membresia,
        amount=60_000,
        reference="EF-001",
        paid_at=PAGADO,
        registered_by=coach.id,
        created_at=PAGADO + timedelta(hours=1),
    )
    anulado = await make_payment(
        session,
        membresia,
        amount=40_000,
        method="nequi",
        paid_at=PAGADO + timedelta(days=2),
        registered_by=coach.id,
        voided=True,
        void_reason=MOTIVO,
        voided_by=admin.id,
        voided_at=PAGADO + timedelta(days=3),
    )
    return Datos(vigente.id, anulado.id, socio.id, admin.id, coach.id)


async def descargar(session: AsyncSession, quien: UUID, payment_id: UUID) -> bytes:
    """Una petición: `receipt_pdf` bajo el actor y commit."""
    with actor_scope(quien):
        salida = await service.receipt_pdf(session, payment_id, quien)
        await session.commit()
    return salida


def texto(pdf: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf), strict=True).pages)


async def descargas(session: AsyncSession, payment_id: UUID) -> list[dict[str, Any]]:
    filas = await session.execute(
        text(
            "SELECT action, table_name, record_id, subject_member_id, user_id, before, after "
            "FROM audit.audit_log WHERE action = 'download' AND record_id = :r ORDER BY seq"
        ),
        {"r": payment_id},
    )
    return [dict(f) for f in filas.mappings().all()]


# Contenido -----------------------------------------------------------------------------------


async def test_el_recibo_trae_frase_id_socio_plan_medio_referencia_y_monto(
    session: AsyncSession, datos: Datos
) -> None:
    pdf = await descargar(session, datos.coach, datos.vigente)
    cuerpo = texto(pdf)
    assert pdf.startswith(b"%PDF-")
    for esperado in (
        FRASE,
        str(datos.vigente),
        "Lucía Gómez",
        "Mensual",
        "Efectivo",
        "EF-001",
        "$ 60.000",
        "10 oct 2026, 10:00 a. m.",
        GIMNASIO,
        "Bogotá",
    ):
        assert esperado in cuerpo, esperado
    assert "ANULADO" not in cuerpo


async def test_el_recibo_de_un_anulado_dice_anulado_con_el_motivo(
    session: AsyncSession, datos: Datos
) -> None:
    cuerpo = texto(await descargar(session, datos.admin, datos.anulado))
    assert "ANULADO" in cuerpo
    assert MOTIVO in cuerpo
    assert "Nequi" in cuerpo
    assert "$ 40.000" in cuerpo
    assert FRASE in cuerpo


async def test_el_recibo_no_lleva_documento_telefono_correo_ni_contacto_de_emergencia(
    session: AsyncSession, datos: Datos
) -> None:
    pdf = await descargar(session, datos.admin, datos.vigente)
    cuerpo = texto(pdf)
    prohibidos = {*KNOWN_NORMALIZED, KNOWN["document"], "Correo.co", "correo.co"}
    for dato in prohibidos:
        assert dato not in cuerpo, dato
        assert dato.encode() not in pdf, dato


# Independencia del bus de cripto (N-16) -------------------------------------------------------


async def test_con_el_custodio_sellado_el_recibo_se_genera_y_no_toca_el_bus(
    session: AsyncSession, datos: Datos
) -> None:
    antes = len(await operaciones(session))
    configure_keyring(None)  # sistema sellado: ninguna DEK cargada
    pdf = await descargar(session, datos.coach, datos.vigente)
    assert FRASE in texto(pdf)
    assert len(await operaciones(session)) == antes


# Auditoría `download` --------------------------------------------------------------------------


async def test_una_descarga_deja_exactamente_una_fila_download(
    session: AsyncSession, datos: Datos
) -> None:
    await descargar(session, datos.coach, datos.vigente)
    filas = await descargas(session, datos.vigente)
    assert len(filas) == 1
    fila = filas[0]
    assert fila["table_name"] == TABLA
    assert fila["record_id"] == datos.vigente
    assert fila["subject_member_id"] == datos.socio
    assert fila["user_id"] == datos.coach
    assert fila["before"] is None
    resto = str(fila["after"])
    for dato in {*KNOWN_NORMALIZED, KNOWN["document"]}:
        assert dato not in resto, dato


async def test_dos_descargas_dejan_dos_filas_una_por_descarga(
    session: AsyncSession, datos: Datos
) -> None:
    await descargar(session, datos.coach, datos.vigente)
    await descargar(session, datos.admin, datos.vigente)
    filas = await descargas(session, datos.vigente)
    assert [f["user_id"] for f in filas] == [datos.coach, datos.admin]


async def test_descargar_no_modifica_el_pago_solo_agrega_download(
    session: AsyncSession, datos: Datos
) -> None:
    await descargar(session, datos.coach, datos.vigente)
    acciones = [f["action"] for f in await leer_auditoria_de_pagos(session, datos.vigente)]
    assert acciones == ["insert", "download"]


async def test_la_descarga_de_otro_pago_no_audita_este(session: AsyncSession, datos: Datos) -> None:
    await descargar(session, datos.coach, datos.anulado)
    assert await descargas(session, datos.vigente) == []
    assert len(await descargas(session, datos.anulado)) == 1


async def test_un_pago_inexistente_lanza_not_found_y_no_audita(
    session: AsyncSession, datos: Datos
) -> None:
    with pytest.raises(PaymentNotFound):
        await descargar(session, datos.coach, uuid4())
    cuenta = await session.scalar(
        text("SELECT count(*) FROM audit.audit_log WHERE action = 'download'")
    )
    assert cuenta == 0
