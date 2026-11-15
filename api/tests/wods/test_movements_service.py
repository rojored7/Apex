"""`wods.service` de movimientos con base real (S8-A1, US-165; S8-D5). Rojo A1."""

from __future__ import annotations

from typing import Any
from unittest import mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.pagination import PageParams
from app.modules.wods import movements as movements_module
from app.modules.wods import service
from app.modules.wods.exceptions import MovementExists, MovementNotFound, WodsValidationError
from app.modules.wods.schemas import (
    CatalogMovementOut,
    MovementCreate,
    MovementListQuery,
    MovementPatch,
)
from tests.conftest import CrearUsuario
from tests.factories.wods import make_wod

PAGINA = PageParams(limit=50, offset=0)
SIN_FILTROS = MovementListQuery()


def _crear(**cambios: Any) -> MovementCreate:
    valores: dict[str, Any] = {"name": "Back Squat", "category": "weightlifting", "unit": "kg"}
    valores.update(cambios)
    return MovementCreate.model_validate(valores)


async def _alta(session: AsyncSession, actor: UUID, **cambios: Any) -> CatalogMovementOut:
    with actor_scope(actor):
        salida = await service.create_movement(session, _crear(**cambios), actor)
        await session.commit()
    return salida


async def _cambio(
    session: AsyncSession, actor: UUID, mid: UUID, **cambios: Any
) -> CatalogMovementOut:
    with actor_scope(actor):
        salida = await service.update_movement(
            session, mid, MovementPatch.model_validate(cambios), actor
        )
        await session.commit()
    return salida


async def _fila(session: AsyncSession, mid: UUID) -> dict[str, Any]:
    consulta = text("SELECT * FROM wods.movements WHERE id = :i")
    return dict((await session.execute(consulta, {"i": mid})).mappings().one())


