"""Medidas corporales (S9-A1, US-178; S9-D3, S9-D4, S9-D15, S9-D29, S9-D32).

- `add_metric`: valida, comprueba que el socio exista y tenga autorización de datos (409
  `consent_required` ANTES de codificar y cifrar: cero filas `encrypt`, H-1) y guarda un blob
  `athlete.metric` por columna con el claro de ancho fijo de `rules.encode_metric`.
- `list_metrics`: solo las marcas `has_*`; no descifra ni audita (funciona con el custodio sellado).
- `_decrypt_metric_field`: la ÚNICA llamada de `athletes` a `types.reveal` (tercera puerta, S9-D15,
  L-2): un solo campo de la tupla de cuatro, `purpose: Literal["reveal"]` y rechazo de la fila
  anulada dentro de la puerta; un blob que no decodifica lanza `MetricDecodeError` (opaco).
"""

from __future__ import annotations

import logging
from typing import Final, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.clock import current_clock
from app.core.context import get_actor
from app.core.crypto import types
from app.core.crypto.secret import Secret
from app.core.errors import ForbiddenError
from app.core.locks import lock_member
from app.core.pagination import Page, PageParams, paginate, to_page
from app.modules.athletes.exceptions import ConsentRequired, MetricNotFound, MetricVoided
from app.modules.athletes.models import BodyMetric
from app.modules.athletes.rules import METRIC_FIELDS, decode_metric, encode_metric, validate_metric
from app.modules.athletes.schemas import MetricIn, MetricOut, MetricRevealOut
from app.modules.auth import service as auth_service
from app.modules.members import service as members_service

logger = logging.getLogger("app.athletes")

REVEAL_PURPOSE: Final = "reveal"
ADMIN_ROLE: Final = "admin"
METRICS_TABLE: Final = "athletes.body_metrics"


def _seal(field: str, value: int | str | None) -> Secret | None:
    return None if value is None else Secret.from_plain(encode_metric(field, value))


def _to_out(metric: BodyMetric, names: dict[UUID, str]) -> MetricOut:
    return MetricOut(
        id=metric.id,
        measured_on=metric.measured_on,
        has_weight=metric.weight_g is not None,
        has_height=metric.height_cm is not None,
        has_body_fat=metric.body_fat_pct is not None,
        has_notes=metric.notes is not None,
        recorded_by=metric.recorded_by,
        recorded_by_name=names.get(metric.recorded_by),
        voided_at=metric.voided_at,
        created_at=metric.created_at,
    )


async def add_metric(
    session: AsyncSession, member_id: UUID, data: MetricIn, *, by: UUID
) -> MetricOut:
    """Registra una medición. 422 sin repetir el valor; 404 `member_not_found` (inexistente o
    dado de baja, S9-D14); 409 `consent_required` sin autorización de datos (S9-D29). Toma el
    candado del socio ANTES de comprobar que existe (L-A: una baja simultánea no deja una medición
    en un socio dado de baja; orden único de candados de `core/locks.py`)."""
    validate_metric(
        measured_on=data.measured_on,
        weight_g=data.weight_g,
        height_cm=data.height_cm,
        body_fat_pct=data.body_fat_pct,
        notes=data.notes,
        today=current_clock().today_bogota(),
    )
    await lock_member(session, member_id)
    await members_service.ensure_exists(session, member_id)
    if member_id in await members_service.consent_missing_for(session, [member_id]):
        raise ConsentRequired()
    metric = BodyMetric(
        created_by=by,
        member_id=member_id,
        measured_on=data.measured_on,
        recorded_by=by,
        weight_g=_seal("weight_g", data.weight_g),
        height_cm=_seal("height_cm", data.height_cm),
        body_fat_pct=_seal("body_fat_pct", data.body_fat_pct),
        notes=_seal("notes", data.notes),
    )
    session.add(metric)
    await session.flush()
    names = await auth_service.user_names_for(session, [by])
    return _to_out(metric, names)


