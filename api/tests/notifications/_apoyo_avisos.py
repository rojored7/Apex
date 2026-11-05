"""Ayudas de las pruebas de avisos (S5-B7, US-124, US-127 a US-130). # Rojo B7

- Rutas: `AVISOS`, `HOY_RUTA`, `ruta_aviso(id)`, `ruta_wa(id)`, `ruta_omitir(id)`,
  `ruta_del_socio(member_id)`; `CAMPOS_AVISO` (claves exactas de `NotificationOut`).
- `HOY`: el "hoy" de Bogotá de la fixture `reloj` (2026-10-21).
- `vence_texto(fecha)`: el formato de `{vence}` (`20 oct 2026`, día sin ceros) que fija el Rojo.
- `cuerpo_esperado(...)`: el cuerpo que debe dejar la plantilla "Vence pronto" sembrada.
- `socio(session, ...)`, `con_membresia(session, socio, plan, fin, ...)`, `canales(session, ...)`:
  armado de escenarios (socio consentido sin teléfono ni correo, membresía `active` de 30 días).
- `reglas_por_defecto(session)`: las cinco reglas sembradas con el ORM (todas `whatsapp_link`).
- `avisos(session)`: filas crudas de `notifications.notifications` por `target_date, rule offset`.
- `eventos_de(tipo)`: captura los eventos de ese tipo en el bus durante la prueba.
- `en_peticion`, `contar` y `filas_de_auditoria` se reusan de `tests/notifications/_apoyo.py`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.events import DomainEvent
from app.modules.members import service as members_service
from app.modules.members.models import Member
from app.modules.members.schemas import ChannelItem
from app.modules.memberships.models import Membership
from app.modules.plans.models import Plan
from tests.conftest import T0
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.notifications import (
    DEFAULT_TEMPLATES,
    SOON,
    make_rule,
    make_template,
    seed_defaults_db,
)

AVISOS: Final = "/api/v1/notifications"
HOY_RUTA: Final = f"{AVISOS}/today"
T_AVISOS: Final = "notifications.notifications"
HOY: Final = date(2026, 10, 21)
ANTES: Final = T0 - timedelta(days=1)
"""Un instante anterior a `T0`: consentimiento de los socios o fecha de baja."""
MESES: Final = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
CAMPOS_AVISO: Final = frozenset(
    {
        "id",
        "rule_id",
        "member_id",
        "member_name",
        "membership_id",
        "target_date",
        "channel",
        "status",
        "rendered_subject",
        "rendered_body",
        "attempts",
        "last_error",
        "sent_at",
        "sent_by",
        "skip_reason",
        "created_at",
        "updated_at",
    }
)
TELEFONO: Final = "300 765 4321"
TELEFONO_DIGITOS: Final = "3007654321"


def ruta_aviso(notification_id: UUID | str) -> str:
    return f"{AVISOS}/{notification_id}"


def ruta_wa(notification_id: UUID | str) -> str:
    return f"{AVISOS}/{notification_id}/wa-link"


def ruta_omitir(notification_id: UUID | str) -> str:
    return f"{AVISOS}/{notification_id}/skip"


def ruta_del_socio(member_id: UUID | str) -> str:
    return f"/api/v1/members/{member_id}/notifications"


def vence_texto(fecha: date) -> str:
    """`{vence}`: día sin ceros, mes abreviado en minúsculas y año (`5 nov 2026`)."""
    return f"{fecha.day} {MESES[fecha.month - 1]} {fecha.year}"


def cuerpo_esperado(nombre: str, plan: str, fin: date, dias: int, plantilla: str = SOON) -> str:
    """El cuerpo de la plantilla sembrada con `{nombre} {plan} {vence} {dias}` sustituidos."""
    _, cuerpo = DEFAULT_TEMPLATES[plantilla]
    return (
        cuerpo.replace("{nombre}", nombre)
        .replace("{plan}", plan)
        .replace("{vence}", vence_texto(fin))
        .replace("{dias}", str(dias))
    )


async def socio(
    session: AsyncSession,
    *,
    consentido: bool = True,
    nombre: str = "Lucía",
    apellido: str = "Gómez",
    **cambios: Any,
) -> Member:
    """Socio con documento único, sin teléfono ni correo, con o sin `data_consent_at`."""
    valores: dict[str, Any] = {
        "first_name": nombre,
        "last_name": apellido,
        "document": unique_document(),
        "phone": None,
        "email": None,
        "data_consent_at": ANTES if consentido else None,
    }
    valores.update(cambios)
    return await make_member(session, **valores)


async def con_membresia(
    session: AsyncSession,
    miembro: Member,
    plan: Plan,
    fin: date,
    *,
    status: str = "active",
    dias: int = 30,
    **cambios: Any,
) -> Membership:
    """Membresía del socio que termina en `fin` y empezó `dias - 1` días antes."""
    return await make_membership(
        session,
        miembro,
        plan,
        status=status,
        start=fin - timedelta(days=dias - 1),
        end=fin,
        **cambios,
    )


async def canales(session: AsyncSession, miembro: Member, **activos: bool) -> None:
    """Guarda preferencias (`email=True`, `whatsapp_link=False`...) con `set_channels`."""
    items = [ChannelItem(channel=c, active=a) for c, a in activos.items()]  # type: ignore[arg-type]
    with actor_scope(SYSTEM_USER_ID):
        await members_service.set_channels(session, miembro.id, items, SYSTEM_USER_ID)
        await session.commit()


async def reglas_por_defecto(session: AsyncSession) -> None:
    await seed_defaults_db(session)


async def regla_aislada(
    session: AsyncSession,
    trigger: str,
    offset_days: int,
    *,
    channel: str = "whatsapp_link",
    plantilla: str = SOON,
    **cambios: Any,
) -> Any:
    """Una sola regla activa con la plantilla sembrada `plantilla` (para aislar la ventana)."""
    asunto, cuerpo = DEFAULT_TEMPLATES[plantilla]
    base = await make_template(session, name=plantilla, subject=asunto, body=cuerpo)
    return await make_rule(
        session, base, trigger=trigger, offset_days=offset_days, channel=channel, **cambios
    )


async def avisos(session: AsyncSession) -> list[dict[str, Any]]:
    consulta = text(
        "SELECT n.*, r.offset_days FROM notifications.notifications n "
        "JOIN notifications.notification_rules r ON r.id = n.rule_id "
        "ORDER BY n.target_date, r.offset_days, n.member_id"
    )
    return [dict(f) for f in (await session.execute(consulta)).mappings()]


class Capturados[E: DomainEvent]:
    """Eventos de un tipo recibidos por el bus mientras dura la prueba."""

    def __init__(self, tipo: type[E]) -> None:
        self.tipo = tipo
        self.vistos: list[E] = []

    async def _recibir(self, evento: E, _session: AsyncSession) -> None:
        self.vistos.append(evento)


def eventos_de[E: DomainEvent](tipo: type[E]) -> Capturados[E]:
    """Se suscribe a `tipo`; la fixture autouse `restaurar_bus` limpia la suscripción."""
    captura = Capturados(tipo)
    events.subscribe(tipo, captura._recibir)
    return captura


# Rojo V11c · ajustes de Canales (S5-D265) ---------------------------------------------------------


async def ajustar_canales(
    session: AsyncSession,
    *,
    email: bool = False,
    whatsapp: bool = False,
    telegram: bool = False,
    country_code: str = "57",
) -> None:
    """Guarda `settings.channels` (con el control de versión) y confirma. Sin llamarla no hay fila:
    sin fila el canal está apagado (S5-D231)."""
    from app.modules.settings import service as settings_service

    actual = await settings_service.get_section(session, "channels")
    valor = {
        "email": {"enabled": email, "sender_name": "APEX", "reply_to": None},
        "whatsapp": {"enabled": whatsapp, "country_code": country_code},
        "telegram": {"enabled": telegram},
    }
    with actor_scope(SYSTEM_USER_ID):
        await settings_service.update_section(
            session, "channels", valor, actual.version, SYSTEM_USER_ID
        )
        await session.commit()
