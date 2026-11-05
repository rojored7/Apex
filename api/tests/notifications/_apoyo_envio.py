"""Ayudas de las pruebas de envío de correo de avisos (S5-B8, US-125). # Rojo B8

- `CanalFalso`: `NotificationChannel` de prueba; anota cada `ChannelPayload`, devuelve los
  `ChannelResult` programados (o lanza la excepción programada) y puede ejecutar un `espia` justo
  antes de responder (para mirar la base desde otra conexión mientras "envía").
- `cargar_correo`: el `load_contact` real (`contact_for_notification(..., fields={"email"})`).
- `habilitar_correo(fabrica)`: guarda `settings.channels` con el correo activo.
- `socio_con_correo`, `regla_correo`, `aviso_correo`: escenarios con commit real.
- `estado_de(fabrica, id)`, `todos(fabrica)`: filas crudas de `notifications.notifications`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.members import service as members_service
from app.modules.members.models import Member
from app.modules.notifications.channels.base import ChannelPayload, ChannelResult
from app.modules.notifications.models import Notification, NotificationRule
from app.modules.settings.service import update_section
from tests.factories.notifications import SOON, make_notification, make_rule, make_template
from tests.notifications._apoyo_avisos import HOY, canales, socio

Fabrica = async_sessionmaker[AsyncSession]

CORREO: Final = "lucia.gomez@example.com"
CANALES_CON_CORREO: Final[dict[str, Any]] = {
    "email": {"enabled": True, "sender_name": "APEX CrossFit", "reply_to": "hola@gimnasio.test"},
    "whatsapp": {"enabled": True, "country_code": "57"},
    "telegram": {"enabled": False},
}
OK: Final = ChannelResult(ok=True)


def fallo(codigo: str) -> ChannelResult:
    return ChannelResult(ok=False, error_code=codigo)


@dataclass
class CanalFalso:
    """Registra lo enviado. `resultados` se consume en orden (el último se repite);
    `lanzar` es una excepción que `send` lanza siempre (un canal con un bug)."""

    resultados: list[ChannelResult] = field(default_factory=lambda: [OK])
    configured: bool = True
    lanzar: BaseException | None = None
    espia: Callable[[ChannelPayload], Awaitable[None]] | None = None
    enviados: list[ChannelPayload] = field(default_factory=list)
    name: str = "email"

    async def send(self, payload: ChannelPayload) -> ChannelResult:
        self.enviados.append(payload)
        if self.espia is not None:
            await self.espia(payload)
        if self.lanzar is not None:
            raise self.lanzar
        indice = min(len(self.enviados) - 1, len(self.resultados) - 1)
        return self.resultados[indice]


async def cargar_correo(session: AsyncSession, member_id: UUID) -> Any:
    return await members_service.contact_for_notification(
        session, member_id, "notify", fields={"email"}
    )


async def habilitar_correo(fabrica: Fabrica, valor: dict[str, Any] | None = None) -> None:
    async with fabrica() as sesion:
        with actor_scope(SYSTEM_USER_ID):
            await update_section(sesion, "channels", valor or CANALES_CON_CORREO, 0, SYSTEM_USER_ID)
            await sesion.commit()


async def socio_con_correo(
    fabrica: Fabrica, correo: str | None = CORREO, *, nombre: str = "Lucía", **cambios: Any
) -> Member:
    """Socio consentido con correo cifrado y la preferencia de correo activa."""
    async with fabrica() as sesion:
        miembro = await socio(sesion, nombre=nombre, email=correo, **cambios)
        if correo is not None and cambios.get("consentido", True):
            await canales(sesion, miembro, email=True)
        return miembro


async def regla_correo(fabrica: Fabrica, **cambios: Any) -> NotificationRule:
    async with fabrica() as sesion:
        plantilla = await make_template(sesion, name=SOON)
        valores = {"channel": "email", **cambios}
        return await make_rule(sesion, plantilla, **valores)


async def aviso_correo(
    fabrica: Fabrica,
    regla: NotificationRule,
    miembro: Member,
    **cambios: Any,
) -> Notification:
    valores = {
        "member_id": miembro.id,
        "channel": "email",
        "target_date": HOY,
        "rendered_subject": "Tu membresía vence pronto",
        "rendered_body": "Hola Lucía, tu plan Mensual vence el 24 oct 2026 (en 3 días).",
        **cambios,
    }
    async with fabrica() as sesion:
        return await make_notification(sesion, regla, **valores)


async def estado_de(fabrica: Fabrica, notification_id: UUID) -> dict[str, Any]:
    async with fabrica() as sesion:
        fila = (
            (
                await sesion.execute(
                    text("SELECT * FROM notifications.notifications WHERE id = :i"),
                    {"i": notification_id},
                )
            )
            .mappings()
            .one()
        )
        return dict(fila)


async def todos(fabrica: Fabrica) -> list[dict[str, Any]]:
    async with fabrica() as sesion:
        filas = await sesion.execute(
            text("SELECT * FROM notifications.notifications ORDER BY created_at, id")
        )
        return [dict(f) for f in filas.mappings()]


async def escenario_job(
    fabrica: Fabrica, *, fin_en_dias: int = 3, correo: str | None = CORREO
) -> Member:
    """Correo activo, una regla `email` (vence en 3 días) y un socio con correo y membresía que
    termina en `HOY + fin_en_dias`: el job genera 1 aviso y lo envía."""
    from datetime import timedelta

    from tests.factories.plans import make_plan
    from tests.notifications._apoyo_avisos import con_membresia

    await habilitar_correo(fabrica)
    await regla_correo(fabrica, name="Vence en 3 días")
    miembro = await socio_con_correo(fabrica, correo)
    async with fabrica() as sesion:
        plan = await make_plan(sesion)
        await con_membresia(sesion, miembro, plan, HOY + timedelta(days=fin_en_dias))
    return miembro
