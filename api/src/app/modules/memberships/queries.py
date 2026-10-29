"""Lecturas de membresías (S3-B1: `refs_for`; B7 agrega listas, resumen y estados). Privado (D7).

- `refs_for(session, membership_ids)`: por cada id existente, `MembershipRef` con el nombre del
  socio (`members.service.names_for`, incluye dados de baja), el del plan
  (`plans.service.names_for`, incluye dados de baja) y las fechas. Consulta `memberships` en lotes
  de `core.pagination.ID_BATCH` con `chunked` (S3-D59); sin ids no consulta nada.
- `_freeze_rows_for(session, ids)`: las filas de `memberships.membership_freezes` de cada id, en
  orden de `frozen_from` (S3-B2, D6: sin `relationship()`), en lotes de `ID_BATCH`; todo id pedido
  aparece en el resultado (lista vacía si no tiene congelaciones).
- `_load_freezes_for(session, ids)`: las mismas, como `rules.FreezeWindow` (lo que leen
  `compute_status` y `apply_freeze`); la usan `sell` y `freeze`.
- `freeze_out(fila)` y `membership_out(session, membresia, freezes)`: la salida `MembershipOut`
  con el nombre del socio y del plan (`names_for` de cada módulo dueño), `paid_cop`
  (`payments.service.sum_not_voided`, S3-B4) y, desde la revisión de Fase 4 del Sprint 3 (PM4,
  S3-D91), el estado EFECTIVO (D5) con la política y el "hoy" del reloj: `get`, `freeze` y
  `cancel` lo usan y responden lo mismo que la lista.
- `row_fields(...)` y `out_fields(...)` (PM4): los campos de `MembershipRow` y de `MembershipOut`
  desde la fila del ORM; los únicos constructores de las dos salidas (también de la de `sell`).

S3-B7 (US-091, US-092; D5, D18, M-4, M-10, S3-D53, S3-D60, E11, E13). `list` sombrea al
`list` de Python en este archivo: las anotaciones y llamadas usan `builtins.list`.
- `status_expr(today, expiring_days)`: el `CASE` de SQLAlchemy espejo de `rules.compute_status`
  (cancelada y pendiente de pago de lo guardado; congelada si una fila de `membership_freezes`
  del mismo esquema contiene `today`; vencida si `today > end_date` o `classes_remaining = 0`;
  por vencer si `end_date - today <= expiring_days`; si no, al día). `today` va como
  `literal(today, Date)`. Paridad: `tests/memberships/test_status_expr_parity.py`.
- `member_status_rank_expr(today, expiring_days)`: la posición en `rules.MEMBER_STATUS_PRIORITY`
  de la categoría de cada fila no cancelada (0 vigente, 1 pendiente de pago, 2 vencida, 3
  futura), sobre `status_expr`: el orden del `DISTINCT ON (member_id)` del resumen y de las
  consultas de estado. Oráculo: `rules.resolve_member_status`.
- `list(session, filters, page) -> Page[MembershipRow]` (D18): `rules.parse_status_filter`
  (sin `status`, excluye `cancelled`), fechas de fin entre `ENDS_FLOOR` y hoy más
  `ENDS_CEILING_YEARS` años (`DateRangeInvalid` con el campo que falla; invertidas en
  `ends_to`), `q` con `members.service.search_ids(include_deleted=True)` (sin coincidencias,
  página vacía), `plan_id`, `member_id`; orden `end_date, id`; nombres, sumas no anuladas y
  estado efectivo por lote (una consulta por servicio vecino por página). Nunca descifra.
- `get(session, membership_id) -> MembershipOut` (`MembershipNotFound`): con sus congelaciones y
  el estado EFECTIVO (D5), como la fila de la lista.
- `list_for_member(session, member_id, page, *, q=None) -> Page[MembershipOut]` (S3-B11, US-093,
  D28): la pestaña de la ficha (docstring de la función).
- `_summary_counts(session, member_ids, today, expiring_days)` y `SUMMARY_FIELDS`: una
  sentencia con `DISTINCT ON (member_id)` ordenado por `member_status_rank_expr` y
  `count(*) FILTER` por estado; la usa `summary.py` (el resumen y su caché de proceso, que se
  separaron de este archivo en la revisión de Fase 4 del Sprint 3, S3-D90).
- `status_for(session, member_ids, *, today=None) -> dict[UUID, MemberMembership]`: el estado
  del socio y la membresía que lo decide, en lotes de `ID_BATCH`; los ids sin membresías no
  canceladas no aparecen (el llamador usa `none`).
- `member_ids_by_status(session, statuses, plan_id=None, *, today=None) -> set[UUID]`: socios
  cuyo estado resuelto está en `statuses`; `plan_id` filtra por el plan de la membresía que
  decide. El complemento `none` lo calcula `members`.
- `count_active_by_plan(session, plan_id) -> int`: membresías del plan con estado EFECTIVO
  distinto de `cancelled` y de `expired` (G-04, N-22 sobre D5).
- S4A-B7 (S4A-D25): `counts_active_by_plans(session, plan_ids) -> dict[UUID, int]`: el mismo
  conteo por lote (`GROUP BY plan_id`, trozos de `ID_BATCH`); todo id pedido aparece (0 si no
  tiene); sin ids no consulta.
"""