async def list_metrics(
    session: AsyncSession, member_id: UUID, page: PageParams, *, include_voided: bool = False
) -> Page[MetricOut]:
    """Mediciones del socio (también dado de baja), por fecha y alta descendentes."""
    await members_service.ensure_exists(session, member_id, include_deleted=True)
    consulta = select(BodyMetric).where(BodyMetric.member_id == member_id)
    if not include_voided:
        consulta = consulta.where(BodyMetric.voided_at.is_(None))
    filas, total = await paginate(
        session,
        consulta.order_by(BodyMetric.measured_on.desc(), BodyMetric.created_at.desc()),
        page,
    )
    names = await auth_service.user_names_for(session, list({f.recorded_by for f in filas}))
    return to_page([_to_out(f, names) for f in filas], total, page)


def _decrypt_metric_field(
    metric: BodyMetric, field: str, purpose: Literal["reveal"]
) -> int | str | None:
    """Única puerta de descifrado de las medidas. `ValueError` si el campo no es UNO de los
    cuatro o el propósito no es `reveal`; `MetricVoided` si la fila está anulada (sin descifrar);
    `MetricDecodeError` si el claro no decodifica (marca ajena, largo o dígitos); `TypeError` si
    `metric` no es una `BodyMetric` (L-D: se comprueba primero)."""
    if not isinstance(metric, BodyMetric):
        raise TypeError("la puerta solo descifra mediciones")
    if not isinstance(field, str) or field not in METRIC_FIELDS:
        raise ValueError("campo de medida inválido")
    if purpose != REVEAL_PURPOSE:
        raise ValueError("purpose de medida inválido")
    if metric.voided_at is not None:
        raise MetricVoided()
    claro = types.reveal(metric, field, purpose)
    if claro is None:
        return None
    if not isinstance(claro, str):
        raise ValueError("campo de medida inválido")
    return decode_metric(field, claro)


async def reveal_metric(
    session: AsyncSession,
    member_id: UUID,
    metric_id: UUID,
    field: str,
    *,
    ip: str,
    role: str,
) -> MetricRevealOut:
    """El valor en claro de UN campo de una medición (US-179; S9-D15, S9-D34).

    `MemberNotFound` si el socio no existe; `MetricNotFound` (404) si la medición no existe o es de
    otro socio, sin delatar que existe; `ForbiddenError` (403) si el socio está dado de baja y quien
    llama no es admin (M-4), sin descifrar; `MetricVoided` (409) si está anulada. La fila se relee
    con `populate_existing` y `FOR SHARE` DENTRO de la transacción: una copia vieja de la sesión no
    engaña y una anulación concurrente espera a que este `reveal` confirme (o cae en 503 `busy`).
    Deja una fila `reveal` en la auditoría (`after = {"field", "ip"}`, nunca el valor) y, si el
    campo tiene valor, una `decrypt` de `crypto_ops`; un campo vacío da `None`, audita y no
    descifra. Un blob que no decodifica sube como `MetricDecodeError` (500 opaco, L-2). Sin evento
    y sin `commit()` propio: el valor solo sale si la auditoría quedó en la misma transacción."""
    await lock_member(session, member_id)  # L-1: orden único de candados; una baja no se cuela
    socio = await members_service.get_ref(session, member_id)
    metric = await session.scalar(
        select(BodyMetric)
        .where(BodyMetric.id == metric_id, BodyMetric.member_id == member_id)
        .with_for_update(read=True, of=BodyMetric)
        .execution_options(populate_existing=True)
    )
    if metric is None:
        raise MetricNotFound()
    if socio.is_deleted and role != ADMIN_ROLE:
        # L-2: el 403 no deja fila de auditoría; el aviso lleva usuario y medición (S9-D35: el
        # usuario va al log, no a la alerta), nunca campo, valor ni datos del socio.
        logger.warning(
            "athletes: reveal denegado de un socio dado de baja",
            extra={"user_id": str(get_actor()), "metric_id": str(metric.id)},
        )
        raise ForbiddenError()
    valor = _decrypt_metric_field(metric, field, REVEAL_PURPOSE)
    await audit.record(
        session,
        action="reveal",
        table_name=METRICS_TABLE,
        record_id=metric.id,
        before=None,
        after={"field": field, "ip": ip},
        subject_member_id=member_id,
    )
    return MetricRevealOut(field=field, value=valor)
