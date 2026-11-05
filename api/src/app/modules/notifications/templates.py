"""CRUD de plantillas y vista previa (S5-B6, US-120; S5-D24, S5-D213, S5-D214). Privado: solo
`service.py` lo importa.

- `create_template`: nombre en NFC y recortado, variables de `subject` y `body` validadas (422 con
  `field`), único por nombre (409 `template_name_taken`; la carrera la decide
  `uq_notification_templates_name` dentro de un savepoint).
- `update_template`: `FOR UPDATE`, aplica solo lo enviado; sin cambios no hay `flush` ni auditoría.
- `list_templates`: `q` sobre el nombre, sin tildes ni mayúsculas, comodines escapados; orden
  `name, id`.
- `preview`: renderiza asunto y cuerpo con el contexto de ejemplo; no escribe.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Final
from uuid import UUID

from sqlalchemy import Text, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_actor
from app.core.db import violated_constraint
from app.core.pagination import Page, PageParams, paginate, to_page
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern, sql_fold
from app.modules.notifications.exceptions import TemplateNameTaken, TemplateNotFound
from app.modules.notifications.models import TEMPLATE_NAME_UNIQUE, NotificationTemplate
from app.modules.notifications.rules import render, render_subject, validate_template_vars
from app.modules.notifications.schemas import (
    PreviewOut,
    TemplateCreate,
    TemplateOut,
    TemplatePatch,
)

logger = logging.getLogger("app.notifications")

PREVIEW_CONTEXT: Final[dict[str, str | int]] = {
    "nombre": "Ana",
    "plan": "Mensual",
    "vence": "20 oct 2026",
    "dias": 3,
}
"""Contexto de ejemplo de la vista previa (S5-D213)."""
_EDITABLES: Final = ("name", "subject", "body")


def _clean(name: str) -> str:
    return unicodedata.normalize("NFC", name).strip()


async def _id_by_name(
    session: AsyncSession, name: str, *, exclude: UUID | None = None
) -> UUID | None:
    consulta = select(NotificationTemplate.id).where(NotificationTemplate.name == name)
    if exclude is not None:
        consulta = consulta.where(NotificationTemplate.id != exclude)
    resultado: UUID | None = await session.scalar(consulta)
    return resultado


async def _flush_unique(
    session: AsyncSession, template: NotificationTemplate, *, exclude: UUID | None = None
) -> None:
    """`flush` en un savepoint; el choque de nombre se traduce a 409 con el id del ganador."""
    nombre, plantilla_id = template.name, template.id  # el rollback del savepoint expira la fila
    try:
        async with session.begin_nested():
            session.add(template)
            await session.flush()
    except IntegrityError as error:
        if violated_constraint(error) != TEMPLATE_NAME_UNIQUE:
            raise
        logger.info("notifications: nombre de plantilla repetido")
        ganador = await _id_by_name(session, nombre, exclude=exclude or plantilla_id)
        raise TemplateNameTaken(ganador) from None


async def list_templates(
    session: AsyncSession, q: str | None, page: PageParams
) -> Page[TemplateOut]:
    consulta = select(NotificationTemplate)
    termino = clean_query(q)
    if termino:
        patron = sql_fold(literal(contains_pattern(termino), Text))  # valor ligado
        consulta = consulta.where(
            sql_fold(NotificationTemplate.name).ilike(patron, escape=LIKE_ESCAPE)
        )
    filas, total = await paginate(
        session, consulta.order_by(NotificationTemplate.name, NotificationTemplate.id), page
    )
    return to_page([TemplateOut.model_validate(f) for f in filas], total, page)


async def _get(session: AsyncSession, template_id: UUID, *, lock: bool) -> NotificationTemplate:
    consulta = select(NotificationTemplate).where(NotificationTemplate.id == template_id)
    if lock:
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    plantilla = await session.scalar(consulta)
    if plantilla is None:
        raise TemplateNotFound()
    return plantilla


async def get_template(session: AsyncSession, template_id: UUID) -> TemplateOut:
    return TemplateOut.model_validate(await _get(session, template_id, lock=False))


async def create_template(session: AsyncSession, data: TemplateCreate) -> TemplateOut:
    nombre = _clean(data.name)
    validate_template_vars(data.subject, "subject")
    validate_template_vars(data.body, "body")
    existente = await _id_by_name(session, nombre)
    if existente is not None:
        raise TemplateNameTaken(existente)
    plantilla = NotificationTemplate(
        name=nombre, subject=data.subject, body=data.body, created_by=get_actor()
    )
    await _flush_unique(session, plantilla)
    logger.info("notifications: plantilla creada", extra={"template_id": str(plantilla.id)})
    return TemplateOut.model_validate(plantilla)


async def update_template(
    session: AsyncSession, template_id: UUID, data: TemplatePatch
) -> TemplateOut:
    plantilla = await _get(session, template_id, lock=True)
    nuevos = {
        campo: _clean(valor) if campo == "name" else valor
        for campo in _EDITABLES
        if campo in data.model_fields_set and (valor := getattr(data, campo)) is not None
    }
    cambios = {c: v for c, v in nuevos.items() if getattr(plantilla, c) != v}
    if not cambios:
        return TemplateOut.model_validate(plantilla)
    for campo in ("subject", "body"):
        if campo in cambios:
            validate_template_vars(cambios[campo], campo)
    if "name" in cambios:
        existente = await _id_by_name(session, cambios["name"], exclude=template_id)
        if existente is not None:
            raise TemplateNameTaken(existente)
    for campo, valor in cambios.items():
        setattr(plantilla, campo, valor)
    await _flush_unique(session, plantilla, exclude=template_id)
    logger.info(
        "notifications: plantilla editada",
        extra={"template_id": str(template_id), "template_fields": sorted(cambios)},
    )
    return TemplateOut.model_validate(plantilla)


def preview(subject: str, body: str) -> PreviewOut:
    """Asunto y cuerpo renderizados con `PREVIEW_CONTEXT`; 422 con `field` si hay error."""
    validate_template_vars(subject, "subject")
    validate_template_vars(body, "body")
    return PreviewOut(
        subject=render_subject(subject, PREVIEW_CONTEXT), body=render(body, PREVIEW_CONTEXT)
    )
