"""`payments.service.get` (S3-B8, US-099; D26, L-2, S3-D57, S3-D80).

Hoy es 2026-10-21 (`reloj`). Datos a mano: la membresía "Mensual" de Lucía Gómez del
2026-10-01 al 2026-10-30; la cajera `laura.cajera@test.apex` (coach) registra
- un pago vigente de 60.000 en efectivo con referencia `EF-001`, pagado el 2026-10-10T15:00Z y
  registrado una hora después;
- un pago de 40.000 por Nequi pagado el 2026-10-12T15:00Z (registrado una hora después) que
  `mario.admin@test.apex` anuló el 2026-10-13T15:00Z con el motivo "Monto mal digitado".

El detalle es `PaymentDetail` (claves exactas `CAMPOS_DETAIL`): la fila de la lista más
`voided_by`, `voided_by_name` (correo parcial `m•••@test.apex`, L-2), `voided_at` y
`created_at`. Inexistente: `PaymentNotFound` (404 `payment_not_found`). Una sentencia por
servicio vecino (`memberships`, `members`, `plans` y `auth` con los dos usuarios a la vez) y
ninguna operación del bus de cripto.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.modules.payments import service
from app.modules.payments.exceptions import PaymentNotFound
from app.modules.payments.schemas import PaymentDetail
from tests.conftest import ContadorDeConsultas
from tests.factories.members import KNOWN_NORMALIZED, make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.factories.users import make_user
from tests.members._apoyo import operaciones
from tests.payments._apoyo import CAMPOS_DETAIL

CORREO_CAJERA = "laura.cajera@test.apex"
CORREO_ADMIN = "mario.admin@test.apex"
MOTIVO = "Monto mal digitado"
PAGADO_VIGENTE = datetime(2026, 10, 10, 15, tzinfo=UTC)
PAGADO_ANULADO = datetime(2026, 10, 12, 15, tzinfo=UTC)
ANULADO_EN = datetime(2026, 10, 13, 15, tzinfo=UTC)


@dataclass(frozen=True)
class DosPagos:
    vigente: UUID
    anulado: UUID
    membresia: UUID
    socio: UUID
    cajera: UUID
    admin: UUID


@pytest.fixture
async def dos_pagos(session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock) -> DosPagos:
    plan = await make_plan(session, name="Mensual")
    socio = await make_member(session)
    membresia = await make_membership(
        session, socio, plan, status="active", start=date(2026, 10, 1), end=date(2026, 10, 30)
    )
    cajera = await make_user(session, role="coach", email=CORREO_CAJERA)
    admin = await make_user(session, role="admin", email=CORREO_ADMIN)
    vigente = await make_payment(
        session,
        membresia,
        amount=60_000,
        reference="EF-001",
        paid_at=PAGADO_VIGENTE,
        registered_by=cajera.id,
        created_at=PAGADO_VIGENTE + timedelta(hours=1),
    )
    anulado = await make_payment(
        session,
        membresia,
        amount=40_000,
        method="nequi",
        paid_at=PAGADO_ANULADO,
        registered_by=cajera.id,
        created_at=PAGADO_ANULADO + timedelta(hours=1),
        voided=True,
        void_reason=MOTIVO,
        voided_by=admin.id,
        voided_at=ANULADO_EN,
    )
    return DosPagos(
        vigente=vigente.id,
        anulado=anulado.id,
        membresia=membresia.id,
        socio=socio.id,
        cajera=cajera.id,
        admin=admin.id,
    )


async def detalle(session: AsyncSession, payment_id: UUID) -> PaymentDetail:
    """Una petición: `service.get` bajo un actor y el commit (vacía la bitácora `crypto_ops`)."""
    with actor_scope(SYSTEM_USER_ID):
        salida = await service.get(session, payment_id)
        await session.commit()
    return salida


async def test_el_detalle_de_un_pago_vigente(session: AsyncSession, dos_pagos: DosPagos) -> None:
    pago = await detalle(session, dos_pagos.vigente)
    assert set(pago.model_dump()) == CAMPOS_DETAIL
    assert (pago.id, pago.amount_cop, pago.method, pago.reference) == (
        dos_pagos.vigente,
        60_000,
        "cash",
        "EF-001",
    )
    assert (pago.paid_at, pago.created_at) == (
        PAGADO_VIGENTE,
        PAGADO_VIGENTE + timedelta(hours=1),
    )
    assert (pago.voided, pago.void_reason, pago.voided_by, pago.voided_by_name, pago.voided_at) == (
        False,
        None,
        None,
        None,
        None,
    )
    assert (pago.registered_by, pago.registered_by_name) == (dos_pagos.cajera, "l•••@test.apex")
    assert (pago.membership_id, pago.member_id) == (dos_pagos.membresia, dos_pagos.socio)
    assert (pago.member_first_name, pago.member_last_name, pago.plan_name) == (
        "Lucía",
        "Gómez",
        "Mensual",
    )
    assert (pago.membership_start_date, pago.membership_end_date) == (
        date(2026, 10, 1),
        date(2026, 10, 30),
    )
    assert pago.backdated is False


async def test_el_detalle_de_un_pago_anulado_trae_quien_y_cuando_con_correo_parcial(
    session: AsyncSession, dos_pagos: DosPagos
) -> None:
    pago = await detalle(session, dos_pagos.anulado)
    assert (pago.voided, pago.void_reason) == (True, MOTIVO)
    assert (pago.voided_by, pago.voided_by_name, pago.voided_at) == (
        dos_pagos.admin,
        "m•••@test.apex",
        ANULADO_EN,
    )
    assert (pago.registered_by_name, pago.method, pago.amount_cop) == (
        "l•••@test.apex",
        "nequi",
        40_000,
    )


async def test_un_pago_inexistente_da_404(session: AsyncSession, dos_pagos: DosPagos) -> None:
    with pytest.raises(PaymentNotFound) as error:
        await detalle(session, uuid4())
    assert (error.value.status, error.value.code) == (404, "payment_not_found")


async def test_el_detalle_no_trae_datos_cifrados_ni_correos_completos(
    session: AsyncSession, dos_pagos: DosPagos
) -> None:
    antes = len(await operaciones(session))
    texto = (await detalle(session, dos_pagos.anulado)).model_dump_json()
    for valor in (*KNOWN_NORMALIZED, "apx1.", CORREO_CAJERA, CORREO_ADMIN, "mario.admin"):
        assert valor not in texto, valor
    assert len(await operaciones(session)) == antes  # ni `decrypt` ni índices


async def test_una_sentencia_por_servicio_vecino(
    session: AsyncSession, dos_pagos: DosPagos, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo():
        await detalle(session, dos_pagos.anulado)
    assert contador_de_consultas.de("memberships.memberships") == 1
    assert contador_de_consultas.de("members.members") == 1
    assert contador_de_consultas.de("plans.plans") == 1
    assert contador_de_consultas.de("auth.users") == 1  # quien registró y quien anuló a la vez
