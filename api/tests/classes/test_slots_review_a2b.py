"""Correcciones de la revisión de S7-A2 (S7-A2b): hora inválida, días repetidos, PATCH, coach,
búsqueda y candado asesor 4_270_005."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.pagination import PageParams
from app.modules.classes import service
from app.modules.classes.exceptions import ClassValidationError, CoachInvalid, SlotConflict
from app.modules.classes.rules import validate_slot
from app.modules.classes.schemas import SlotCreate, SlotListQuery, SlotOut, SlotPatch
from tests.conftest import Cabeceras, CrearUsuario

SLOTS = "/api/v1/class-slots"
ARABE_8 = chr(0x0668)  # dígito árabe-índico ocho
ARABE_0 = chr(0x0660)

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


# MEDIUM: dígitos Unicode ------------------------------------------------------------------------


@pytest.mark.parametrize("hora", [f"0{ARABE_8}:30", f"06:3{ARABE_0}"], ids=["hora", "minuto"])
async def test_hora_con_digitos_unicode_da_422_start_time_en_post_y_patch(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, hora: str
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    cuerpo = {"weekdays": [0], "start_time": hora, "duration_min": 60}
    r = await app_http.post(SLOTS, json=cuerpo, headers=h)
    assert r.status_code == 422 and r.json()["error"]["field"] == "start_time", r.text
    ok = await app_http.post(SLOTS, json={**cuerpo, "start_time": "06:00"}, headers=h)
    parche = await app_http.patch(
        f"{SLOTS}/{ok.json()['id']}", json={"start_time": hora}, headers=h
    )
    assert parche.status_code == 422 and parche.json()["error"]["field"] == "start_time"


@pytest.mark.parametrize("hora", [f"0{ARABE_8}:30", "ab:cd", "24:00"])
def test_validate_slot_rechaza_la_hora_sin_lanzar_value_error(hora: str) -> None:
    with pytest.raises(ClassValidationError) as error:
        validate_slot([0], hora, 60, 15)
    assert error.value.field == "start_time"


# LOW: días repetidos con el mismo criterio -----------------------------------------------------


async def test_patch_con_dias_repetidos_da_422_como_el_alta(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    franja = await _alta(session, admin.id)
    with pytest.raises(ClassValidationError) as error:
        await _alta(session, admin.id, weekdays=[1, 1], start_time="07:00")
    assert error.value.field == "weekdays"
    with pytest.raises(ClassValidationError) as error:
        await _cambio(session, admin.id, franja.id, weekdays=[0, 0])
    assert error.value.field == "weekdays"


# LOW: PATCH hacia una franja activa -------------------------------------------------------------


async def test_patch_de_hora_o_dias_hacia_otra_franja_activa_da_409(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    primera = await _alta(session, admin.id, weekdays=[0, 2], start_time="06:00")
    segunda = await _alta(session, admin.id, weekdays=[1], start_time="06:00")
    tercera = await _alta(session, admin.id, weekdays=[0], start_time="07:00")
    with pytest.raises(SlotConflict) as por_dia:
        await _cambio(session, admin.id, segunda.id, weekdays=[1, 2])
    assert por_dia.value.existing_id == primera.id
    with pytest.raises(SlotConflict) as por_hora:
        await _cambio(session, admin.id, tercera.id, start_time="06:00")
    assert por_hora.value.existing_id == primera.id


async def test_patch_con_coach_invalido_da_422_coach_invalid(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    socio = await usuario_real("member")
    franja = await _alta(session, admin.id)
    with pytest.raises(CoachInvalid):
        await _cambio(session, admin.id, franja.id, default_coach_id=socio.id)


@pytest.mark.parametrize("estado", ["inactivo", "pendiente", "sistema"])
async def test_coach_inactivo_pendiente_o_del_sistema_da_422(
    session: AsyncSession, usuario_real: CrearUsuario, estado: str
) -> None:
    admin = await usuario_real("admin")
    if estado == "inactivo":
        coach_id = (await usuario_real("coach", activo=False)).id
    elif estado == "pendiente":
        coach_id = (await usuario_real("coach", password=None)).id
    else:
        coach_id = SYSTEM_USER_ID
    with pytest.raises(CoachInvalid):
        await _alta(session, admin.id, default_coach_id=coach_id)


async def test_otra_hora_o_dias_distintos_no_chocan_y_quedan_tres(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    await _alta(session, admin.id, weekdays=[0, 2])
    await _alta(session, admin.id, weekdays=[1, 3])
    await _alta(session, admin.id, weekdays=[0, 2], start_time="06:30")
    todas = await service.list_slots(session, SlotListQuery(), PageParams(limit=50, offset=0))
    assert todas.total == 3


@pytest.mark.parametrize("q", ["%", "_", "100%", "a_b"])
async def test_q_con_comodines_de_like_no_coincide_con_todo(
    session: AsyncSession, usuario_real: CrearUsuario, q: str
) -> None:
    admin = await usuario_real("admin")
    await _alta(session, admin.id, weekdays=[0], name="Fuerza AM")
    await _alta(session, admin.id, weekdays=[1], name="Cardio")
    r = await service.list_slots(session, SlotListQuery(), PageParams(limit=50, offset=0), q=q)
    assert r.total == 0


async def test_dos_altas_concurrentes_con_el_mismo_dia_y_hora_dejan_una_sola(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    """El candado 4_270_005 serializa las altas: la segunda ve la primera y da 409."""
    primera, segunda = dos_sesiones
    from tests.factories.users import make_user

    admin = await make_user(primera, role="admin")

    async def alta(sesion: AsyncSession) -> str:
        with actor_scope(admin.id):
            try:
                await service.create_slot(sesion, _crear(), admin.id)
                await sesion.commit()
            except SlotConflict:
                await sesion.rollback()
                return "conflicto"
        return "creada"

    resultados = await asyncio.gather(alta(primera), alta(segunda))
    assert sorted(resultados) == ["conflicto", "creada"]
