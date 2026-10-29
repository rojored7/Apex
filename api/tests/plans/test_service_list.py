"""`plans.service.list`, `get`, `get_including_deleted` y `names_for` con PostgreSQL real (S2-B9;
US-079; S2-D26; blueprint B9).

Lista:
- excluye los dados de baja; `active` filtra (`True` activos, `False` inactivos, `None` todos los
  vivos para el admin); el coach solo con `active=True` (si no, `PlanScopeForbidden`);
- `q` sin distinguir mayúsculas ni tildes, en los dos sentidos (`translate(lower(name), ...)` en
  columna y término): `"TRIMES"` encuentra "Trimestral", `"promo"` encuentra "Mensual Promo",
  `"promocion"` encuentra "Promoción" y `"ménsual"` encuentra "Mensual"; `%`, `_` y `\\` no son
  comodines; `q` en blanco no filtra;
- orden `name, id`; paginación con `limit`, `offset` y `total` sin repetir ni omitir.
Contratos para otros módulos:
- `get(plan_id)` da `PlanSnapshot` (nunca el ORM); `PlanNotFound` (404) si no existe o está dado de
  baja; con `for_share=True` la consulta lleva `FOR SHARE` y el candado frena un `UPDATE` de otra
  transacción;
- `get_including_deleted` lee también los dados de baja;
- `names_for(ids)`: `{id: nombre}` en una sola sentencia, con dados de baja, sin los inexistentes;
  `names_for([])` da `{}` sin consultar.
S4A-B7 (S4A-D25): cada fila de `list` y la salida de `detail` llevan `active_members_count`
(membresías con estado efectivo distinto de `cancelled` y `expired`), contado por lote en una
sola consulta a `memberships.memberships` por página; `create` devuelve 0 sin consultar
`memberships`.
"""

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator, Sequence
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.core.crypto.keyring import Keyring
from app.core.pagination import PageParams
from app.core.security import Role
from app.modules.plans import service
from app.modules.plans.exceptions import PlanNotFound, PlanScopeForbidden
from app.modules.plans.models import Plan
from app.modules.plans.schemas import PlanOut, PlanSnapshot
from tests.conftest import T0, ContadorDeConsultas
from tests.factories.plans import make_plan, make_plans
from tests.plans._apoyo import CAMPOS_PLAN, con_membresias, crear, entrada

LOCK_NOT_AVAILABLE = "55P03"


async def listar(
    session: AsyncSession,
    *,
    q: str | None = None,
    active: bool | None = None,
    role: Role = "admin",
    limit: int = 25,
    offset: int = 0,
) -> Any:
    return await service.list(
        session, q=q, active=active, page=PageParams(limit=limit, offset=offset), role=role
    )


def nombres(pagina: Any) -> builtins.list[str]:
    return [fila.name for fila in pagina.items]


async def catalogo(session: AsyncSession) -> dict[str, Plan]:
    """Seis planes: cuatro activos, uno inactivo y uno dado de baja."""
    planes = {
        "Mensual": await make_plan(session, name="Mensual"),
        "Trimestral": await make_plan(session, name="Trimestral", duration_days=90),
        "Mensual Promo": await make_plan(session, name="Mensual Promo", price_cop=99_000),
        "Promoción": await make_plan(session, name="Promoción", duration_days=15),
        "Anual": await make_plan(session, name="Anual", duration_days=365, is_active=False),
        "Semestral": await make_plan(
            session, name="Semestral", duration_days=180, deleted_at=T0 - timedelta(days=1)
        ),
    }
    return planes


@pytest.fixture
async def sentencias(engine: AsyncEngine) -> AsyncIterator[builtins.list[str]]:
    """SQL que envía la sesión de la prueba (sin `SAVEPOINT`/`RELEASE`)."""
    capturadas: builtins.list[str] = []

    def anotar(_conn: Any, _cursor: Any, sql: str, *_args: Any) -> None:
        if not sql.lstrip().upper().startswith(("SAVEPOINT", "RELEASE", "ROLLBACK TO")):
            capturadas.append(sql)

    event.listen(engine.sync_engine, "before_cursor_execute", anotar)
    try:
        yield capturadas
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", anotar)