from __future__ import annotations

import builtins
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any, Final
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Date,
    Integer,
    Row,
    Subquery,
    Text,
    case,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.pagination import Page, PageParams, any_uuids, chunked, paginate, to_page
from app.modules.members import service as members_service
from app.modules.memberships.exceptions import DateRangeInvalid, MembershipNotFound
from app.modules.memberships.models import Membership, MembershipFreeze
from app.modules.memberships.rules import (
    MEMBER_STATUS_PRIORITY,
    FreezeWindow,
    MembershipStatus,
    compute_status,
    parse_status_filter,
    snapshot,
)
from app.modules.memberships.schemas import (
    FreezeOut,
    MemberMembership,
    MembershipListQuery,
    MembershipOut,
    MembershipRef,
    MembershipRow,
)
from app.modules.payments import service as payments_service
from app.modules.plans import service as plans_service
from app.modules.settings import service as settings_service


async def refs_for(
    session: AsyncSession, membership_ids: Iterable[UUID]
) -> dict[UUID, MembershipRef]:
    """Nombre del socio, del plan y fechas por id de membresía existente (incluye dados de baja).

    Una consulta a `memberships.memberships` por lote de `ID_BATCH` y una a cada módulo dueño de
    los nombres. Socios y planes nunca se borran físicamente (regla de datos 4); si faltara el
    nombre de alguno, esa membresía no aparece en el resultado.
    """
    buscados = builtins.list(dict.fromkeys(membership_ids))
    if not buscados:
        return {}
    filas: builtins.list[Row[*tuple[Any, ...]]] = []
    for lote in chunked(buscados):
        consulta = select(
            Membership.id,
            Membership.member_id,
            Membership.plan_id,
            Membership.start_date,
            Membership.end_date,
        ).where(Membership.id.in_(lote))
        filas.extend((await session.execute(consulta)).all())
    if not filas:
        return {}
    socios = await members_service.names_for(session, (fila.member_id for fila in filas))
    planes = await plans_service.names_for(session, (fila.plan_id for fila in filas))
    return {
        fila.id: MembershipRef(
            member_id=fila.member_id,
            member_first_name=socios[fila.member_id].first_name,
            member_last_name=socios[fila.member_id].last_name,
            plan_name=planes[fila.plan_id],
            start_date=fila.start_date,
            end_date=fila.end_date,
        )
        for fila in filas
        if fila.member_id in socios and fila.plan_id in planes
    }


