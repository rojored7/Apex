"""Lista de la auditoría con datos reales (S4A-B4, US-102; S4A-D16, S4A-D19, S4A-D45, S4A-D54).

`audit_service.list_entries(session, AuditListQuery(...), page)` (fachada: filtros con el reloj de
la app y `queries.list`) sobre la cadena de la prueba: `audit_chain_factory` la vacía, `ana`
(admin, `ana.perez@ejemplo.local`) y `juan` (coach, `juan.rios@ejemplo.local`) se crean después
y `sembrar_actividad` corre los services reales. Reloj congelado en T0 = 2026-10-21T15:00:00Z.
Las once filas, calculadas a mano (y confirmadas una vez contra los services):

  1 Sistema insert auth.users (Ana)        7 Ana  insert memberships.memberships (venta)
  2 Sistema insert auth.users (Juan)       8 Juan insert payments.payments (pago)
  3 Ana  insert plans.plans                9 Juan update memberships.memberships (activa)
  4 Ana  insert members.members (Lucía)   10 Ana  update payments.payments (anula)
  5 Juan update members.members           11 Ana  update memberships.memberships (revierte)
  6 Juan reveal members.members

`record_id` de 4 a 6 es la socia, de 7, 9 y 11 la membresía y de 8 y 10 el pago;
`subject_member_id` es la socia de 4 a 11. `user_name` es la parte local del correo (`ana.perez`,
`juan.rios`) y `Sistema` para `SYSTEM_USER_ID` (correo `system@apex.local`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditEntry
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.core.pagination import Page, PageParams
from app.modules.audit import queries as audit_queries
from app.modules.audit.schemas import AuditListQuery, AuditRow
from app.modules.members import service as members_service
from tests.audit._apoyo import (
    ANA_EMAIL,
    ANA_NOMBRE,
    CAMPOS_ROW,
    JUAN_EMAIL,
    JUAN_NOMBRE,
    Actividad,
    sembrar_actividad,
)
from tests.audit.conftest import CadenaDePrueba, audit_service
from tests.conftest import UsuarioPrueba

T0 = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
TODAS = list(range(11, 0, -1))
GRANDE = PageParams(limit=200)


@pytest.fixture
async def actividad(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
) -> Actividad:
    return await sembrar_actividad(session, ana=ana, juan=juan)


async def _lista(session: AsyncSession, page: PageParams = GRANDE, **datos: Any) -> Page[AuditRow]:
    return await audit_service.list_entries(session, AuditListQuery(**datos), page)


async def _seqs(session: AsyncSession, **datos: Any) -> list[int]:
    pagina = await _lista(session, **datos)
    assert pagina.total == len(pagina.items)
    return [fila.seq for fila in pagina.items]


async def test_sin_filtros_trae_las_once_en_seq_descendente(
    session: AsyncSession, actividad: Actividad
) -> None:
    pagina = await _lista(session)
    assert [f.seq for f in pagina.items] == TODAS
    assert (pagina.total, pagina.limit, pagina.offset) == (11, 200, 0)
    assert all(set(f.model_dump()) == CAMPOS_ROW for f in pagina.items)
    assert all(f.at == T0 for f in pagina.items)


async def test_paginacion_y_total(session: AsyncSession, actividad: Actividad) -> None:
    segunda = await _lista(session, PageParams(limit=4, offset=4))
    assert ([f.seq for f in segunda.items], segunda.total) == ([7, 6, 5, 4], 11)
    ultima = await _lista(session, PageParams(limit=4, offset=8))
    assert ([f.seq for f in ultima.items], ultima.total) == ([3, 2, 1], 11)


async def test_offset_100000_responde_vacio_con_el_total(
    session: AsyncSession, actividad: Actividad
) -> None:
    pagina = await _lista(session, PageParams(limit=25, offset=100_000))
    assert (pagina.items, pagina.total, pagina.offset) == ([], 11, 100_000)


@pytest.mark.parametrize(
    ("tabla", "esperadas"),
    [
        ("members.members", [6, 5, 4]),
        ("memberships.memberships", [11, 9, 7]),
        ("payments.payments", [10, 8]),
        ("plans.plans", [3]),
        ("auth.users", [2, 1]),
        ("settings.settings_sections", []),
    ],
)
async def test_filtro_por_tabla_con_esquema(
    session: AsyncSession, actividad: Actividad, tabla: str, esperadas: list[int]
) -> None:
    assert await _seqs(session, table=tabla) == esperadas


async def test_filtro_por_subject_member_id(session: AsyncSession, actividad: Actividad) -> None:
    assert await _seqs(session, subject_member_id=actividad.member_id) == [
        11,
        10,
        9,
        8,
        7,
        6,
        5,
        4,
    ]


async def test_filtro_por_usuario(
    session: AsyncSession, actividad: Actividad, ana: UsuarioPrueba, juan: UsuarioPrueba
) -> None:
    assert await _seqs(session, user_id=ana.id) == [11, 10, 7, 4, 3]
    assert await _seqs(session, user_id=juan.id) == [9, 8, 6, 5]
    assert await _seqs(session, user_id=SYSTEM_USER_ID) == [2, 1]


async def test_filtro_por_record_id(session: AsyncSession, actividad: Actividad) -> None:
    assert await _seqs(
        session, table="memberships.memberships", record_id=actividad.membership_id
    ) == [11, 9, 7]
    assert await _seqs(session, table="payments.payments", record_id=actividad.payment_id) == [
        10,
        8,
    ]
    assert await _seqs(session, table="members.members", record_id=actividad.member_id) == [6, 5, 4]


@pytest.mark.parametrize(
    ("accion", "esperadas"),
    [
        ("insert", [8, 7, 4, 3, 2, 1]),
        ("update", [11, 10, 9, 5]),
        ("reveal", [6]),
        ("delete", []),
        ("login", []),
    ],
)
async def test_filtro_por_accion(
    session: AsyncSession, actividad: Actividad, accion: str, esperadas: list[int]
) -> None:
    assert await _seqs(session, action=accion) == esperadas


async def test_filtros_combinados(
    session: AsyncSession, actividad: Actividad, juan: UsuarioPrueba
) -> None:
    assert await _seqs(session, table="memberships.memberships", action="update") == [11, 9]
    assert await _seqs(session, table="members.members", user_id=juan.id) == [6, 5]
    assert await _seqs(session, q="ana", table="payments.payments") == [10]


async def test_rango_semiabierto_from_incluye_y_to_excluye(
    session: AsyncSession, actividad: Actividad, ana: UsuarioPrueba, reloj: FrozenClock
) -> None:
    reloj.advance(hours=1)  # fila 12 a las 16:00Z: Ana revela el documento
    session.expunge_all()
    with actor_scope(ana.id):
        await members_service.reveal(session, actividad.member_id, "document", ip="198.51.100.41")
        await session.commit()
    una_hora = T0 + timedelta(hours=1)

    assert await _seqs(session, **{"from": T0 + timedelta(minutes=30)}) == [12]
    assert await _seqs(session, **{"from": una_hora}) == [12]
    assert await _seqs(session, to=una_hora) == TODAS
    assert await _seqs(session, **{"from": T0, "to": una_hora}) == TODAS
    assert await _seqs(session, to=T0) == []


@pytest.mark.parametrize(
    ("q", "esperadas"),
    [
        ("PÉREZ", [11, 10, 7, 4, 3]),
        ("ana.perez", [11, 10, 7, 4, 3]),
        ("JUAN.RIOS", [9, 8, 6, 5]),
        ("Ríos", [9, 8, 6, 5]),
        ("ejemplo.local", [11, 10, 9, 8, 7, 6, 5, 4, 3]),
        ("system", [2, 1]),
        ("nadie-con-este-correo", []),
        ("_", []),
        ("%", []),
    ],
    ids=[
        "mayus-tilde",
        "local",
        "mayus",
        "tilde",
        "dominio",
        "sistema",
        "nadie",
        "guion-bajo",
        "porcentaje",
    ],
)
async def test_q_por_correo_parcial_sin_mayusculas_ni_tildes(
    session: AsyncSession, actividad: Actividad, q: str, esperadas: list[int]
) -> None:
    assert await _seqs(session, q=q) == esperadas


async def test_q_por_record_id(session: AsyncSession, actividad: Actividad) -> None:
    assert await _seqs(session, table="members.members", q=str(actividad.member_id)) == [6, 5, 4]
    assert await _seqs(session, table="payments.payments", q=str(actividad.payment_id).upper()) == [
        10,
        8,
    ]


async def test_q_uuid_sin_table_no_filtra(session: AsyncSession, actividad: Actividad) -> None:
    """S4A-D106 a: sin `table` un `q` UUID se ignora (el conteo no tendría índice líder)."""
    assert await _seqs(session, q=str(actividad.member_id)) == TODAS


async def test_total_se_satura_en_max_audit_offset_mas_uno(
    session: AsyncSession, actividad: Actividad, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S4A-D106 b: el conteo recorre como mucho `MAX_AUDIT_OFFSET + 1` filas."""
    monkeypatch.setattr(audit_queries, "MAX_AUDIT_OFFSET", 5)
    pagina = await _lista(session, PageParams(limit=3, offset=3))
    assert ([f.seq for f in pagina.items], pagina.total) == ([8, 7, 6], 6)
    filtrada = await _lista(session, PageParams(limit=3), table="payments.payments")
    assert filtrada.total == 2


