"""Ciclo de vida de una membresía (privado, D7): congelar (B2), anular (B6) y los handlers de
pagos `on_payment_registered` y `on_payment_voided` (B4 y B5).

`freeze` (S3-B2, US-089; D3, D14, N-25), en el orden único de candados de D3 y dentro de
`session.begin_nested()` (regla transversal 5: si un paso o un handler de `MembershipFrozen`
falla, no queda congelación, ni fin corrido, ni auditoría):
1. leer la membresía sin candado para saber el socio (`MembershipNotFound` si no existe);
2. `core.locks.lock_member` (candado del socio) y `sell.lock_membership` (`FOR UPDATE` con
   `populate_existing`; `MembershipNotFound` si desapareció); `members.service.get_ref`:
   `MemberInactive` (422) si el socio está dado de baja o inactivo, como en `sell` (D21);
3. `settings.service.memberships_policy` (límites de Q9) y "hoy" de
   `current_clock().today_bogota()`;
4. congelaciones de la membresía (`queries._freeze_rows_for`, las mismas filas que lee
   `_load_freezes_for`) y `rules.apply_freeze` (`FreezeError` sale como `FreezeRejected` con su
   `code`, `message`, `field` y `status`);
5. `rules.find_overlap` del rango `[start_date, new_end_date]` contra las otras no canceladas del
   socio (`OverlapsFutureMembership` con `existing_id`);
6. insertar la `MembershipFreeze`, correr `end_date` y fijar `status = compute_status(...)` con la
   lista nueva; `flush` con `ex_memberships_member_dates` (23P01) traducida a
   `OverlapsFutureMembership` sin `existing_id` y `ex_membership_freezes_dates` (dos ventanas que
   se cruzan; con el candado de la fila no hay carrera posible) a `FreezeRejected`
   `freeze_already_scheduled`; `emit(MembershipFrozen)`. La salida lista las congelaciones en
   orden de `frozen_from` (la nueva puede ser anterior a otra ya terminada).

Partición (funciones de menos de 50 líneas): `freeze` orquesta; `_lock_for_freeze` (pasos 1 y 2),
`_apply` (paso 4), `_check_dates_of_member` (paso 5) y `_store_freeze` (paso 6).
`find_overlap` se importa al nivel del módulo y se llama por ese nombre (la prueba de la `EXCLUDE`
la reemplaza con `monkeypatch`, como `sell._check_open_memberships`).

`on_payment_registered(event, session)` (S3-B4, US-086; D11), handler de `PaymentRegistered`:
`sell.lock_membership(session, event.membership_id)` (la fila que el emisor ya bloqueó por el
gate); si no está `pending_payment`, nada. Si `covers(agreed_price_cop,
payments.service.sum_not_voided(...))` (la suma ve el pago: `register` hace `flush` antes de
emitir; nunca confía en `event.amount_cop`), fija `status = compute_status(base activa, hoy,
expiring_days, congelaciones)` con `hoy = to_bogota_date(event.occurred_at)`, hace `flush`
(auditoría `update` del usuario que pagó) y emite `MembershipActivated`. `snapshot(row)` es el
`MembershipSnapshot` de una fila (lo que leen las reglas).

Regla de candados (S3-D43, `tests/architecture/test_handlers_no_new_locks.py`): un handler `on_*`
solo vuelve a pedir la fila que el emisor ya tiene (`sell.lock_membership` con
`event.membership_id`); nunca el candado del socio ni otro `FOR UPDATE`. `freeze` no es handler:
es un caso de uso que emite, y toma los candados en el orden de D3.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import NoReturn
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock, to_bogota_date
from app.core.db import violated_constraint
from app.core.events import emit
from app.core.locks import lock_member
from app.modules.members import service as members_service
from app.modules.memberships.events import MembershipActivated, MembershipFrozen
from app.modules.memberships.exceptions import (
    FreezeRejected,
    MemberInactive,
    MembershipNotFound,
    OverlapsFutureMembership,
)
from app.modules.memberships.models import (
    EXCLUDE_NAME,
    FREEZE_EXCLUDE_NAME,
    Membership,
    MembershipFreeze,
)
from app.modules.memberships.queries import _freeze_rows_for, _load_freezes_for, membership_out
from app.modules.memberships.rules import (
    FreezeError,
    FreezeLimits,
    FreezeOutcome,
    FreezeWindow,
    MembershipSnapshot,
    MembershipStatus,
    apply_freeze,
    compute_status,
    covers,
    find_overlap,
)
from app.modules.memberships.schemas import MembershipOut
from app.modules.memberships.sell import MEMBER_ACTIVE, lock_membership
from app.modules.payments import service as payments_service
from app.modules.settings import service as settings_service
from app.modules.settings.schemas import MembershipsPolicy


@dataclass(frozen=True, slots=True)
class _FreezeContext:
    """Lo que la congelación leyó con los candados tomados: ventanas previas, política y "hoy"."""

    windows: list[FreezeWindow]
    policy: MembershipsPolicy
    today: date


async def freeze(
    session: AsyncSession, *, membership_id: UUID, frozen_from: date, frozen_to: date
) -> MembershipOut:
    """Congela la membresía `[frozen_from, frozen_to]` y corre su fin; actor de `get_actor()`."""
    async with session.begin_nested():
        membresia = await _lock_for_freeze(session, membership_id)
        filas = (await _freeze_rows_for(session, [membresia.id]))[membresia.id]
        ctx = _FreezeContext(
            windows=[FreezeWindow(fila.frozen_from, fila.frozen_to) for fila in filas],
            policy=await settings_service.memberships_policy(session),
            today=current_clock().today_bogota(),
        )
        salida = _apply(membresia, ctx, frozen_from, frozen_to)
        await _check_dates_of_member(session, membresia, salida.new_end_date)
        nueva = await _store_freeze(session, membresia, salida, ctx)
    todas = sorted([*filas, nueva], key=lambda fila: (fila.frozen_from, fila.id))
    return await membership_out(session, membresia, todas)


async def _lock_for_freeze(session: AsyncSession, membership_id: UUID) -> Membership:
    """Lee el socio sin candado y toma los candados en el orden de D3: el del socio y después
    `FOR UPDATE` de la fila (`populate_existing`). `MembershipNotFound` si no existe;
    `MemberInactive` si el socio está dado de baja o inactivo (como `sell`, D21; revisión de
    seguridad de B2, M1)."""
    member_id = await session.scalar(
        select(Membership.member_id).where(Membership.id == membership_id)
    )
    if member_id is None:
        raise MembershipNotFound()
    await lock_member(session, member_id)
    membresia = await lock_membership(session, membership_id)
    if membresia is None:
        raise MembershipNotFound()
    socio = await members_service.get_ref(session, member_id)
    if socio.is_deleted or socio.status != MEMBER_ACTIVE:
        raise MemberInactive()
    return membresia


def snapshot(row: Membership) -> MembershipSnapshot:
    """El `MembershipSnapshot` de la fila (id, estado guardado, fechas y clases restantes); no la
    cambia."""
    return MembershipSnapshot(
        id=row.id,
        status=MembershipStatus(row.status),
        start_date=row.start_date,
        end_date=row.end_date,
        classes_remaining=row.classes_remaining,
    )


def _apply(
    membresia: Membership, ctx: _FreezeContext, frozen_from: date, frozen_to: date
) -> FreezeOutcome:
    """`rules.apply_freeze` con los límites de Q9; `FreezeError` sale como `FreezeRejected`."""
    limites = FreezeLimits(
        max_days=ctx.policy.max_freeze_days_per_membership,
        max_count=ctx.policy.max_freezes_per_membership,
        max_retroactive_days=ctx.policy.max_retroactive_days,
    )
    try:
        return apply_freeze(
            snapshot(membresia),
            ctx.windows,
            frozen_from,
            frozen_to,
            limites,
            ctx.today,
            ctx.policy.expiring_days,
        )
    except FreezeError as error:
        raise FreezeRejected(
            error.code, error.message, field=error.field, status=error.status
        ) from error


async def _check_dates_of_member(
    session: AsyncSession, membresia: Membership, new_end_date: date
) -> None:
    """`[start_date, new_end_date]` contra las otras no canceladas del socio (sin la propia):
    `OverlapsFutureMembership` con el `existing_id` de la primera que choca (D14)."""
    consulta = select(
        Membership.id,
        Membership.status,
        Membership.start_date,
        Membership.end_date,
        Membership.classes_remaining,
    ).where(
        Membership.member_id == membresia.member_id,
        Membership.id != membresia.id,
        Membership.status != MembershipStatus.cancelled.value,
    )
    otras = [
        MembershipSnapshot(
            id=fila.id,
            status=MembershipStatus(fila.status),
            start_date=fila.start_date,
            end_date=fila.end_date,
            classes_remaining=fila.classes_remaining,
        )
        for fila in await session.execute(consulta)
    ]
    choque = find_overlap(membresia.start_date, new_end_date, otras)
    if choque is not None:
        raise OverlapsFutureMembership(existing_id=choque)


async def _store_freeze(
    session: AsyncSession, membresia: Membership, salida: FreezeOutcome, ctx: _FreezeContext
) -> MembershipFreeze:
    """Inserta la congelación, corre el fin y recalcula el estado con la lista nueva; `flush` con
    las `EXCLUDE` traducidas; después `emit(MembershipFrozen)`."""
    ventana = salida.window
    nueva = MembershipFreeze(
        membership_id=membresia.id,
        frozen_from=ventana.frozen_from,
        frozen_to=ventana.frozen_to,
        days=ventana.days,
    )
    session.add(nueva)
    corrida = replace(snapshot(membresia), end_date=salida.new_end_date)
    estado = compute_status(corrida, ctx.today, ctx.policy.expiring_days, [*ctx.windows, ventana])
    membresia.end_date = salida.new_end_date
    membresia.status = estado.value
    try:
        await session.flush()
    except IntegrityError as error:
        _translate_flush_error(error)
    evento = MembershipFrozen(
        membership_id=membresia.id,
        member_id=membresia.member_id,
        frozen_from=ventana.frozen_from,
        frozen_to=ventana.frozen_to,
        days=ventana.days,
        end_date=membresia.end_date,
    )
    await emit(evento, session)
    return nueva


def _translate_flush_error(error: IntegrityError) -> NoReturn:
    """La carrera que la revisión previa no vio (D8, D14): `ex_memberships_member_dates` sale como
    `OverlapsFutureMembership` sin `existing_id` (la base no lo da) y `ex_membership_freezes_dates`
    como `FreezeRejected` `freeze_already_scheduled`. Cualquier otra violación sale intacta."""
    nombre = violated_constraint(error)
    if nombre == EXCLUDE_NAME:
        raise OverlapsFutureMembership() from error
    if nombre == FREEZE_EXCLUDE_NAME:
        raise FreezeRejected("freeze_already_scheduled", status=409) from error
    raise error


async def on_payment_registered(
    event: payments_service.PaymentRegistered, session: AsyncSession
) -> None:
    """Activa la membresía del pago si quedó cubierta (D11; pasos en el docstring del módulo)."""
    membresia = await lock_membership(session, event.membership_id)
    if membresia is None or membresia.status != MembershipStatus.pending_payment.value:
        return
    pagado = await payments_service.sum_not_voided(session, membresia.id)
    if not covers(membresia.agreed_price_cop, pagado):
        return
    politica = await settings_service.memberships_policy(session)
    ventanas = (await _load_freezes_for(session, [membresia.id]))[membresia.id]
    base = replace(snapshot(membresia), status=MembershipStatus.active)
    hoy = to_bogota_date(event.occurred_at)
    estado = compute_status(base, hoy, politica.expiring_days, ventanas)
    membresia.status = estado.value
    await session.flush()
    evento = MembershipActivated(
        membership_id=membresia.id, member_id=membresia.member_id, status=estado.value
    )
    await emit(evento, session)