async def _freeze_rows_for(
    session: AsyncSession, membership_ids: Iterable[UUID]
) -> dict[UUID, builtins.list[MembershipFreeze]]:
    """Congelaciones por id de membresía (D6), en orden de `frozen_from`; una consulta por lote de
    `ID_BATCH`. Todo id pedido tiene su lista (vacía si no tiene congelaciones)."""
    buscados = builtins.list(dict.fromkeys(membership_ids))
    salida: dict[UUID, builtins.list[MembershipFreeze]] = {
        membership_id: [] for membership_id in buscados
    }
    for lote in chunked(buscados):
        consulta = (
            select(MembershipFreeze)
            .where(MembershipFreeze.membership_id.in_(lote))
            .order_by(MembershipFreeze.frozen_from, MembershipFreeze.id)
        )
        for fila in await session.scalars(consulta):
            salida[fila.membership_id].append(fila)
    return salida


async def _load_freezes_for(
    session: AsyncSession, membership_ids: Iterable[UUID]
) -> dict[UUID, builtins.list[FreezeWindow]]:
    """Congelaciones por id (D6), en orden de `frozen_from`, como ventanas de las reglas."""
    filas = await _freeze_rows_for(session, membership_ids)
    return {
        membership_id: [FreezeWindow(fila.frozen_from, fila.frozen_to) for fila in lista]
        for membership_id, lista in filas.items()
    }


def freeze_out(fila: MembershipFreeze) -> FreezeOut:
    return FreezeOut(
        id=fila.id,
        frozen_from=fila.frozen_from,
        frozen_to=fila.frozen_to,
        days=fila.days,
        created_at=fila.created_at,
    )


def row_fields(
    m: Membership, *, member_name: str, plan_name: str, paid_cop: int, status: MembershipStatus
) -> dict[str, Any]:
    """Los campos de `MembershipRow` (PM4): la base de toda salida de una membresía."""
    return {
        "id": m.id,
        "member_id": m.member_id,
        "member_name": member_name,
        "plan_id": m.plan_id,
        "plan_name": plan_name,
        "agreed_price_cop": m.agreed_price_cop,
        "paid_cop": paid_cop,
        "start_date": m.start_date,
        "end_date": m.end_date,
        "classes_total": m.classes_total,
        "classes_remaining": m.classes_remaining,
        "status": status,
    }


def out_fields(
    m: Membership,
    *,
    member_name: str,
    plan_name: str,
    paid_cop: int,
    status: MembershipStatus,
    freezes: Iterable[MembershipFreeze],
) -> dict[str, Any]:
    """Los campos de `MembershipOut` (PM4): los de la fila más congelaciones y anulación."""
    return {
        **row_fields(
            m, member_name=member_name, plan_name=plan_name, paid_cop=paid_cop, status=status
        ),
        "freezes": [freeze_out(fila) for fila in freezes],
        "cancel_reason": m.cancel_reason,
        "cancelled_at": m.cancelled_at,
        "created_at": m.created_at,
    }


def _effective(
    m: Membership, freezes: Iterable[MembershipFreeze], today: date, expiring_days: int
) -> MembershipStatus:
    """El estado EFECTIVO de la fila con sus congelaciones (D5)."""
    ventanas = [FreezeWindow(fila.frozen_from, fila.frozen_to) for fila in freezes]
    return compute_status(snapshot(m), today, expiring_days, ventanas)


async def membership_out(
    session: AsyncSession, membresia: Membership, freezes: Iterable[MembershipFreeze]
) -> MembershipOut:
    """`MembershipOut` de una membresía con sus congelaciones (en el orden dado) y su estado
    EFECTIVO de hoy (D5, PM4). Socios y planes nunca se borran físicamente (regla de datos 4): si
    faltara un nombre, el `KeyError` es la señal de un defecto, no un caso de negocio. `paid_cop`
    es la suma de los pagos no anulados (S3-B4)."""
    filas = builtins.list(freezes)
    socio = (await members_service.names_for(session, [membresia.member_id]))[membresia.member_id]
    plan_name = (await plans_service.names_for(session, [membresia.plan_id]))[membresia.plan_id]
    hoy, dias = await _today_and_expiring_days(session, None)
    campos = out_fields(
        membresia,
        member_name=f"{socio.first_name} {socio.last_name}",
        plan_name=plan_name,
        paid_cop=await payments_service.sum_not_voided(session, membresia.id),
        status=_effective(membresia, filas, hoy, dias),
        freezes=filas,
    )
    return MembershipOut(**campos)


