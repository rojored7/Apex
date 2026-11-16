"""Fábrica de `athletes.body_metrics` (S9-A1; hallazgo 6 de la crítica 1).

La guarda de la base prohíbe nacer anulada y cambiar el claro de una medición. La fábrica inserta
por el ORM con blobs reales del bus (`encode_metric` + `Secret.from_plain`) bajo
`actor_scope(actor)` y confirma el savepoint; si se pide anulada, hace DESPUÉS un `UPDATE` por SQL
de `voided_at` y `voided_by` (la rama que la guarda permite). Nunca apaga una guarda. Sin
`member_id` crea antes un socio CON autorización de datos. Necesita el bus listo (fixture
`bus_listo`) y la llave `encrypt` activa de `athlete.metric`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.secret import Secret
from app.modules.athletes.models import BodyMetric
from app.modules.athletes.rules import encode_metric
from tests.factories.members import make_member, unique_document

PESO_G = 62_500
ESTATURA_CM = 165
GRASA_PCT = 22
NOTAS = "Medición de prueba"
FECHA = date(2026, 10, 20)

ANULAR = text("UPDATE athletes.body_metrics SET voided_at = now(), voided_by = :a WHERE id = :i")


def _sellar(campo: str, valor: int | str | None) -> Secret | None:
    return None if valor is None else Secret.from_plain(encode_metric(campo, valor))


async def make_metric(
    session: AsyncSession,
    member_id: UUID | None = None,
    *,
    measured_on: date = FECHA,
    weight_g: int | None = PESO_G,
    height_cm: int | None = ESTATURA_CM,
    body_fat_pct: int | None = GRASA_PCT,
    notes: str | None = NOTAS,
    voided: bool = False,
    actor: UUID = SYSTEM_USER_ID,
    **cambios: Any,
) -> BodyMetric:
    if member_id is None:
        socio = await make_member(
            session,
            document=unique_document(),
            phone=None,
            email=None,
            data_consent_at=datetime.now(UTC),
        )
        member_id = socio.id
    valores: dict[str, Any] = {
        "created_by": actor,
        "member_id": member_id,
        "measured_on": measured_on,
        "recorded_by": actor,
        "weight_g": _sellar("weight_g", weight_g),
        "height_cm": _sellar("height_cm", height_cm),
        "body_fat_pct": _sellar("body_fat_pct", body_fat_pct),
        "notes": _sellar("notes", notes),
    }
    valores.update(cambios)
    medicion = BodyMetric(**valores)
    with actor_scope(actor):
        session.add(medicion)
        await session.flush()
        await session.commit()
        if voided:
            await session.execute(ANULAR, {"a": actor, "i": medicion.id})
            await session.commit()
            await session.refresh(medicion)
    return medicion