def _de_planes(capturadas: Sequence[str]) -> builtins.list[str]:
    return [s for s in capturadas if "plans.plans" in s]


# Lista: filtros ------------------------------------------------------------------------------


async def test_sin_filtros_el_admin_ve_los_vivos_activos_e_inactivos_en_orden_de_nombre(
    session: AsyncSession,
) -> None:
    await catalogo(session)
    pagina = await listar(session)
    assert nombres(pagina) == ["Anual", "Mensual", "Mensual Promo", "Promoción", "Trimestral"]
    assert pagina.total == 5 and (pagina.limit, pagina.offset) == (25, 0)
    for fila in pagina.items:
        assert isinstance(fila, PlanOut)
        assert set(fila.model_dump()) == CAMPOS_PLAN
        assert type(fila.price_cop) is int


async def test_active_true_da_solo_los_activos_y_false_solo_los_inactivos(
    session: AsyncSession,
) -> None:
    await catalogo(session)
    activos = await listar(session, active=True)
    assert nombres(activos) == ["Mensual", "Mensual Promo", "Promoción", "Trimestral"]
    assert all(f.is_active for f in activos.items)
    inactivos = await listar(session, active=False)
    assert nombres(inactivos) == ["Anual"] and inactivos.total == 1


async def test_los_dados_de_baja_nunca_aparecen(session: AsyncSession) -> None:
    await catalogo(session)
    for active in (None, True, False):
        assert "Semestral" not in nombres(await listar(session, active=active))
    assert (await listar(session, q="semes")).items == []


async def test_el_coach_lista_los_activos_con_active_true(session: AsyncSession) -> None:
    await catalogo(session)
    pagina = await listar(session, active=True, role="coach")
    assert nombres(pagina) == ["Mensual", "Mensual Promo", "Promoción", "Trimestral"]


@pytest.mark.parametrize("active", [None, False], ids=["sin-parametro", "inactivos"])
async def test_el_coach_sin_active_true_recibe_plan_scope_forbidden(
    session: AsyncSession, active: bool | None
) -> None:
    await make_plan(session)
    with pytest.raises(PlanScopeForbidden):
        await listar(session, active=active, role="coach")


# Lista: búsqueda -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("q", "esperados"),
    [
        ("TRIMES", ["Trimestral"]),
        ("trimes", ["Trimestral"]),
        ("promo", ["Mensual Promo", "Promoción"]),
        ("PROMO", ["Mensual Promo", "Promoción"]),
        ("promocion", ["Promoción"]),
        ("PROMOCIÓN", ["Promoción"]),
        ("ménsual", ["Mensual", "Mensual Promo"]),
        ("  mensual  ", ["Mensual", "Mensual Promo"]),
        ("anu", ["Anual"]),
        ("zzz", []),
    ],
    ids=[
        "mayusculas",
        "minusculas",
        "promo",
        "promo-mayusculas",
        "sin-tilde-encuentra-con-tilde",
        "tilde-mayuscula",
        "con-tilde-encuentra-sin-tilde",
        "recortado",
        "inactivo",
        "nada",
    ],
)
async def test_q_busca_sin_mayusculas_ni_tildes(
    session: AsyncSession, q: str, esperados: builtins.list[str]
) -> None:
    await catalogo(session)
    pagina = await listar(session, q=q)
    assert nombres(pagina) == esperados
    assert pagina.total == len(esperados)


@pytest.mark.parametrize("q", [None, "", "   "], ids=["nulo", "vacio", "blanco"])
async def test_q_vacio_no_filtra(session: AsyncSession, q: str | None) -> None:
    await catalogo(session)
    assert (await listar(session, q=q)).total == 5