# Listas, resumen y consultas de estado (S3-B7) ---------------------------------------------------

ENDS_FLOOR: Final = date(2020, 1, 1)
"""Piso de `ends_from` y `ends_to` (M-4, S3-D47: el sistema no existe antes)."""
ENDS_CEILING_YEARS: Final = 5
"""Techo de `ends_from` y `ends_to`: hoy más 5 años (M-4, S3-D47)."""


# Estado derivado en SQL (D5) ----------------------------------------------------------------------


def _frozen_on(hoy: ColumnElement[date]) -> ColumnElement[bool]:
    """Hay una congelación de la fila de `memberships` que contiene `hoy` (mismo esquema)."""
    return (
        exists()
        .where(
            MembershipFreeze.membership_id == Membership.id,
            MembershipFreeze.frozen_from <= hoy,
            MembershipFreeze.frozen_to >= hoy,
        )
        .correlate(Membership)
    )


def status_expr(today: date, expiring_days: int) -> ColumnElement[str]:
    """`CASE` espejo de `rules.compute_status` (docstring del módulo)."""
    if expiring_days < 0:
        raise ValueError("expiring_days no puede ser negativo")
    hoy = literal(today, Date)
    return case(
        (Membership.status == MembershipStatus.cancelled.value, Membership.status),
        (Membership.status == MembershipStatus.pending_payment.value, Membership.status),
        (_frozen_on(hoy), literal(MembershipStatus.frozen.value, Text)),
        (
            or_(Membership.end_date < hoy, Membership.classes_remaining == 0),
            literal(MembershipStatus.expired.value, Text),
        ),
        (
            Membership.end_date - hoy <= literal(expiring_days, Integer),
            literal(MembershipStatus.expiring.value, Text),
        ),
        else_=literal(MembershipStatus.active.value, Text),
    )


def member_status_rank_expr(today: date, expiring_days: int) -> ColumnElement[int]:
    """Rango de prioridad de US-092 de cada fila no anulada (docstring del módulo)."""
    estado = status_expr(today, expiring_days)
    posicion = MEMBER_STATUS_PRIORITY.index
    return case(
        (
            estado == MembershipStatus.pending_payment.value,
            literal(posicion("pending_payment"), Integer),
        ),
        (estado == MembershipStatus.expired.value, literal(posicion("expired"), Integer)),
        (Membership.start_date <= literal(today, Date), literal(posicion("current"), Integer)),
        else_=literal(posicion("future"), Integer),
    )


def _deciding(
    today: date, expiring_days: int, member_ids: Iterable[UUID] | None = None
) -> Subquery:
    """La membresía que decide el estado de cada socio (US-092): `DISTINCT ON (member_id)` sobre
    las no anuladas, ordenado por `member_status_rank_expr` y el fin (y el inicio) más tardío.
    Columnas `member_id`, `plan_id`, `end_date` y `estado` (el estado efectivo)."""
    consulta = select(
        Membership.member_id,
        Membership.plan_id,
        Membership.end_date,
        status_expr(today, expiring_days).label("estado"),
    ).where(Membership.status != MembershipStatus.cancelled.value)
    if member_ids is not None:
        consulta = consulta.where(Membership.member_id == any_uuids(member_ids))
    return (
        consulta.order_by(
            Membership.member_id,
            member_status_rank_expr(today, expiring_days),
            Membership.end_date.desc(),
            Membership.start_date.desc(),
        )
        .ext(distinct_on(Membership.member_id))
        .subquery("decide")
    )


