"""Ayudas de las pruebas de `notifications` (S5-B6). # Rojo B6

- Rutas: `PLANTILLAS`, `REGLAS`, `ruta_plantilla(id)`, `ruta_regla(id)`, `PREVIEW`.
- `cuerpo_plantilla(**cambios)` / `cuerpo_regla(template_id, **cambios)`: cuerpos JSON válidos.
- `CAMPOS_PLANTILLA` y `CAMPOS_REGLA`: las claves exactas de `TemplateOut` y `RuleOut`.
- `plantilla_in`, `regla_in`: los cuerpos validados como `TemplateCreate` / `RuleCreate`.
- `contar(session, tabla)`, `fila(session, tabla, id)`: lecturas con SQL crudo.
- `en_peticion(session, actor, operacion)`: una petición (actor fijado) y commit del savepoint.
- `filas_de_auditoria(session, tabla)`: `(action, user_id)` en orden de `seq`.
- `EJEMPLO_*`: el contexto de ejemplo que fija el Rojo para `preview` (duda de contrato).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.notifications.schemas import RuleCreate, TemplateCreate

PLANTILLAS: Final = "/api/v1/notification-templates"
REGLAS: Final = "/api/v1/notification-rules"
PREVIEW: Final = f"{PLANTILLAS}/preview"

T_PLANTILLAS: Final = "notifications.notification_templates"
T_REGLAS: Final = "notifications.notification_rules"

CAMPOS_PLANTILLA: Final = frozenset({"id", "name", "subject", "body", "created_at", "updated_at"})
CAMPOS_REGLA: Final = frozenset(
    {
        "id",
        "name",
        "trigger",
        "offset_days",
        "channel",
        "template_id",
        "is_active",
        "created_at",
        "updated_at",
    }
)

# Contexto de ejemplo de `preview` (fijado por el Rojo B6): nombre, plan, vencimiento y días.
EJEMPLO_TEXTO: Final = "Hola {nombre}, tu plan {plan} vence el {vence} (en {dias} días)."
EJEMPLO_RENDER: Final = "Hola Ana, tu plan Mensual vence el 20 oct 2026 (en 3 días)."


def ruta_plantilla(template_id: UUID | str) -> str:
    return f"{PLANTILLAS}/{template_id}"


def ruta_regla(rule_id: UUID | str) -> str:
    return f"{REGLAS}/{rule_id}"


def cuerpo_plantilla(**cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {
        "name": "Vence pronto",
        "subject": "Tu membresía vence pronto",
        "body": "Hola {nombre}, tu plan {plan} vence el {vence}.",
    }
    valores.update(cambios)
    return valores


def cuerpo_regla(template_id: UUID | str, **cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {
        "name": "Vence en 3 días",
        "trigger": "membership_expiring",
        "offset_days": -3,
        "channel": "whatsapp_link",
        "template_id": str(template_id),
    }
    valores.update(cambios)
    return valores


def plantilla_in(**cambios: Any) -> TemplateCreate:
    return TemplateCreate.model_validate(cuerpo_plantilla(**cambios))


def regla_in(template_id: UUID, **cambios: Any) -> RuleCreate:
    return RuleCreate.model_validate(cuerpo_regla(template_id, **cambios))


async def contar(session: AsyncSession, tabla: str) -> int:
    return int(await session.scalar(text(f"SELECT count(*) FROM {tabla}")) or 0)  # noqa: S608


async def fila(session: AsyncSession, tabla: str, registro: UUID) -> dict[str, Any]:
    consulta = text(f"SELECT * FROM {tabla} WHERE id = :id")  # noqa: S608
    return dict((await session.execute(consulta, {"id": registro})).mappings().one())


async def en_peticion[T](
    session: AsyncSession, actor: UUID, operacion: Callable[[], Awaitable[T]]
) -> T:
    """`operacion()` bajo `actor_scope(actor)` y commit (libera el savepoint de la prueba)."""
    with actor_scope(actor):
        salida = await operacion()
        await session.commit()
    return salida


async def filas_de_auditoria(session: AsyncSession, tabla: str) -> list[tuple[str, UUID]]:
    consulta = text(
        "SELECT action, user_id FROM audit.audit_log WHERE table_name = :t ORDER BY seq"
    )
    return [
        (f["action"], f["user_id"])
        for f in (await session.execute(consulta, {"t": tabla})).mappings()
    ]