@pytest.mark.parametrize(
    ("q", "esperado"),
    [("100%", "100% Libre"), ("a_b", "Plan a_b"), ("\\", "Barra \\ Plan"), ("%", "100% Libre")],
    ids=["porcentaje", "guion-bajo", "barra", "solo-porcentaje"],
)
async def test_los_comodines_se_escapan(session: AsyncSession, q: str, esperado: str) -> None:
    for nombre in ("100% Libre", "1000 Libre", "Plan a_b", "Plan axb", "Barra \\ Plan", "Barra"):
        await make_plan(session, name=nombre)
    assert nombres(await listar(session, q=q)) == [esperado]


async def test_q_y_active_se_combinan(session: AsyncSession) -> None:
    await catalogo(session)
    assert nombres(await listar(session, q="a", active=False)) == ["Anual"]
    assert nombres(await listar(session, q="promo", active=True)) == ["Mensual Promo", "Promoción"]


# Lista: orden y paginación -------------------------------------------------------------------


async def test_pagina_en_orden_de_nombre_sin_repetir_ni_omitir(session: AsyncSession) -> None:
    creados = await make_plans(session, 5)
    primera = await listar(session, limit=2, offset=0)
    segunda = await listar(session, limit=2, offset=2)
    tercera = await listar(session, limit=2, offset=4)
    assert nombres(primera) == ["Plan 000", "Plan 001"]
    assert nombres(segunda) == ["Plan 002", "Plan 003"]
    assert nombres(tercera) == ["Plan 004"]
    assert {p.total for p in (primera, segunda, tercera)} == {5}
    assert (segunda.limit, segunda.offset) == (2, 2)
    vistos = [f.id for p in (primera, segunda, tercera) for f in p.items]
    assert vistos == [p.id for p in creados]


async def test_la_consulta_ordena_por_nombre_y_luego_por_id(
    session: AsyncSession, sentencias: builtins.list[str]
) -> None:
    await make_plan(session)
    sentencias.clear()
    await listar(session)
    pagina = [s for s in _de_planes(sentencias) if "ORDER BY" in s.upper()]
    assert pagina, sentencias
    orden = pagina[-1].upper().split("ORDER BY", 1)[1]
    assert orden.index("NAME") < orden.index(".ID"), orden


# get y get_including_deleted -----------------------------------------------------------------


async def test_get_devuelve_el_snapshot_y_no_el_orm(session: AsyncSession) -> None:
    plan = await make_plan(session, name="Tiquetera 12", kind="classes", class_count=12)
    snapshot = await service.get(session, plan.id)
    assert snapshot == PlanSnapshot(
        id=plan.id,
        name="Tiquetera 12",
        price_cop=120_000,
        kind="classes",
        duration_days=30,
        class_count=12,
        is_active=True,
        deleted_at=None,
    )
    assert not isinstance(snapshot, Plan)


async def test_get_de_un_plan_inactivo_lo_devuelve(session: AsyncSession) -> None:
    plan = await make_plan(session, is_active=False)
    assert (await service.get(session, plan.id)).is_active is False


async def test_get_de_un_dado_de_baja_o_inexistente_da_plan_not_found(
    session: AsyncSession,
) -> None:
    baja = await make_plan(session, deleted_at=T0)
    for plan_id in (baja.id, uuid4()):
        with pytest.raises(PlanNotFound) as error:
            await service.get(session, plan_id)
        assert error.value.status == 404 and error.value.code == "plan_not_found"


async def test_get_including_deleted_lee_los_dados_de_baja(session: AsyncSession) -> None:
    baja = await make_plan(session, deleted_at=T0)
    snapshot = await service.get_including_deleted(session, baja.id)
    assert snapshot.id == baja.id and snapshot.deleted_at == T0
    with pytest.raises(PlanNotFound):
        await service.get_including_deleted(session, uuid4())


async def test_get_for_share_lleva_for_share_y_sin_el_no(
    session: AsyncSession, sentencias: builtins.list[str]
) -> None:
    plan = await make_plan(session)
    sentencias.clear()
    await service.get(session, plan.id)
    assert _de_planes(sentencias) and not any(
        "FOR SHARE" in s.upper() for s in _de_planes(sentencias)
    )
    sentencias.clear()
    await service.get(session, plan.id, for_share=True)
    assert any("FOR SHARE" in s.upper() for s in _de_planes(sentencias)), sentencias