async def _today_and_expiring_days(session: AsyncSession, today: date | None) -> tuple[date, int]:
    """ "Hoy" (el pedido o el de Bogotá del reloj) y `expiring_days` de la política (Q4)."""
    politica = await settings_service.memberships_policy(session)
    return today or current_clock().today_bogota(), politica.expiring_days


# Lista y detalle (US-091) -------------------------------------------------------------------------


def _ends_ceiling(today: date) -> date:
    """Hoy más `ENDS_CEILING_YEARS` años (un 29 de febrero pasa al 28)."""
    try:
        return today.replace(year=today.year + ENDS_CEILING_YEARS)
    except ValueError:
        return today.replace(year=today.year + ENDS_CEILING_YEARS, day=28)


def _check_ends(filters: MembershipListQuery, today: date) -> None:
    """M-4 (S3-D47): cada `ends_*` en `[ENDS_FLOOR, hoy + 5 años]`; después, sin invertir."""
    techo = _ends_ceiling(today)
    for campo, valor in (("ends_from", filters.ends_from), ("ends_to", filters.ends_to)):
        if valor is not None and not ENDS_FLOOR <= valor <= techo:
            raise DateRangeInvalid(field=campo)
    if filters.ends_from and filters.ends_to and filters.ends_from > filters.ends_to:
        raise DateRangeInvalid(field="ends_to")


def _list_conditions(
    filters: MembershipListQuery,
    statuses: frozenset[MembershipStatus] | None,
    member_ids: set[UUID] | None,
    today: date,
    expiring_days: int,
) -> builtins.list[ColumnElement[bool]]:
    condiciones: builtins.list[ColumnElement[bool]] = []
    if statuses is None:
        condiciones.append(Membership.status != MembershipStatus.cancelled.value)
    else:
        valores = sorted(estado.value for estado in statuses)
        condiciones.append(status_expr(today, expiring_days).in_(valores))
    if member_ids is not None:
        condiciones.append(Membership.member_id == any_uuids(member_ids))
    if filters.member_id is not None:
        condiciones.append(Membership.member_id == filters.member_id)
    if filters.plan_id is not None:
        condiciones.append(Membership.plan_id == filters.plan_id)
    if filters.ends_from is not None:
        condiciones.append(Membership.end_date >= filters.ends_from)
    if filters.ends_to is not None:
        condiciones.append(Membership.end_date <= filters.ends_to)
    return condiciones


async def _rows_for(
    session: AsyncSession, filas: Sequence[Membership], today: date, expiring_days: int
) -> builtins.list[MembershipRow]:
    """`MembershipRow` de la página: una sentencia a cada vecino (nombres de socios y planes,
    sumas no anuladas) y una de congelaciones para el estado efectivo (S3-D59)."""
    ids = [m.id for m in filas]
    socios = await members_service.names_for(session, (m.member_id for m in filas))
    planes = await plans_service.names_for(session, (m.plan_id for m in filas))
    pagado = await payments_service.sums_not_voided(session, ids)
    congelaciones = await _freeze_rows_for(session, ids)
    return [
        MembershipRow(
            **row_fields(
                m,
                member_name=f"{socios[m.member_id].first_name} {socios[m.member_id].last_name}",
                plan_name=planes[m.plan_id],
                paid_cop=pagado.get(m.id, 0),
                status=_effective(m, congelaciones[m.id], today, expiring_days),
            )
        )
        for m in filas
    ]


