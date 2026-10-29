"""RN-04: cambiar el plan no cambia lo ya vendido (S4A-B7; US-080; S4A-D22, S4A-D60).

`plans.service.update` y `memberships.service.sell` reales sobre PostgreSQL:
- se vende "Mensual" ($ 120.000, 30 días) el 2026-10-21: `agreed_price_cop = 120.000` y
  `end_date = 2026-11-20` (`compute_end_date`: inicio más `duration_days`, RN-05);
- se sube el plan a $ 135.000 (y se alarga a 45 días): la membresía vendida sigue con 120.000, el
  mismo `end_date` y el mismo `classes_total` (en una tiquetera de 12 clases que pasa a 20 también);
- un `UPDATE` crudo del precio pactado lo rechaza `memberships.guard_identity` (23000,
  `memberships_identity`);
- una venta posterior cobra el precio vigente, $ 135.000, con la duración nueva (S4A-D60: sin
  `expected_price_cop`, el servidor cobra el precio vigente al vender).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.core.db import sqlstate_of, violated_constraint
from app.modules.memberships import service as memberships_service  # noqa: F401
from app.modules.plans import service as plans_service
from tests.conftest import CrearUsuario, UsuarioPrueba
from tests.factories.members import make_members
from tests.factories.plans import make_plan
from tests.memberships._apoyo import leer_membresia, vender
from tests.plans._apoyo import en_unidad, parche

IDENTIDAD = "memberships_identity"


@dataclass(frozen=True)
class Caso:
    plan: dict[str, Any]
    cambio: dict[str, Any]
    fin_vendida: date
    fin_nueva: date
    clases_vendida: int | None
    clases_nueva: int | None


CASOS = {
    "mensual": Caso(
        plan={"name": "Mensual", "price_cop": 120_000, "duration_days": 30},
        cambio={"price_cop": 135_000, "duration_days": 45},
        fin_vendida=date(2026, 11, 20),
        fin_nueva=date(2026, 12, 5),
        clases_vendida=None,
        clases_nueva=None,
    ),
    "tiquetera": Caso(
        plan={
            "name": "Tiquetera 12",
            "price_cop": 120_000,
            "kind": "classes",
            "duration_days": 60,
            "class_count": 12,
        },
        cambio={"price_cop": 135_000, "duration_days": 90, "class_count": 20},
        fin_vendida=date(2026, 12, 20),
        fin_nueva=date(2027, 1, 19),
        clases_vendida=12,
        clases_nueva=20,
    ),
}


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


@pytest.mark.parametrize("nombre", sorted(CASOS))
async def test_subir_el_plan_no_cambia_lo_vendido_y_la_venta_nueva_cobra_el_precio_vigente(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    bus_listo: Keyring,
    nombre: str,
) -> None:
    caso = CASOS[nombre]
    plan = await make_plan(session, **caso.plan)
    primero, segundo = await make_members(session, 2)

    vendida = await vender(session, admin.id, member_id=primero.id, plan_id=plan.id)
    assert vendida.agreed_price_cop == 120_000
    assert (vendida.start_date, vendida.end_date) == (date(2026, 10, 21), caso.fin_vendida)
    assert vendida.classes_total == caso.clases_vendida
    antes = await leer_membresia(session, vendida.id)

    actualizado = await en_unidad(
        session, admin.id, lambda: plans_service.update(session, plan.id, parche(**caso.cambio))
    )
    assert actualizado.price_cop == 135_000

    despues = await leer_membresia(session, vendida.id)
    assert despues is not None and antes is not None
    claves = ("agreed_price_cop", "start_date", "end_date", "classes_total", "classes_remaining")
    assert {k: despues[k] for k in claves} == {k: antes[k] for k in claves}
    assert despues["agreed_price_cop"] == 120_000 and despues["end_date"] == caso.fin_vendida

    nueva = await vender(session, admin.id, member_id=segundo.id, plan_id=plan.id)
    assert nueva.agreed_price_cop == 135_000
    assert nueva.end_date == caso.fin_nueva
    assert nueva.classes_total == caso.clases_nueva


@pytest.mark.parametrize(
    "cambio",
    ["agreed_price_cop = 135000", "classes_total = 20", "start_date = start_date + 1"],
    ids=["precio", "clases", "inicio"],
)
async def test_guard_identity_rechaza_cambiar_lo_pactado_por_sql_crudo(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    bus_listo: Keyring,
    cambio: str,
) -> None:
    plan = await make_plan(session, **CASOS["tiquetera"].plan)
    (socio,) = await make_members(session, 1)
    vendida = await vender(session, admin.id, member_id=socio.id, plan_id=plan.id)
    sentencia = text(f"UPDATE memberships.memberships SET {cambio} WHERE id = :id")  # noqa: S608
    with pytest.raises(IntegrityError) as error:
        async with session.begin_nested():
            await session.execute(sentencia, {"id": vendida.id})
    assert sqlstate_of(error.value) == "23000"
    assert violated_constraint(error.value) == IDENTIDAD
    fila = await leer_membresia(session, vendida.id)
    assert fila is not None
    assert (fila["agreed_price_cop"], fila["classes_total"]) == (120_000, 12)