async def test_quien_actuo_parte_local_y_sistema(
    session: AsyncSession, actividad: Actividad, ana: UsuarioPrueba, juan: UsuarioPrueba
) -> None:
    filas = {f.seq: f for f in (await _lista(session)).items}
    assert (filas[3].user_id, filas[3].user_email, filas[3].user_name) == (
        ana.id,
        ANA_EMAIL,
        ANA_NOMBRE,
    )
    assert (filas[5].user_email, filas[5].user_name) == (JUAN_EMAIL, JUAN_NOMBRE)
    assert (filas[1].user_id, filas[1].user_email, filas[1].user_name) == (
        SYSTEM_USER_ID,
        "system@apex.local",
        "Sistema",
    )


async def test_las_filas_no_traen_before_ni_after(
    session: AsyncSession, actividad: Actividad
) -> None:
    for fila in (await _lista(session)).items:
        volcado = fila.model_dump(mode="json")
        assert "before" not in volcado and "after" not in volcado
        assert "apx1." not in repr(volcado)


async def test_los_campos_de_cada_fila(session: AsyncSession, actividad: Actividad) -> None:
    filas = {f.seq: f for f in (await _lista(session)).items}
    assert (filas[6].action, filas[6].table_name, filas[6].record_id) == (
        "reveal",
        "members.members",
        actividad.member_id,
    )
    assert filas[6].subject_member_id == actividad.member_id
    assert (filas[3].record_id, filas[3].subject_member_id) == (actividad.plan_id, None)


async def test_un_usuario_que_no_existe_sale_sin_correo_ni_nombre(
    audit_chain_factory: CadenaDePrueba, actividad: Actividad
) -> None:
    desconocido = UUID("0000000a-0000-4000-8000-0000000b4404")
    await audit_chain_factory.make(1, user_id=desconocido)
    pagina = await _lista(audit_chain_factory.session, user_id=desconocido)
    [fila] = pagina.items
    assert (fila.seq, fila.user_email, fila.user_name) == (12, None, None)


async def test_la_consulta_no_modifica_audit_log(
    audit_chain_factory: CadenaDePrueba, actividad: Actividad
) -> None:
    session = audit_chain_factory.session
    antes = (await audit_chain_factory.digest(), await _total(session))

    await _lista(session)
    await _lista(session, q="ana", table="members.members")
    await _lista(session, PageParams(limit=1, offset=5))

    assert (await audit_chain_factory.digest(), await _total(session)) == antes


async def _total(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(AuditEntry)) or 0)
