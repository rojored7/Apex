"""Fábricas de `athletes` (S9-A1 `make_metric`, S9-B1 `make_record`; hallazgo 6 de la crítica 1).

`make_metric`: fábrica de `athletes.body_metrics`.

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
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.secret import Secret
from app.modules.athletes.models import BodyMetric, PersonalRecord
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


INVALIDAR = text(
    "UPDATE athletes.personal_records SET invalidated_at = clock_timestamp(), "
    "invalidated_by = :a, "
    "invalidated_reason = :r, invalidated_by_result_id = :n, "
    "updated_at = clock_timestamp() WHERE id = :i"
)

# S9-B1 (US-180; hallazgo 6 de la crítica 1): récords personales ---------------------------------

MARCA_RM_G = 100_000
"""RM por defecto de `make_record(kind="rm")`: 100 kg."""
SEGUNDOS_BENCHMARK = 300
"""Marca por defecto de `make_record(kind="benchmark")`: `rx`, `seconds=300` (tipo `time`)."""


async def make_record(
    session: AsyncSession,
    member_id: UUID | None = None,
    *,
    kind: str = "rm",
    movement_id: UUID | None = None,
    benchmark_id: UUID | None = None,
    value_g: int | None = None,
    level: str | None = None,
    seconds: int | None = None,
    rounds: int | None = None,
    reps: int | None = None,
    load_g: int | None = None,
    capped: bool = False,
    achieved_on: date = FECHA,
    source: str = "manual",
    result_id: UUID | None = None,
    wod_id: UUID | None = None,
    invalidated: bool = False,
    invalidated_reason: str | None = None,
    invalidated_by_result_id: UUID | None = None,
    actor: UUID = SYSTEM_USER_ID,
    **cambios: Any,
) -> PersonalRecord:
    """Un récord VIVO, o invalidado con `invalidated=True` (S9-B1). Contrato (el Verde lo escribe):

    - Sin `member_id` crea antes un socio (no hace falta autorización de datos: un récord no es
      dato de salud, S9-D8).
    - `kind="rm"`: `movement_id` (un `uuid4()` si no se pasa: no hay FK entre esquemas) y `value_g`
      (`MARCA_RM_G` si no se pasa). `kind="benchmark"`: `benchmark_id` (un `uuid4()`), `level`
      (`"rx"`) y, si no se pasa ninguna marca, `seconds=SEGUNDOS_BENCHMARK`.
    - `source="derived"` exige `result_id` y `wod_id` (un `uuid4()` cada uno si faltan); `"manual"`
      los deja en `None` (el CHECK de la base).
    - Inserta por el ORM bajo `actor_scope(actor)` con `created_by = actor` y confirma el
      savepoint. Si `invalidated`, hace DESPUÉS un `UPDATE` por SQL de `invalidated_at = now()`,
      `invalidated_reason` (`"manual_error"` en un manual, `"superseded"` en un derivado, o el
      pasado), `invalidated_by = actor` e `invalidated_by_result_id` (la rama que la guarda de la
      base permite, nunca apagando una guarda) y refresca la fila.
    - `**cambios` pisa cualquier columna del modelo.
    """
    if member_id is None:
        socio = await make_member(session, document=unique_document(), phone=None, email=None)
        member_id = socio.id
    derivado = source == "derived"
    valores: dict[str, Any] = {
        "created_by": actor,
        "member_id": member_id,
        "kind": kind,
        "achieved_on": achieved_on,
        "source": source,
        "capped": capped,
        "result_id": (result_id or uuid4()) if derivado else result_id,
        "wod_id": (wod_id or uuid4()) if derivado else wod_id,
    }
    if kind == "rm":
        valores["movement_id"] = movement_id or uuid4()
        valores["value_g"] = MARCA_RM_G if value_g is None else value_g
    else:
        valores["benchmark_id"] = benchmark_id or uuid4()
        valores["level"] = level or "rx"
        sin_marca = all(m is None for m in (seconds, rounds, reps, load_g))
        valores["seconds"] = SEGUNDOS_BENCHMARK if sin_marca else seconds
        valores["rounds"], valores["reps"], valores["load_g"] = rounds, reps, load_g
    valores.update(cambios)
    record = PersonalRecord(**valores)
    with actor_scope(actor):
        session.add(record)
        await session.flush()
        await session.commit()
        if invalidated:
            razon = invalidated_reason or ("superseded" if derivado else "manual_error")
            await session.execute(
                INVALIDAR,
                {
                    "a": actor,
                    "r": razon,
                    "n": invalidated_by_result_id,
                    "i": record.id,
                },
            )
            await session.commit()
            await session.refresh(record)
    return record