async def list(  # nombre del contrato del blueprint B7 (las anotaciones usan builtins.list)
    session: AsyncSession, filters: MembershipListQuery, page: PageParams
) -> Page[MembershipRow]:
    """US-091: la página de membresías filtrada (docstring del módulo). Nunca descifra."""
    hoy = current_clock().today_bogota()
    estados = parse_status_filter(filters.status)
    _check_ends(filters, hoy)
    socios: set[UUID] | None = None
    if filters.q is not None and filters.q.strip():
        socios = await members_service.search_ids(session, filters.q, include_deleted=True)
        if not socios:
            return to_page([], 0, page)
    hoy, dias = await _today_and_expiring_days(session, hoy)
    consulta = (
        select(Membership)
        .where(*_list_conditions(filters, estados, socios, hoy, dias))
        .order_by(Membership.end_date, Membership.id)
    )
    filas, total = await paginate(session, consulta, page)
    return to_page(await _rows_for(session, filas, hoy, dias), total, page)


async def get(session: AsyncSession, membership_id: UUID) -> MembershipOut:
    """Detalle de una membresía con sus congelaciones y el estado EFECTIVO (D5);
    `MembershipNotFound` si no existe."""
    membresia = await session.get(Membership, membership_id)
    if membresia is None:
        raise MembershipNotFound()
    filas = (await _freeze_rows_for(session, [membresia.id]))[membresia.id]
    return await membership_out(session, membresia, filas)


async def list_for_member(
    session: AsyncSession, member_id: UUID, page: PageParams, *, q: str | None = None
) -> Page[MembershipOut]:
    """S3-B11 (US-093, D28): la pestaña de membresías de la ficha. `MemberNotFound` si el socio
    no existe (`members.ensure_exists(include_deleted=True)`: un dado de baja ve las suyas);
    orden `start_date DESC, id`; incluye anuladas; congelaciones, nombres, `paid_cop` y estado
    efectivo por lote; `q` filtra por nombre de plan (`plans.search_ids`). Nunca descifra."""
    await members_service.ensure_exists(session, member_id, include_deleted=True)  # 404 primero
    condiciones: builtins.list[ColumnElement[bool]] = [Membership.member_id == member_id]
    if q is not None and q.strip():
        planes = await plans_service.search_ids(session, q)
        if not planes:
            return to_page([], 0, page)
        condiciones.append(Membership.plan_id == any_uuids(planes))
    hoy, dias = await _today_and_expiring_days(session, None)
    consulta = (
        select(Membership).where(*condiciones).order_by(Membership.start_date.desc(), Membership.id)
    )
    filas, total = await paginate(session, consulta, page)
    return to_page(await _member_outs(session, filas, hoy, dias), total, page)


async def _member_outs(
    session: AsyncSession, filas: Sequence[Membership], today: date, expiring_days: int
) -> builtins.list[MembershipOut]:
    """`MembershipOut` de la página con el estado EFECTIVO (D5): una sentencia a cada vecino
    (nombres de socios y planes, sumas no anuladas) y una de congelaciones; nunca
    `membership_out` por fila (sería N+1)."""
    ids = [m.id for m in filas]
    socios = await members_service.names_for(session, (m.member_id for m in filas))
    planes = await plans_service.names_for(session, (m.plan_id for m in filas))
    pagado = await payments_service.sums_not_voided(session, ids)
    congelaciones = await _freeze_rows_for(session, ids)
    return [
        MembershipOut(
            **out_fields(
                m,
                member_name=f"{socios[m.member_id].first_name} {socios[m.member_id].last_name}",
                plan_name=planes[m.plan_id],
                paid_cop=pagado.get(m.id, 0),
                status=_effective(m, congelaciones[m.id], today, expiring_days),
                freezes=congelaciones[m.id],
            )
        )
        for m in filas
    ]


# Resumen (US-092; S3-D53, S3-D60, E11) ------------------------------------------------------------

SUMMARY_FIELDS: Final = ("active", "expiring", "expired", "frozen", "pending_payment")


