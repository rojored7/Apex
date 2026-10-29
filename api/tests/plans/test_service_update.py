"""`plans.service.update` con PostgreSQL real (S4A-B7; US-080; S4A-D22, S4A-D25, S4A-D60).

- Cambio de precio: una fila `update` en `audit.audit_log` con `price_cop` antes (120.000) y
  después (135.000), con el actor; `PlanUpdated(plan_id, changed_fields)` con nombres de campo en
  orden alfabético, nunca valores.
- Sin cambios efectivos (cuerpo vacío o los mismos valores): 200 igual, sin `flush`, sin fila de
  auditoría y sin evento.
- `PlanNotFound` si no existe o está dado de baja; un plan inactivo sí se edita (sigue inactivo).
- Renombrar respeta `uq_plans_name_alive`: un nombre de otro plan vivo (sin distinguir mayúsculas
  ni espacios) da `PlanNameDuplicated` con su `existing_id` y no cambia nada; el propio nombre con
  otras mayúsculas no es repetido; el de un plan dado de baja se puede usar.
- `merge_plan` y `validate_plan` corren en el service: pasar a `classes` sin clases da 422 con
  `field` y no cambia nada.
- `SELECT ... FOR UPDATE` del plan (serializa dos PATCH).
- `active_members_count` en la respuesta (S4A-D25).
- Carreras con `dos_sesiones`: dos renombres de dos planes al mismo nombre (uno gana, el otro 409;
  nunca 55P03 ni 40P01) y dos PATCH del mismo plan (se serializan; gana el último).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.db import DatabaseBusy, sqlstate_of
from app.core.errors import DomainError
from app.modules.plans import service
from app.modules.plans.exceptions import (
    PlanNameDuplicated,
    PlanNotFound,
    PlanValidationError,
)
from app.modules.plans.schemas import PlanOut, PlanPatch
from app.modules.plans.service import PlanUpdated
from tests.auth._cuentas import filas_auditoria
from tests.conftest import T0, CapturarEventos, ContadorDeConsultas, CrearUsuario, UsuarioPrueba
from tests.factories.plans import make_plan
from tests.plans._apoyo import CAMPOS_PLAN, con_membresias, en_unidad, fila_plan, parche

SQLSTATES_PROHIBIDOS = frozenset({"55P03", "40P01"})
ACTOR = UUID("0000000a-0000-4000-8000-00000000b007")
"""Actor de las carreras: `dos_sesiones` no se combina con `session` (ni con `usuario_real`)."""


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


def editar(session: AsyncSession, plan_id: UUID, patch: PlanPatch) -> Callable[[], Any]:
    return lambda: service.update(session, plan_id, patch)


async def updates(session: AsyncSession, plan_id: UUID) -> list[dict[str, Any]]:
    return [
        f for f in await filas_auditoria(session, "plans.plans", plan_id) if f["action"] == "update"
    ]


# Cambios ------------------------------------------------------------------------------------


async def test_cambiar_el_precio_responde_el_plan_y_lo_guarda(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    plan = await make_plan(session)
    salida = await en_unidad(session, admin.id, editar(session, plan.id, parche(price_cop=135_000)))
    assert isinstance(salida, PlanOut)
    assert set(salida.model_dump()) == CAMPOS_PLAN
    assert (salida.id, salida.name, salida.price_cop) == (plan.id, "Mensual", 135_000)
    assert (salida.kind, salida.duration_days, salida.class_count) == ("days", 30, None)
    assert salida.is_active is True
    fila = await fila_plan(session, plan.id)
    assert fila["price_cop"] == 135_000 and fila["deleted_at"] is None


async def test_el_cambio_de_precio_deja_una_fila_update_con_antes_y_despues(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    plan = await make_plan(session)
    await en_unidad(session, admin.id, editar(session, plan.id, parche(price_cop=135_000)))
    (fila,) = await updates(session, plan.id)
    assert fila["user_id"] == admin.id
    assert fila["before"] == {"price_cop": 120_000}
    assert fila["after"] == {"price_cop": 135_000}


async def test_emite_plan_updated_con_los_nombres_de_campo_en_orden(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    recibidos = capturar_eventos(PlanUpdated)
    plan = await make_plan(session)
    cambios = parche(price_cop=135_000, name="Mensual Plus", duration_days=31)
    await en_unidad(session, admin.id, editar(session, plan.id, cambios))
    assert recibidos == [
        PlanUpdated(
            plan_id=plan.id,
            changed_fields=("duration_days", "name", "price_cop"),
            occurred_at=T0,
        )
    ]


async def test_pasar_a_clases_cambia_kind_y_class_count(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    plan = await make_plan(session)
    cambios = parche(kind="classes", class_count=12)
    salida = await en_unidad(session, admin.id, editar(session, plan.id, cambios))
    assert (salida.kind, salida.class_count) == ("classes", 12)
    fila = await fila_plan(session, plan.id)
    assert (fila["kind"], fila["class_count"]) == ("classes", 12)


async def test_un_plan_inactivo_se_edita_y_sigue_inactivo(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    plan = await make_plan(session, is_active=False)
    salida = await en_unidad(session, admin.id, editar(session, plan.id, parche(price_cop=90_000)))
    assert (salida.price_cop, salida.is_active) == (90_000, False)


async def test_renombrar_con_otras_mayusculas_del_propio_nombre_no_es_repetido(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    plan = await make_plan(session, name="Mensual")
    salida = await en_unidad(session, admin.id, editar(session, plan.id, parche(name="MENSUAL")))
    assert salida.name == "MENSUAL"


async def test_puede_usar_el_nombre_de_un_plan_dado_de_baja(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    await make_plan(session, name="Anual", deleted_at=T0 - timedelta(days=1))
    plan = await make_plan(session, name="Mensual")
    salida = await en_unidad(session, admin.id, editar(session, plan.id, parche(name="Anual")))
    assert salida.name == "Anual"


# Sin cambios --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cambios",
    [{}, {"price_cop": 120_000}, {"name": "Mensual", "duration_days": 30}, {"class_count": None}],
    ids=["vacio", "mismo-precio", "mismos-valores", "class-count-null-en-days"],
)
async def test_sin_cambios_efectivos_no_audita_ni_emite(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
    cambios: dict[str, Any],
) -> None:
    recibidos = capturar_eventos(PlanUpdated)
    plan = await make_plan(session)
    antes = await fila_plan(session, plan.id)
    salida = await en_unidad(session, admin.id, editar(session, plan.id, parche(**cambios)))
    assert (salida.name, salida.price_cop) == ("Mensual", 120_000)
    assert await updates(session, plan.id) == []
    assert recibidos == []
    assert await fila_plan(session, plan.id) == antes


# Errores ------------------------------------------------------------------------------------


async def test_un_plan_dado_de_baja_da_plan_not_found(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    plan = await make_plan(session, deleted_at=T0 - timedelta(days=1))
    plan_id = plan.id
    with actor_scope(admin.id), pytest.raises(PlanNotFound):
        await service.update(session, plan.id, parche(price_cop=1))
    await session.rollback()
    assert (await fila_plan(session, plan_id))["price_cop"] == 120_000


async def test_un_plan_inexistente_da_plan_not_found(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    with actor_scope(admin.id), pytest.raises(PlanNotFound) as error:
        await service.update(session, uuid4(), parche(price_cop=1))
    assert (error.value.status, error.value.code) == (404, "plan_not_found")


@pytest.mark.parametrize("nombre", ["Trimestral", "  trimestral ", "TRIMESTRAL"])
async def test_un_nombre_repetido_da_plan_name_duplicated_con_existing_id(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock, nombre: str
) -> None:
    otro = await make_plan(session, name="Trimestral", duration_days=90)
    otro_id = otro.id
    plan = await make_plan(session, name="Mensual")
    plan_id = plan.id
    with actor_scope(admin.id), pytest.raises(PlanNameDuplicated) as error:
        await service.update(session, plan.id, parche(name=nombre))
    await session.rollback()
    assert (error.value.status, error.value.code) == (409, "plan_name_duplicated")
    assert error.value.field == "name" and error.value.existing_id == otro_id
    assert (await fila_plan(session, plan_id))["name"] == "Mensual"
    assert await updates(session, plan_id) == []


async def test_pasar_a_clases_sin_clases_da_422_y_no_cambia_nada(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    plan = await make_plan(session)
    plan_id = plan.id
    with actor_scope(admin.id), pytest.raises(PlanValidationError) as error:
        await service.update(session, plan.id, parche(kind="classes"))
    await session.rollback()
    assert error.value.field == "class_count"
    assert (await fila_plan(session, plan_id))["kind"] == "days"


# Candado y conteo ---------------------------------------------------------------------------


async def test_toma_el_plan_con_for_update(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    plan = await make_plan(session)
    with contador_de_consultas.midiendo() as medido:
        await en_unidad(session, admin.id, editar(session, plan.id, parche(price_cop=130_000)))
    candados = [
        sql
        for sql in medido.sentencias
        if "plans.plans" in sql and "FOR UPDATE" in sql.upper() and "FOR SHARE" not in sql.upper()
    ]
    assert candados, medido.sentencias


async def test_la_respuesta_lleva_active_members_count(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    await con_membresias(session, plan, ["active", "pending_payment", "expired", "cancelled"])
    salida = await en_unidad(session, admin.id, editar(session, plan.id, parche(price_cop=1_000)))
    assert salida.active_members_count == 2


# Carreras (dos_sesiones; sin `session`, que retiene el candado de la cadena) ---------------


async def _correr(sesion: AsyncSession, actor: UUID, plan_id: UUID, patch: PlanPatch) -> object:
    with actor_scope(actor):
        try:
            await sesion.execute(text("SET LOCAL lock_timeout = '2s'"))
            salida = await service.update(sesion, plan_id, patch)
            await sesion.commit()
        except (DomainError, DBAPIError) as error:
            await sesion.rollback()
            return error
    return salida


def _prohibidos(resultados: list[object]) -> list[object]:
    return [
        r
        for r in resultados
        if isinstance(r, DatabaseBusy)
        or (isinstance(r, DBAPIError) and sqlstate_of(r) in SQLSTATES_PROHIBIDOS)
    ]


async def test_dos_renombres_al_mismo_nombre_uno_gana_y_el_otro_da_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession], reloj: FrozenClock
) -> None:
    primera, segunda = dos_sesiones
    a = await make_plan(primera, name="Plan A")
    b = await make_plan(primera, name="Plan B")
    resultados = list(
        await asyncio.gather(
            _correr(primera, ACTOR, a.id, parche(name="Nuevo")),
            _correr(segunda, ACTOR, b.id, parche(name="Nuevo")),
            return_exceptions=True,
        )
    )
    assert _prohibidos(resultados) == [], resultados
    ganadores = [r for r in resultados if isinstance(r, PlanOut)]
    perdedores = [r for r in resultados if isinstance(r, PlanNameDuplicated)]
    assert len(ganadores) == 1 and len(perdedores) == 1, resultados
    assert perdedores[0].existing_id == ganadores[0].id
    vivos = await primera.scalar(
        text("SELECT count(*) FROM plans.plans WHERE name = 'Nuevo' AND deleted_at IS NULL")
    )
    assert vivos == 1


async def test_dos_patch_del_mismo_plan_se_serializan(
    dos_sesiones: tuple[AsyncSession, AsyncSession], reloj: FrozenClock
) -> None:
    primera, segunda = dos_sesiones
    plan = await make_plan(primera)
    resultados = list(
        await asyncio.gather(
            _correr(primera, ACTOR, plan.id, parche(price_cop=130_000)),
            _correr(segunda, ACTOR, plan.id, parche(price_cop=140_000)),
            return_exceptions=True,
        )
    )
    assert _prohibidos(resultados) == [], resultados
    assert all(isinstance(r, PlanOut) for r in resultados), resultados
    filas = await updates(primera, plan.id)
    assert len(filas) == 2
    final = await primera.scalar(
        text("SELECT price_cop FROM plans.plans WHERE id = :id"), {"id": plan.id}
    )
    assert final == filas[-1]["after"]["price_cop"]
    assert filas[1]["before"]["price_cop"] == filas[0]["after"]["price_cop"]
