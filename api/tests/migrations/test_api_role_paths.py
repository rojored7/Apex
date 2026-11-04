"""Los caminos de escritura del api corren como `apex_api` sobre `apex_roles` (S5-W0-3; S5-D202).

Con el `INSERT` de `payments.payments` por columna (sin `void_reason`, `voided_by` ni
`voided_at`), el ORM no puede nombrar esas columnas al registrar un pago. Estas pruebas ejecutan
`payments.service.register` y `payments.service.void` (las funciones reales de `POST /payments`
y de la anulación) con una sesión conectada como `apex_api`.
Las filas se siembran como propietario; `apex_roles` se descarta al terminar la sesión.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.memberships import service as _memberships_service  # registra el gate  # noqa: F401
from app.modules.payments import service as payments_service
from tests.migrations.conftest import RolesDb, url_por_rol
from tests.migrations.test_db_grants import propietario

SYSTEM = str(SYSTEM_USER_ID)


def _como_api[T](apex: RolesDb, trabajo: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async def correr() -> T:
        motor: AsyncEngine = create_async_engine(url_por_rol(apex, "apex_api"))
        try:
            fabrica = async_sessionmaker(motor, expire_on_commit=False)
            with actor_scope(SYSTEM_USER_ID):
                async with fabrica() as sesion:
                    resultado = await trabajo(sesion)
                    await sesion.commit()
                    return resultado
        finally:
            await motor.dispose()

    return asyncio.run(correr())


@pytest.fixture
def membresia_activa(apex_roles: RolesDb) -> UUID:
    """Un socio, un plan y una membresía `active` de 100000 COP sembrados como propietario."""
    socio, plan, membresia = str(uuid4()), str(uuid4()), str(uuid4())
    hoy = date.today()
    propietario(
        apex_roles,
        "INSERT INTO members.members (id, created_by, first_name, last_name, document, "  # noqa: S608
        "document_idx, phone, phone_idx, email, email_idx) "
        f"VALUES ('{socio}', '{SYSTEM}', 'Ana', 'Api', "
        f"'apx1.doc', 'idx-{socio}', 'apx1.fono', 'pidx-{socio}', 'apx1.correo', 'eidx-{socio}')",
        "INSERT INTO plans.plans (id, created_by, name, price_cop, kind, duration_days) "  # noqa: S608
        f"VALUES ('{plan}', '{SYSTEM}', 'Plan {plan}', 100000, 'days', 30)",
        "INSERT INTO memberships.memberships (id, created_by, member_id, plan_id, "  # noqa: S608
        "agreed_price_cop, start_date, end_date, status) "
        f"VALUES ('{membresia}', '{SYSTEM}', '{socio}', '{plan}', 100000, "
        f"'{hoy}', '{hoy + timedelta(days=30)}', 'active')",
    )
    return UUID(membresia)


def test_registrar_un_pago_como_apex_api_usa_el_insert_por_columna(
    apex_roles: RolesDb, membresia_activa: UUID
) -> None:
    async def trabajo(sesion: AsyncSession) -> UUID:
        pago = await payments_service.register(
            sesion,
            membership_id=membresia_activa,
            amount_cop=40000,
            method="cash",
            role="admin",
        )
        return pago.id

    pago_id = _como_api(apex_roles, trabajo)

    async def leer(sesion: AsyncSession) -> tuple[bool, object, object, object]:
        fila = (
            await sesion.execute(
                text(
                    "SELECT voided, void_reason, voided_by, voided_at "
                    "FROM payments.payments WHERE id = :i"
                ),
                {"i": pago_id},
            )
        ).one()
        return fila.voided, fila.void_reason, fila.voided_by, fila.voided_at

    assert _como_api(apex_roles, leer) == (False, None, None, None)


def test_anular_un_pago_como_apex_api_usa_el_update_por_columna(
    apex_roles: RolesDb, membresia_activa: UUID
) -> None:
    async def registrar(sesion: AsyncSession) -> UUID:
        pago = await payments_service.register(
            sesion,
            membership_id=membresia_activa,
            amount_cop=30000,
            method="cash",
            role="admin",
        )
        return pago.id

    pago_id = _como_api(apex_roles, registrar)

    async def anular(sesion: AsyncSession) -> bool:
        anulado = await payments_service.void(
            sesion, payment_id=pago_id, reason="error de digitación"
        )
        return anulado.voided

    assert _como_api(apex_roles, anular) is True