async def test_get_for_share_frena_un_update_de_otra_transaccion(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    """El candado de `FOR SHARE` es real: mientras la venta lee el plan, una baja concurrente
    espera (aquí, con `lock_timeout`, falla con 55P03)."""
    lectora, otra = dos_sesiones
    plan = await make_plan(lectora, name="Candado")
    await service.get(lectora, plan.id, for_share=True)
    try:
        await otra.execute(text("SET LOCAL lock_timeout = '300ms'"))
        with pytest.raises(DBAPIError) as error:
            await otra.execute(
                text("UPDATE plans.plans SET deleted_at = now() WHERE id = :id"), {"id": plan.id}
            )
        assert getattr(error.value.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE
    finally:
        await otra.rollback()
        await lectora.rollback()


# names_for -----------------------------------------------------------------------------------


async def test_names_for_incluye_dados_de_baja_en_una_sola_sentencia(
    session: AsyncSession, sentencias: builtins.list[str]
) -> None:
    vivo = await make_plan(session, name="Mensual")
    inactivo = await make_plan(session, name="Anual", is_active=False)
    baja = await make_plan(session, name="Semestral", deleted_at=T0)
    sentencias.clear()
    resultado = await service.names_for(session, [vivo.id, inactivo.id, baja.id, uuid4()])
    assert resultado == {vivo.id: "Mensual", inactivo.id: "Anual", baja.id: "Semestral"}
    assert len(_de_planes(sentencias)) == 1, sentencias


async def test_names_for_vacio_da_dict_vacio_sin_consultar(
    session: AsyncSession, sentencias: builtins.list[str]
) -> None:
    sentencias.clear()
    assert await service.names_for(session, []) == {}
    assert _de_planes(sentencias) == []


async def test_names_for_acepta_cualquier_iterable_y_repetidos(session: AsyncSession) -> None:
    plan = await make_plan(session)
    ids: tuple[UUID, ...] = (plan.id, plan.id)
    assert await service.names_for(session, iter(ids)) == {plan.id: "Mensual"}


# S4A-B7 (S4A-D25): `active_members_count` -------------------------------------------------------


async def test_cada_fila_de_la_lista_lleva_active_members_count(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    planes = await catalogo(session)
    estados = ["active", "expiring", "pending_payment", "frozen", "expired", "cancelled"]
    await con_membresias(session, planes["Mensual"], estados)
    await con_membresias(session, planes["Trimestral"], ["expired", "pending_payment"])
    await con_membresias(session, planes["Anual"], ["frozen"])
    pagina = await listar(session)
    conteos = {fila.name: fila.active_members_count for fila in pagina.items}
    assert conteos == {
        "Anual": 1,
        "Mensual": 4,
        "Mensual Promo": 0,
        "Promoción": 0,
        "Trimestral": 1,
    }


async def test_la_lista_cuenta_con_una_sola_consulta_a_memberships(
    session: AsyncSession,
    reloj: FrozenClock,
    bus_listo: Keyring,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    planes = await make_plans(session, 30)
    await con_membresias(session, planes[0], ["active"])
    with contador_de_consultas.midiendo() as medido:
        pagina = await listar(session, limit=25)
    assert len(pagina.items) == 25
    assert medido.de("memberships.memberships") == 1
    assert [f.active_members_count for f in pagina.items][:2] == [1, 0]


async def test_el_detalle_lleva_active_members_count(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    await con_membresias(session, plan, ["active", "pending_payment", "expired"])
    salida = await service.detail(session, plan.id, role="admin")
    assert salida.active_members_count == 2


async def test_create_devuelve_cero_sin_consultar_memberships(
    session: AsyncSession, reloj: FrozenClock, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo() as medido:
        salida = await crear(session, SYSTEM_USER_ID, entrada(name="Quincenal", duration_days=15))
    assert salida.active_members_count == 0
    assert set(salida.model_dump()) == CAMPOS_PLAN
    assert medido.de("memberships.memberships") == 0
