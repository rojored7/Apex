"""`plans.service.create` con PostgreSQL real (S2-B9; US-078; DECISIÓN 32, S2-D32; blueprint B9).

- Alta de "Mensual" (`days`, 30 días, $ 120.000) y de "Tiquetera 12" (`classes`, 12 clases):
  `PlanOut` con `price_cop` entero, `is_active=True` y `created_at`/`updated_at` leídos de la
  base tras el `flush` (`refresh` de las columnas de servidor); `created_by` es el actor.
- Una fila `insert` en `audit.audit_log` con `table_name = 'plans.plans'` y el actor.
- `PlanCreated(plan_id)` en la misma transacción; si un handler falla, no queda ni el plan ni
  su auditoría.
- El nombre se recorta. Un nombre repetido entre los vivos, sin distinguir mayúsculas ni
  espacios ("mensual", "  MENSUAL  "), da `PlanNameDuplicated` (409, `plan_name_duplicated`,
  `field="name"`, `existing_id`) y no crea nada; el de un plan dado de baja se reutiliza.
- Carrera: dos altas del mismo nombre a la vez (`dos_sesiones`) pasan el pre-chequeo;
  `uq_plans_name_alive` decide dentro de `begin_nested()` y la perdedora recibe el 409.
- `validate_plan` corre en el service: `days` con clases o `classes` sin clases da 422 con
  `field` y no crea nada.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.events import DomainEvent
from app.modules.plans import service
from app.modules.plans.exceptions import PlanNameDuplicated, PlanValidationError
from app.modules.plans.schemas import PlanCreate, PlanOut
from app.modules.plans.service import PlanCreated
from tests.auth._cuentas import filas_auditoria
from tests.conftest import T0, CapturarEventos, CrearUsuario, UsuarioPrueba
from tests.factories.plans import make_plan
from tests.plans._apoyo import (
    CAMPOS_PLAN,
    crear,
    cuantos_planes,
    entrada,
    fila_plan,
    tiquetera,
)


class HandlerRoto(Exception):
    """Falla de un suscriptor de `PlanCreated`. No hereda de `RuntimeError`: `NotImplementedError`
    sí, y la prueba pasaría sobre los stubs."""


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


# Alta ------------------------------------------------------------------------------------


async def test_crea_mensual_con_dias_y_responde_el_contrato(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    salida = await crear(session, admin.id, entrada())
    assert isinstance(salida, PlanOut)
    assert set(salida.model_dump()) == CAMPOS_PLAN
    assert salida.name == "Mensual"
    assert salida.price_cop == 120_000 and type(salida.price_cop) is int
    assert (salida.kind, salida.duration_days, salida.class_count) == ("days", 30, None)
    assert salida.is_active is True
    fila = await fila_plan(session, salida.id)
    assert fila["name"] == "Mensual" and fila["price_cop"] == 120_000
    assert fila["kind"] == "days" and fila["class_count"] is None
    assert fila["is_active"] is True and fila["deleted_at"] is None
    assert fila["created_by"] == admin.id


async def test_crea_tiquetera_12_con_clases(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    salida = await crear(session, admin.id, PlanCreate.model_validate(tiquetera()))
    assert (salida.name, salida.kind, salida.class_count) == ("Tiquetera 12", "classes", 12)
    assert (salida.duration_days, salida.price_cop) == (60, 150_000)
    fila = await fila_plan(session, salida.id)
    assert fila["kind"] == "classes" and fila["class_count"] == 12


async def test_created_at_y_updated_at_salen_de_la_base(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    """Columnas de servidor (`now()`): el service las refresca tras el `flush` (sin
    `MissingGreenlet` ni valores inventados en Python)."""
    salida = await crear(session, admin.id, entrada())
    fila = await fila_plan(session, salida.id)
    assert salida.created_at == fila["created_at"]
    assert salida.updated_at == fila["updated_at"]
    assert salida.created_at.tzinfo is not None


async def test_el_nombre_se_recorta(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    """`PlanCreate` ya recorta por HTTP; el service recorta también lo que llega sin validar."""
    data = entrada().model_copy(update={"name": "  Trimestral  "})
    salida = await crear(session, admin.id, data)
    assert salida.name == "Trimestral"
    assert (await fila_plan(session, salida.id))["name"] == "Trimestral"


async def test_deja_una_fila_insert_de_auditoria_con_el_actor(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    salida = await crear(session, admin.id, entrada())
    filas = await filas_auditoria(session, "plans.plans", salida.id)
    assert [(f["action"], f["user_id"], f["table_name"]) for f in filas] == [
        ("insert", admin.id, "plans.plans")
    ]
    despues = filas[0]["after"]
    assert despues["name"] == "Mensual" and despues["price_cop"] == 120_000
    assert despues["created_by"] == str(admin.id)


async def test_emite_plan_created_con_el_id_del_plan(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    recibidos = capturar_eventos(PlanCreated)
    salida = await crear(session, admin.id, entrada())
    assert recibidos == [PlanCreated(plan_id=salida.id, occurred_at=T0)]


async def test_si_un_handler_de_plan_created_falla_el_plan_no_queda(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    vistos: list[UUID] = []

    async def roto(evento: DomainEvent, sesion: AsyncSession) -> None:
        assert isinstance(evento, PlanCreated)
        vistos.append(evento.plan_id)
        raise HandlerRoto("falla a propósito")

    events.subscribe(PlanCreated, roto)  # `restaurar_bus` lo quita al salir
    with actor_scope(admin.id), pytest.raises(HandlerRoto):
        await service.create(session, entrada(name="Semestral"))
    await session.rollback()
    assert len(vistos) == 1
    assert await cuantos_planes(session, nombre="Semestral") == 0
    assert await filas_auditoria(session, "plans.plans", vistos[0]) == []


# Nombre único sin distinguir mayúsculas (DECISIÓN 32) ------------------------------------


@pytest.mark.parametrize("repetido", ["Mensual", "mensual", "  MENSUAL  ", "MeNsUaL"])
async def test_un_nombre_repetido_entre_vivos_da_409_con_existing_id_y_no_crea_nada(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock, repetido: str
) -> None:
    primero = await crear(session, admin.id, entrada())
    data = entrada().model_copy(update={"name": repetido, "price_cop": 99_000})
    with actor_scope(admin.id), pytest.raises(PlanNameDuplicated) as error:
        await service.create(session, data)
    await session.rollback()
    assert error.value.status == 409
    assert error.value.code == "plan_name_duplicated"
    assert error.value.field == "name"
    assert error.value.existing_id == primero.id
    assert error.value.message == "Ya existe un plan con este nombre"
    assert await cuantos_planes(session, nombre="mensual") == 1


async def test_el_nombre_de_un_plan_dado_de_baja_se_puede_reutilizar(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    baja = await make_plan(session, name="Mensual", deleted_at=T0)
    nuevo = await crear(session, admin.id, entrada(name="mensual"))
    assert nuevo.id != baja.id and nuevo.name == "mensual"
    assert await cuantos_planes(session, nombre="Mensual") == 2


async def test_carrera_de_dos_altas_con_el_mismo_nombre_una_gana_y_la_otra_da_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession], reloj: FrozenClock
) -> None:
    """Ambas pasan el pre-chequeo; `uq_plans_name_alive` decide dentro de un `begin_nested()` y el
    `IntegrityError` se traduce a `PlanNameDuplicated`."""
    primera, segunda = dos_sesiones

    async def alta(sesion: AsyncSession, nombre: str) -> Any:
        try:
            with actor_scope(SYSTEM_USER_ID):
                salida = await service.create(sesion, entrada(name=nombre))
                await sesion.commit()
            return salida
        except PlanNameDuplicated as error:
            await sesion.rollback()
            return error

    resultados = await asyncio.gather(
        alta(primera, "Carrera"), alta(segunda, "carrera"), return_exceptions=True
    )
    creados = [r for r in resultados if isinstance(r, PlanOut)]
    duplicados = [r for r in resultados if isinstance(r, PlanNameDuplicated)]
    assert len(creados) == 1 and len(duplicados) == 1, resultados
    assert duplicados[0].existing_id in (None, creados[0].id)
    assert duplicados[0].field == "name" and duplicados[0].status == 409


# Reglas de tipo en el service -------------------------------------------------------------


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"kind": "days", "class_count": 5}, "class_count"),
        ({"kind": "classes", "class_count": None}, "class_count"),
    ],
    ids=["days-con-clases", "classes-sin-clases"],
)
async def test_una_combinacion_invalida_da_422_con_field_y_no_crea_nada(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    cambios: dict[str, Any],
    campo: str,
) -> None:
    antes = await cuantos_planes(session)
    with actor_scope(admin.id), pytest.raises(PlanValidationError) as error:
        await service.create(session, entrada(**cambios))
    await session.rollback()
    assert error.value.status == 422 and error.value.field == campo
    assert await cuantos_planes(session) == antes