async def _summary_counts(
    session: AsyncSession, member_ids: Sequence[UUID], today: date, expiring_days: int
) -> dict[str, int]:
    """Una sentencia: por estado resuelto, cuántos de `member_ids` hay (`count(*) FILTER`)."""
    decide = _deciding(today, expiring_days, member_ids)
    consulta = select(
        *(func.count().filter(decide.c.estado == campo).label(campo) for campo in SUMMARY_FIELDS)
    ).select_from(decide)
    fila = (await session.execute(consulta)).one()
    return {campo: int(getattr(fila, campo)) for campo in SUMMARY_FIELDS}


# Consultas de estado para otros módulos (US-092 criterio 5, US-071, N-22) ------------------------


async def status_for(
    session: AsyncSession, member_ids: Iterable[UUID], *, today: date | None = None
) -> dict[UUID, MemberMembership]:
    """Estado de membresía de cada socio pedido y la membresía que lo decide (docstring del
    módulo). Sin ids no envía ninguna sentencia."""
    buscados = builtins.list(dict.fromkeys(member_ids))
    if not buscados:
        return {}
    hoy, dias = await _today_and_expiring_days(session, today)
    filas: builtins.list[Row[*tuple[Any, ...]]] = []
    for lote in chunked(buscados):
        decide = _deciding(hoy, dias, lote)
        filas.extend((await session.execute(select(decide))).all())
    planes = await plans_service.names_for(session, (fila.plan_id for fila in filas))
    return {
        fila.member_id: MemberMembership(
            status=fila.estado,
            plan_id=fila.plan_id,
            plan_name=planes[fila.plan_id],
            end_date=fila.end_date,
        )
        for fila in filas
    }


async def member_ids_by_status(
    session: AsyncSession,
    statuses: Iterable[str],
    plan_id: UUID | None = None,
    *,
    today: date | None = None,
) -> set[UUID]:
    """Socios cuyo estado resuelto está en `statuses`; `plan_id` filtra por el plan de la
    membresía que decide (docstring del módulo). Con `statuses` vacío, `set()` sin consultar."""
    buscados = sorted(set(statuses))
    if not buscados:
        return set()
    hoy, dias = await _today_and_expiring_days(session, today)
    decide = _deciding(hoy, dias)
    consulta = select(decide.c.member_id).where(decide.c.estado.in_(buscados))
    if plan_id is not None:
        consulta = consulta.where(decide.c.plan_id == plan_id)
    return set(await session.scalars(consulta))


def _active_effective() -> ColumnElement[bool]:
    """Estado EFECTIVO distinto de `cancelled` y de `expired` (G-04, N-22 sobre D5).
    `expiring_days` no cambia si una fila es `cancelled` o `expired`: va 0 y no se lee la
    política."""
    excluidos = (MembershipStatus.cancelled.value, MembershipStatus.expired.value)
    return status_expr(current_clock().today_bogota(), 0).not_in(excluidos)


async def count_active_by_plan(session: AsyncSession, plan_id: UUID) -> int:
    """Membresías del plan con estado EFECTIVO distinto de `cancelled` y de `expired` (G-04,
    N-22 sobre D5)."""
    consulta = (
        select(func.count())
        .select_from(Membership)
        .where(Membership.plan_id == plan_id, _active_effective())
    )
    return int(await session.scalar(consulta) or 0)


async def counts_active_by_plans(
    session: AsyncSession, plan_ids: Iterable[UUID]
) -> dict[UUID, int]:
    """S4A-D25: `count_active_by_plan` por lote (docstring del módulo): `GROUP BY plan_id` en
    trozos de `ID_BATCH`; todo id pedido aparece (0 si no tiene); sin ids no consulta."""
    buscados = builtins.list(dict.fromkeys(plan_ids))
    salida: dict[UUID, int] = dict.fromkeys(buscados, 0)
    for lote in chunked(buscados):
        consulta = (
            select(Membership.plan_id, func.count())
            .where(Membership.plan_id == any_uuids(lote), _active_effective())
            .group_by(Membership.plan_id)
        )
        for plan_id, cantidad in await session.execute(consulta):
            salida[plan_id] = int(cantidad)
    return salida
