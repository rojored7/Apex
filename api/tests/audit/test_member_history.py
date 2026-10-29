"""Historial del socio con datos reales (S4A-B5, US-106; S4A-D20, S4A-D45, S4A-D50, S4A-D54).

`audit_service.member_history(session, member_id, page, q)` (fachada de `queries.py`) y
`members_service.history(...)` (que la envuelve con `ensure_exists(..., include_deleted=True)`)
sobre la cadena de `sembrar_actividad` (reloj congelado en T0, cadena vaciada por
`audit_chain_factory`). Las once filas están en `test_list.py`; las de la socia Lucía son las
`subject_member_id` = socia, de la 4 a la 11. Calculadas a mano (y confirmadas una vez contra los
services con un volcado de `audit.audit_log`):

  seq accion  tabla                     quien      fields
  11  update  memberships.memberships   ana.perez  ["status"]                    (revierte)
  10  update  payments.payments         ana.perez  ["voided", "voided_at", "voided_by"]  (anula)
   9  update  memberships.memberships   juan.rios  ["status"]                    (activa)
   8  insert  payments.payments         juan.rios  []
   7  insert  memberships.memberships   ana.perez  []
   6  reveal  members.members           juan.rios  ["phone"]   purpose None (interactivo)
   5  update  members.members           juan.rios  ["email", "phone"]
   4  insert  members.members           ana.perez  []

Una congelación (pago nuevo de Juan y congelación del 21 al 27 de octubre) agrega 12 `insert`
de pago, 13 `update` de la membresía (`status`), 14 `insert` de `membership_freezes` (SIN sujeto:
no aparece) y 15 `update` de la membresía (`end_date`, `status`): la congelación se ve por la 15.
Dar de baja a la socia agrega 12 `update` de `members.members` (`deleted_at`, `status`).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditEntry, record, verify_chain
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.pagination import Page, PageParams
from app.modules.audit import queries as audit_queries
from app.modules.audit.exceptions import AuditRangeInvalid
from app.modules.audit.schemas import MemberHistoryItem
from app.modules.members import service as members_service
from app.modules.members.exceptions import MemberNotFound
from tests.audit._apoyo import (
    ANA_NOMBRE,
    IP_REVELAR,
    JUAN_NOMBRE,
    MOTIVO_ANULACION,
    PRECIO,
    Actividad,
    filas_de,
    sembrar_actividad,
)
from tests.audit.conftest import audit_service, memberships_service, payments_service
from tests.conftest import UsuarioPrueba
from tests.members._apoyo import entrada

GRANDE: Final = PageParams(limit=200)
CAMPOS_ITEM: Final = frozenset(
    {"seq", "at", "user_id", "user_name", "action", "table_name", "record_id", "fields", "purpose"}
)
SOCIOS: Final = "members.members"
MEMBRESIAS: Final = "memberships.memberships"
PAGOS: Final = "payments.payments"
# (seq, acción, tabla, quién, fields) de la socia, en seq descendente.
ESPERADO: Final = [
    (11, "update", MEMBRESIAS, ANA_NOMBRE, ["status"]),
    (10, "update", PAGOS, ANA_NOMBRE, ["voided", "voided_at", "voided_by"]),
    (9, "update", MEMBRESIAS, JUAN_NOMBRE, ["status"]),
    (8, "insert", PAGOS, JUAN_NOMBRE, []),
    (7, "insert", MEMBRESIAS, ANA_NOMBRE, []),
    (6, "reveal", SOCIOS, JUAN_NOMBRE, ["phone"]),
    (5, "update", SOCIOS, JUAN_NOMBRE, ["email", "phone"]),
    (4, "insert", SOCIOS, ANA_NOMBRE, []),
]
SEQS: Final = [fila[0] for fila in ESPERADO]


@pytest.fixture
async def actividad(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
) -> Actividad:
    return await sembrar_actividad(session, ana=ana, juan=juan)


async def _historial(
    session: AsyncSession, member_id: UUID, page: PageParams = GRANDE, q: str | None = None
) -> Page[MemberHistoryItem]:
    return await audit_service.member_history(session, member_id, page, q)


async def _seqs(session: AsyncSession, member_id: UUID, q: str | None = None) -> list[int]:
    pagina = await _historial(session, member_id, q=q)
    assert pagina.total == len(pagina.items)
    return [item.seq for item in pagina.items]


async def _total_auditoria(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(AuditEntry)) or 0)


# Orden, forma y contenido ---------------------------------------------------------------------


async def test_trae_las_entradas_de_la_socia_en_seq_descendente(
    session: AsyncSession,
    actividad: Actividad,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
) -> None:
    pagina = await _historial(session, actividad.member_id)

    assert (pagina.total, pagina.limit, pagina.offset) == (8, 200, 0)
    obtenido = [(i.seq, i.action, i.table_name, i.user_name, i.fields) for i in pagina.items]
    assert obtenido == ESPERADO
    assert all(set(i.model_dump()) == CAMPOS_ITEM for i in pagina.items)
    quien = {ANA_NOMBRE: ana.id, JUAN_NOMBRE: juan.id}
    assert all(i.user_id == quien[i.user_name or ""] for i in pagina.items)


async def test_record_id_de_cada_entrada(session: AsyncSession, actividad: Actividad) -> None:
    pagina = await _historial(session, actividad.member_id)
    por_seq = {i.seq: i.record_id for i in pagina.items}
    assert {s: por_seq[s] for s in (4, 5, 6)} == dict.fromkeys((4, 5, 6), actividad.member_id)
    assert {s: por_seq[s] for s in (7, 9, 11)} == dict.fromkeys((7, 9, 11), actividad.membership_id)
    assert {s: por_seq[s] for s in (8, 10)} == dict.fromkeys((8, 10), actividad.payment_id)


async def test_cada_entrada_tiene_el_subject_member_id_de_la_socia(
    session: AsyncSession, actividad: Actividad
) -> None:
    crudas = await filas_de(session, subject_member_id=actividad.member_id)
    assert sorted((f["seq"] for f in crudas), reverse=True) == SEQS
    assert await _seqs(session, actividad.member_id) == SEQS


async def test_purpose_es_null_en_el_reveal_interactivo(
    session: AsyncSession, actividad: Actividad
) -> None:
    pagina = await _historial(session, actividad.member_id)
    assert all(i.purpose is None for i in pagina.items)
    (revelado,) = [i for i in pagina.items if i.action == "reveal"]
    assert (revelado.seq, revelado.fields, revelado.purpose) == (6, ["phone"], None)


async def test_un_reveal_automatico_lleva_su_purpose(
    session: AsyncSession, actividad: Actividad, juan: UsuarioPrueba
) -> None:
    """M-6.3 (S4A-D50): la fila que escribirá `contact_for_notification` (B6), hecha a mano."""
    await record(
        session,
        action="reveal",
        table_name=SOCIOS,
        record_id=actividad.member_id,
        before=None,
        after={"field": "email", "purpose": "notify"},
        user_id=juan.id,
        subject_member_id=actividad.member_id,
    )
    primera = (await _historial(session, actividad.member_id)).items[0]
    assert (primera.seq, primera.action, primera.fields, primera.purpose) == (
        12,
        "reveal",
        ["email"],
        "notify",
    )


async def test_la_respuesta_serializada_no_lleva_blobs_ni_reference_ni_motivo(
    session: AsyncSession, actividad: Actividad
) -> None:
    texto = (await _historial(session, actividad.member_id)).model_dump_json()
    for prohibido in ("apx1.", "reference", "void_reason", MOTIVO_ANULACION, IP_REVELAR, "@"):
        assert prohibido not in texto, prohibido
    assert '"ip"' not in texto and "_idx" not in texto and "updated_at" not in texto


# Alcance --------------------------------------------------------------------------------------


async def test_ninguna_entrada_de_otro_socio(
    session: AsyncSession, actividad: Actividad, ana: UsuarioPrueba
) -> None:
    with actor_scope(ana.id):
        otro = await members_service.create(session, entrada(document="99887766"))
        await session.commit()

    assert await _seqs(session, actividad.member_id) == SEQS
    assert await _seqs(session, otro.id) == [12]


async def test_un_socio_sin_auditoria_da_pagina_vacia(
    session: AsyncSession, actividad: Actividad
) -> None:
    pagina = await _historial(session, uuid4())
    assert (pagina.items, pagina.total) == ([], 0)


async def test_una_congelacion_aparece_por_el_update_de_la_membresia(
    session: AsyncSession, actividad: Actividad, juan: UsuarioPrueba
) -> None:
    with actor_scope(juan.id):
        await payments_service.register(
            session,
            membership_id=actividad.membership_id,
            amount_cop=PRECIO,
            method="cash",
            role=juan.role,  # type: ignore[arg-type]
        )
        await session.commit()
    with actor_scope(juan.id):
        await memberships_service.freeze(
            session,
            membership_id=actividad.membership_id,
            frozen_from=date(2026, 10, 21),
            frozen_to=date(2026, 10, 27),
        )
        await session.commit()

    pagina = await _historial(session, actividad.member_id)

    assert [i.seq for i in pagina.items] == [15, 13, 12, *SEQS]
    congelada = pagina.items[0]
    assert (congelada.action, congelada.table_name, congelada.fields) == (
        "update",
        MEMBRESIAS,
        ["end_date", "status"],
    )
    assert congelada.record_id == actividad.membership_id
    assert all(i.table_name != "memberships.membership_freezes" for i in pagina.items)
    (congelacion,) = await filas_de(session, table_name="memberships.membership_freezes")
    assert congelacion["seq"] == 14 and congelacion["subject_member_id"] is None


async def test_abrir_la_ficha_no_agrega_entradas(
    session: AsyncSession, actividad: Actividad
) -> None:
    antes = await _total_auditoria(session)
    await members_service.get(session, actividad.member_id)
    await _historial(session, actividad.member_id)
    await members_service.history(session, actividad.member_id, GRANDE, None)
    assert await _total_auditoria(session) == antes
    assert await _seqs(session, actividad.member_id) == SEQS


async def test_un_socio_dado_de_baja_devuelve_su_historial(
    session: AsyncSession, actividad: Actividad, ana: UsuarioPrueba
) -> None:
    with actor_scope(ana.id):
        await members_service.deactivate(session, actividad.member_id)
        await session.commit()

    pagina = await members_service.history(session, actividad.member_id, GRANDE, None)

    assert [i.seq for i in pagina.items] == [12, *SEQS]
    baja = pagina.items[0]
    assert (baja.action, baja.table_name, baja.user_name, baja.fields) == (
        "update",
        SOCIOS,
        ANA_NOMBRE,
        ["deleted_at", "status"],
    )


async def test_history_de_un_socio_inexistente_da_member_not_found(
    session: AsyncSession, actividad: Actividad
) -> None:
    with pytest.raises(MemberNotFound):
        await members_service.history(session, uuid4(), GRANDE, None)


async def test_members_history_devuelve_lo_mismo_que_audit(
    session: AsyncSession, actividad: Actividad
) -> None:
    por_members = await members_service.history(session, actividad.member_id, GRANDE, None)
    por_audit = await _historial(session, actividad.member_id)
    assert por_members.model_dump() == por_audit.model_dump()


# q: parte local de quien actuó -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("q", "esperadas"),
    [
        ("juan", [9, 8, 6, 5]),
        ("JUAN.RIOS", [9, 8, 6, 5]),
        ("PÉREZ", [11, 10, 7, 4]),
        ("  ana  ", [11, 10, 7, 4]),
        ("", SEQS),
        (None, SEQS),
    ],
)
async def test_q_filtra_por_la_parte_local_de_quien_actuo(
    session: AsyncSession, actividad: Actividad, q: str | None, esperadas: list[int]
) -> None:
    assert await _seqs(session, actividad.member_id, q) == esperadas


@pytest.mark.parametrize("q", ["ejemplo", "ejemplo.local", "rios@ejemplo", "@", "local"])
async def test_q_no_filtra_por_el_dominio(
    session: AsyncSession, actividad: Actividad, q: str
) -> None:
    pagina = await _historial(session, actividad.member_id, q=q)
    assert (pagina.items, pagina.total) == ([], 0)


@pytest.mark.parametrize("q", ["juan.rios@ejemplo.local", "@", "juan@", "  @ana  "])
async def test_q_con_arroba_da_pagina_vacia_sin_buscar_usuarios(
    session: AsyncSession, actividad: Actividad, monkeypatch: pytest.MonkeyPatch, q: str
) -> None:
    """Revisión de B5 (LOW-1, S4A-D112): un `q` con `@` no es parte local; ni se consulta."""

    async def _no_debe_llamarse(*args: object, **kwargs: object) -> set[UUID]:
        raise AssertionError("search_user_ids no debe llamarse con `@`")

    monkeypatch.setattr(audit_queries.auth_service, "search_user_ids", _no_debe_llamarse)
    pagina = await _historial(session, actividad.member_id, q=q)
    assert (pagina.items, pagina.total) == ([], 0)


async def test_q_no_trae_entradas_de_otro_socio(
    session: AsyncSession, actividad: Actividad, juan: UsuarioPrueba
) -> None:
    with actor_scope(juan.id):
        otro = await members_service.create(session, entrada(document="99887766"))
        await session.commit()
    assert await _seqs(session, actividad.member_id, "juan") == [9, 8, 6, 5]
    assert await _seqs(session, otro.id, "juan") == [12]


# Paginación y rango ---------------------------------------------------------------------------


async def test_paginacion_y_total(session: AsyncSession, actividad: Actividad) -> None:
    pagina = await _historial(session, actividad.member_id, PageParams(limit=3, offset=2))
    assert ([i.seq for i in pagina.items], pagina.total) == ([9, 8, 7], 8)
    assert (pagina.limit, pagina.offset) == (3, 2)


async def test_offset_100000_da_pagina_vacia_con_total(
    session: AsyncSession, actividad: Actividad
) -> None:
    pagina = await _historial(session, actividad.member_id, PageParams(limit=25, offset=100_000))
    assert (pagina.items, pagina.total, pagina.offset) == ([], 8, 100_000)


async def test_offset_100001_da_audit_range_invalid(
    session: AsyncSession, actividad: Actividad
) -> None:
    with pytest.raises(AuditRangeInvalid) as error:
        await _historial(session, actividad.member_id, PageParams(limit=25, offset=100_001))
    assert error.value.field == "offset"


async def test_total_se_satura_en_max_audit_offset_mas_uno(
    session: AsyncSession, actividad: Actividad, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S4A-D106 b (duda 3 de B5): el mismo conteo acotado que `GET /audit`."""
    monkeypatch.setattr(audit_queries, "MAX_AUDIT_OFFSET", 5)
    pagina = await _historial(session, actividad.member_id, PageParams(limit=3, offset=3))
    assert ([i.seq for i in pagina.items], pagina.total) == ([8, 7, 6], 6)
    filtrada = await _historial(session, actividad.member_id, PageParams(limit=3), q="juan")
    assert filtrada.total == 4


async def test_socio_inexistente_con_offset_fuera_de_rango_da_member_not_found(
    session: AsyncSession, actividad: Actividad
) -> None:
    """Duda 4 de B5: `ensure_exists` va antes del rango, así que el 404 manda sobre el 422."""
    with pytest.raises(MemberNotFound):
        await members_service.history(session, uuid4(), PageParams(limit=25, offset=100_001), None)


async def test_la_consulta_no_modifica_la_cadena_y_sigue_integra(
    session: AsyncSession, actividad: Actividad
) -> None:
    antes = await filas_de(session)
    await _historial(session, actividad.member_id)
    await _historial(session, actividad.member_id, q="juan")
    despues = await filas_de(session)
    assert despues == antes
    resultado = verify_chain(despues)
    assert (resultado.ok, resultado.rows_checked) == (True, 11)


def _sin_valores(item: dict[str, Any]) -> bool:
    return all(isinstance(campo, str) and "apx1." not in campo for campo in item["fields"])


async def test_fields_son_solo_nombres(session: AsyncSession, actividad: Actividad) -> None:
    pagina = await _historial(session, actividad.member_id)
    assert all(_sin_valores(i.model_dump()) for i in pagina.items)
