"""`classes.service` de franjas con base real (S7-A2, US-155; S7-D9). Rojo A2."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.pagination import PageParams
from app.modules.classes import service
from app.modules.classes.exceptions import (
    ClassValidationError,
    CoachInvalid,
    SlotConflict,
    SlotNotFound,
)
from app.modules.classes.schemas import SlotCreate, SlotListQuery, SlotOut, SlotPatch
from tests.conftest import CrearUsuario

pytestmark = pytest.mark.usefixtures("reloj")


def _crear(**cambios: Any) -> SlotCreate:
    valores: dict[str, Any] = {"weekdays": [0], "start_time": "06:00", "duration_min": 60}
    valores.update(cambios)
    return SlotCreate.model_validate(valores)


async def _alta(session: AsyncSession, actor: UUID, **cambios: Any) -> SlotOut:
    with actor_scope(actor):
        salida = await service.create_slot(session, _crear(**cambios), actor)
        await session.commit()
    return salida


async def _cambio(session: AsyncSession, actor: UUID, slot: UUID, **cambios: Any) -> SlotOut:
    with actor_scope(actor):
        salida = await service.update_slot(session, slot, SlotPatch.model_validate(cambios), actor)
        await session.commit()
    return salida


async def _fila(session: AsyncSession, slot: UUID) -> dict[str, Any]:
    consulta = text("SELECT * FROM classes.class_slots WHERE id = :i")
    return dict((await session.execute(consulta, {"i": slot})).mappings().one())


async def test_el_alta_guarda_dias_ordenados_y_el_cupo_por_omision(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    franja = await _alta(session, admin.id, weekdays=[4, 0, 2], name="WOD")
    assert franja.weekdays == [0, 2, 4]
    assert franja.capacity == 15  # default_capacity de settings.classes
    assert franja.is_active is True
    assert franja.valid_from == reloj.today_bogota()
    assert franja.start_time == "06:00"
    fila = await _fila(session, franja.id)
    assert fila["created_by"] == admin.id


async def test_capacidad_explicita_gana_al_valor_por_omision(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    assert (await _alta(session, admin.id, capacity=8)).capacity == 8


async def test_coach_nulo_es_open_box(session: AsyncSession, usuario_real: CrearUsuario) -> None:
    admin = await usuario_real("admin")
    franja = await _alta(session, admin.id)
    assert franja.default_coach_id is None
    assert franja.coach_name is None


async def test_coach_activo_o_admin_es_valido_y_trae_su_nombre(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach", email="sara@test.apex")
    franja = await _alta(session, admin.id, default_coach_id=coach.id)
    assert franja.coach_name == "sara"
    otra = await _alta(session, admin.id, start_time="07:00", default_coach_id=admin.id)
    assert otra.default_coach_id == admin.id


async def test_coach_socio_da_422_coach_invalid(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    socio = await usuario_real("member")
    with pytest.raises(CoachInvalid) as error:
        await _alta(session, admin.id, default_coach_id=socio.id)
    assert (error.value.status, error.value.code) == (422, "coach_invalid")
    assert error.value.field == "default_coach_id"


@pytest.mark.parametrize("estado", ["bloqueado", "borrado", "inexistente"])
async def test_coach_bloqueado_borrado_o_inexistente_da_422(
    session: AsyncSession, usuario_real: CrearUsuario, estado: str
) -> None:
    admin = await usuario_real("admin")
    if estado == "inexistente":
        coach_id = uuid4()
    elif estado == "bloqueado":
        coach_id = (await usuario_real("coach", bloqueado=True)).id
    else:
        coach_id = (await usuario_real("coach", borrado=True)).id
    with pytest.raises(CoachInvalid):
        await _alta(session, admin.id, default_coach_id=coach_id)


async def test_409_slot_conflict_por_un_dia_compartido(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    primera = await _alta(session, admin.id, weekdays=[0, 2])
    with pytest.raises(SlotConflict) as error:
        await _alta(session, admin.id, weekdays=[2, 3])
    assert (error.value.status, error.value.code) == (409, "slot_conflict")
    assert error.value.existing_id == primera.id


async def test_otra_hora_o_dias_distintos_no_chocan(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    await _alta(session, admin.id, weekdays=[0, 2])
    await _alta(session, admin.id, weekdays=[1, 3])
    await _alta(session, admin.id, weekdays=[0, 2], start_time="06:30")


async def test_una_franja_pausada_no_cuenta_para_el_choque_y_reactivar_si(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    primera = await _alta(session, admin.id)
    await _cambio(session, admin.id, primera.id, is_active=False)
    segunda = await _alta(session, admin.id)  # mismo día y hora: la primera está pausada
    with pytest.raises(SlotConflict):
        await _cambio(session, admin.id, primera.id, is_active=True)
    assert segunda.id != primera.id


async def test_patch_solo_cambia_lo_enviado_y_audita(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    franja = await _alta(session, admin.id, name="Uno")
    cambiada = await _cambio(session, admin.id, franja.id, capacity=20, name=None)
    assert (cambiada.capacity, cambiada.name, cambiada.start_time) == (20, None, "06:00")
    filas = (
        await session.execute(
            text(
                "SELECT action, after FROM audit.audit_log "
                "WHERE table_name = 'classes.class_slots' AND record_id = :i ORDER BY seq"
            ),
            {"i": franja.id},
        )
    ).all()
    assert [f.action for f in filas] == ["insert", "update"]
    assert filas[1].after == {"capacity": 20, "name": None}


async def test_patch_sin_cambios_no_audita(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    franja = await _alta(session, admin.id)
    await _cambio(session, admin.id, franja.id, capacity=franja.capacity)
    cuantas = await session.scalar(
        text("SELECT count(*) FROM audit.audit_log WHERE record_id = :i"), {"i": franja.id}
    )
    assert cuantas == 1


@pytest.mark.parametrize("campo", ["weekdays", "start_time", "duration_min", "capacity"])
async def test_patch_con_null_en_un_campo_obligatorio_da_422(
    session: AsyncSession, usuario_real: CrearUsuario, campo: str
) -> None:
    admin = await usuario_real("admin")
    franja = await _alta(session, admin.id)
    with pytest.raises(ClassValidationError) as error:
        await _cambio(session, admin.id, franja.id, **{campo: None})
    assert error.value.field == campo


async def test_patch_de_una_franja_inexistente_da_404(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    with pytest.raises(SlotNotFound):
        await _cambio(session, admin.id, uuid4(), capacity=5)


async def test_patch_solo_escribe_en_class_slots(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """A2 aún no tiene `class_sessions` (B1): el `PATCH` no escribe fuera de `class_slots`
    (Q23); B1 suma la prueba con una sesión ya generada."""
    admin = await usuario_real("admin")
    franja = await _alta(session, admin.id)
    await _cambio(session, admin.id, franja.id, start_time="07:30")
    tablas = (
        (
            await session.execute(
                text("SELECT DISTINCT table_name FROM audit.audit_log WHERE record_id = :i"),
                {"i": franja.id},
            )
        )
        .scalars()
        .all()
    )
    assert list(tablas) == ["classes.class_slots"]


async def test_la_lista_filtra_por_activa_y_dia_y_pagina(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    lunes = await _alta(session, admin.id, weekdays=[0], start_time="06:00")
    await _alta(session, admin.id, weekdays=[1, 2], start_time="07:00")
    pausada = await _alta(session, admin.id, weekdays=[0], start_time="08:00")
    await _cambio(session, admin.id, pausada.id, is_active=False)

    pagina = PageParams(limit=50, offset=0)
    todas = await service.list_slots(session, SlotListQuery(), pagina)
    assert (todas.total, [s.start_time for s in todas.items]) == (3, ["06:00", "07:00", "08:00"])
    activas = await service.list_slots(session, SlotListQuery(is_active=True), pagina)
    assert activas.total == 2
    del_lunes = await service.list_slots(session, SlotListQuery(weekday=0), pagina)
    assert {s.id for s in del_lunes.items} == {lunes.id, pausada.id}
    corta = await service.list_slots(session, SlotListQuery(), PageParams(limit=1, offset=1))
    assert (corta.total, len(corta.items), corta.items[0].start_time) == (3, 1, "07:00")


async def test_la_lista_busca_por_nombre_sin_tildes(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    await _alta(session, admin.id, weekdays=[0], name="Fuerza AM")
    await _alta(session, admin.id, weekdays=[1], name="Cardio")
    pagina = PageParams(limit=50, offset=0)
    r = await service.list_slots(session, SlotListQuery(), pagina, q="FUERZA")
    assert [s.name for s in r.items] == ["Fuerza AM"]
    sin = await service.list_slots(session, SlotListQuery(), pagina, q="zzz")
    assert sin.total == 0
