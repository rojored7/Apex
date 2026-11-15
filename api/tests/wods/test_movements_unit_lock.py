"""La unidad de un movimiento con WODs no cambia (revisión de A4, M-1; S8-A3b L-4, S8-D41).

Las cargas RX en gramos solo valen con unidad `kg` y el principal de un WOD `load` se mide en kg:
cambiar la unidad de un movimiento usado dejaría WODs inválidos. Crear o editar un WOD lee los
movimientos con `FOR SHARE`, así que el `PATCH` (que los bloquea `FOR UPDATE`) espera a que el WOD
confirme y luego ve el uso.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.errors import DomainError
from app.modules.wods import service
from app.modules.wods.schemas import MovementPatch, WodCreate
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.users import make_user
from tests.factories.wods import cuerpo_wod, make_movement, make_wod

MOVS = "/api/v1/movements"


async def test_con_wods_la_unidad_no_cambia_422_unit(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    mov = await make_movement(session, admin.id, name="Thruster unidad", unit="kg")
    sin_uso = await make_movement(session, admin.id, name="Libre unidad", unit="kg")
    await make_wod(session, admin.id, [mov.id])
    h = cabeceras(admin)
    bloqueado = await app_http.patch(f"{MOVS}/{mov.id}", json={"unit": "reps"}, headers=h)
    assert bloqueado.status_code == 422, bloqueado.text
    assert bloqueado.json()["error"]["field"] == "unit"
    igual = await app_http.patch(
        f"{MOVS}/{mov.id}", json={"unit": "kg", "name": "Thruster 2"}, headers=h
    )
    assert igual.status_code == 200, igual.text
    libre = await app_http.patch(f"{MOVS}/{sin_uso.id}", json={"unit": "reps"}, headers=h)
    assert libre.status_code == 200 and libre.json()["unit"] == "reps"


async def test_el_wod_toma_el_movimiento_for_share_y_el_patch_espera(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    una, otra = dos_sesiones
    admin = await make_user(una, role="admin")
    mov: UUID = (await make_movement(una, admin.id, name="Carrera unidad", unit="kg")).id
    with actor_scope(admin.id):
        datos = WodCreate.model_validate(cuerpo_wod([mov], date="2026-10-22"))
        await service.create_wod(una, datos, admin.id)  # sin confirmar: FOR SHARE del movimiento

        async def cambiar_unidad() -> None:
            try:
                await service.update_movement(
                    otra, mov, MovementPatch.model_validate({"unit": "reps"}), admin.id
                )
            finally:
                await otra.rollback()

        tarea = asyncio.create_task(cambiar_unidad())
        await asyncio.sleep(0.5)
        assert not tarea.done(), "el PATCH debe esperar al FOR SHARE del WOD sin confirmar"
        await una.commit()
        with pytest.raises(DomainError) as info:
            await asyncio.wait_for(tarea, timeout=30)
    assert (info.value.status, info.value.field) == (422, "unit")