async def test_el_alta_guarda_activo_con_nombre_normalizado(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    salida = await _alta(session, admin.id, name="  Back   Squat ")
    assert (salida.name, salida.category, salida.unit) == ("Back Squat", "weightlifting", "kg")
    assert salida.is_active is True and salida.wod_count == 0
    fila = await _fila(session, salida.id)
    assert fila["name_norm"] == "back squat"
    assert fila["created_by"] == admin.id


async def test_409_movement_exists_con_espacios_y_mayusculas(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    await _alta(session, admin.id, name="Pull-up", category="gymnastics", unit="reps")
    with pytest.raises(MovementExists):
        await _alta(session, admin.id, name=" pull-UP ", category="gymnastics", unit="reps")
    lista = await service.list_movements(session, SIN_FILTROS, PAGINA)
    assert lista.total == 1


async def test_409_trae_existing_id_y_field_name(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    primero = await _alta(session, admin.id, name="Pull-up")
    with pytest.raises(MovementExists) as error:
        await _alta(session, admin.id, name="PULL-UP")
    assert error.value.status == 409 and error.value.code == "movement_exists"
    assert error.value.field == "name"
    assert error.value.existing_id == primero.id


async def test_patch_a_un_nombre_ajeno_da_409_y_a_si_mismo_no(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    a = await _alta(session, admin.id, name="Snatch")
    b = await _alta(session, admin.id, name="Clean")
    with pytest.raises(MovementExists) as error:
        await _cambio(session, admin.id, b.id, name="snatch ")
    assert error.value.existing_id == a.id
    mismo = await _cambio(session, admin.id, a.id, name="SNATCH")  # mismo name_norm: se permite
    assert mismo.name == "SNATCH"


async def test_patch_solo_cambia_lo_enviado_y_audita(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    mov = await _alta(session, admin.id)
    cambiado = await _cambio(session, admin.id, mov.id, category="other", unit="reps")
    assert (cambiado.name, cambiado.category, cambiado.unit) == ("Back Squat", "other", "reps")
    filas = (
        await session.execute(
            text("SELECT action FROM audit.audit_log WHERE record_id = :i ORDER BY seq"),
            {"i": mov.id},
        )
    ).all()
    assert [f[0] for f in filas] == ["insert", "update"]


async def test_patch_sin_cambios_no_audita(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    mov = await _alta(session, admin.id)
    await _cambio(session, admin.id, mov.id, name="Back Squat", is_active=True)
    cuenta = await session.scalar(
        text("SELECT count(*) FROM audit.audit_log WHERE record_id = :i"), {"i": mov.id}
    )
    assert cuenta == 1


async def test_patch_con_null_explicito_da_422_con_field(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    mov = await _alta(session, admin.id)
    for campo in ("name", "category", "unit", "is_active"):
        with pytest.raises(WodsValidationError) as error:
            await _cambio(session, admin.id, mov.id, **{campo: None})
        assert error.value.field == campo


async def test_patch_de_inexistente_da_404(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    with pytest.raises(MovementNotFound):
        await _cambio(session, admin.id, uuid4(), name="X")
    with pytest.raises(MovementNotFound):
        await service.get_movement(session, uuid4())


async def test_desactivar_no_cambia_wods(session: AsyncSession, usuario_real: CrearUsuario) -> None:
    """Desactivar solo cambia `is_active`: nombre, categoría y unidad quedan, el movimiento se
    lista con `active=false` y los WODs que lo usan no cambian (A3: con un WOD real)."""
    admin = await usuario_real("admin")
    mov = await _alta(session, admin.id)
    wod = await make_wod(session, admin.id, [mov.id])
    apagado = await _cambio(session, admin.id, mov.id, is_active=False)
    assert apagado.is_active is False
    assert (apagado.name, apagado.category, apagado.unit) == (mov.name, mov.category, mov.unit)
    inactivos = await service.list_movements(session, MovementListQuery(active=False), PAGINA)
    assert [m.id for m in inactivos.items] == [mov.id]
    activos = await service.list_movements(session, MovementListQuery(active=True), PAGINA)
    assert activos.total == 0
    vuelta = await _cambio(session, admin.id, mov.id, is_active=True)
    assert vuelta.is_active is True
    despues = await service.get_wod(session, wod.id)
    assert despues.movements[0].movement_name == mov.name and despues.updated_at == wod.updated_at
    assert apagado.wod_count == 1 and vuelta.wod_count == 1


async def test_lista_filtra_busca_pagina_y_ordena_por_nombre(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    await _alta(session, admin.id, name="Zancadas", category="other", unit="reps")
    await _alta(session, admin.id, name="Arranque")
    await _alta(session, admin.id, name="Tracción Alta", category="gymnastics", unit="reps")
    todo = await service.list_movements(session, SIN_FILTROS, PAGINA)
    assert [m.name for m in todo.items] == ["Arranque", "Tracción Alta", "Zancadas"]
    gim = await service.list_movements(session, MovementListQuery(category="gymnastics"), PAGINA)
    assert [m.name for m in gim.items] == ["Tracción Alta"]
    sin_tilde = await service.list_movements(session, SIN_FILTROS, PAGINA, q="traccion")
    assert [m.name for m in sin_tilde.items] == ["Tracción Alta"]
    pagina = await service.list_movements(session, SIN_FILTROS, PageParams(limit=2, offset=2))
    assert (pagina.total, [m.name for m in pagina.items]) == (3, ["Zancadas"])


async def test_busqueda_con_comodines_es_literal(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    await _alta(session, admin.id, name="Arranque")
    r = await service.list_movements(session, SIN_FILTROS, PAGINA, q="%")
    assert r.total == 0


async def test_wod_count_en_una_consulta_por_pagina(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """La lista pide los conteos de TODA la pagina en una sola llamada (sin N+1)."""
    admin = await usuario_real("admin")
    ids = [(await _alta(session, admin.id, name=f"Mov {i}")).id for i in range(3)]
    llamadas: list[list[UUID]] = []

    async def espia(_session: AsyncSession, pedidos: list[UUID]) -> dict[UUID, int]:
        llamadas.append(list(pedidos))
        return {ids[0]: 4}

    with mock.patch.object(movements_module, "usage_counts", espia):
        pagina = await service.list_movements(session, SIN_FILTROS, PAGINA)
    assert len(llamadas) == 1 and set(llamadas[0]) == set(ids)
    cuentas = {m.id: m.wod_count for m in pagina.items}
    assert cuentas == {ids[0]: 4, ids[1]: 0, ids[2]: 0}


def _carrera_en_la_primera_llamada() -> Any:
    """Parche de `_id_by_norm`: la primera llamada (la comprobación previa) no ve a nadie, como si
    el otro alta aún no hubiera confirmado; las siguientes consultan de verdad."""
    original = movements_module._id_by_norm
    llamadas: list[int] = []

    async def parcheada(session: AsyncSession, norm: str, *, exclude: UUID | None) -> UUID | None:
        llamadas.append(1)
        if len(llamadas) == 1:
            return None
        return await original(session, norm, exclude=exclude)

    return mock.patch.object(movements_module, "_id_by_norm", parcheada)


async def test_la_carrera_23505_del_alta_da_409_con_existing_id_y_la_sesion_sigue_viva(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    """S8-A1b: la comprobación previa pasa y el índice único decide: 409 `movement_exists`."""
    admin = await usuario_real("admin")
    primero = await _alta(session, admin.id, name="Snatch")
    with _carrera_en_la_primera_llamada():
        with pytest.raises(MovementExists) as error:
            await _alta(session, admin.id, name="  SNATCH ")
    assert error.value.code == "movement_exists" and error.value.field == "name"
    assert error.value.existing_id == primero.id
    # El savepoint se deshizo: la sesión sigue usable y no quedó la fila repetida.
    lista = await service.list_movements(session, SIN_FILTROS, PAGINA)
    assert [m.id for m in lista.items] == [primero.id]
    otro = await _alta(session, admin.id, name="Clean")
    assert otro.name == "Clean"


async def test_la_carrera_23505_del_patch_da_409_con_existing_id_y_la_sesion_sigue_viva(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    a = await _alta(session, admin.id, name="Snatch")
    b = await _alta(session, admin.id, name="Clean")
    with _carrera_en_la_primera_llamada():
        with pytest.raises(MovementExists) as error:
            await _cambio(session, admin.id, b.id, name="snatch")
    assert error.value.existing_id == a.id
    sigue = await service.get_movement(session, b.id)
    assert sigue.name == "Clean"
    ok = await _cambio(session, admin.id, b.id, category="other")
    assert ok.category == "other"
