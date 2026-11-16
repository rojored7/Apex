"""Apoyo de las pruebas de `athletes` (S9-A1, US-178).

- `ENCRIPTADAS`: las cuatro columnas cifradas de `athletes.body_metrics`, en el orden del contrato.
- `cuerpo(**cambios)`: cuerpo JSON de `POST /athletes/{id}/metrics` con una medición válida.
- `entrada(**cambios)`: el mismo cuerpo como `MetricIn`.
- `alta(session, actor, member_id, **cambios)`: `service.add_metric` bajo `actor_scope` y commit
  (una petición, una transacción); la sesión empieza limpia, como una petición nueva.
- `fila_cruda(session, metric_id)`: la fila de `athletes.body_metrics` por SQL crudo (blobs tal
  como están en la base).
- `ops_de(session, metric_id, verb)`: filas de `crypto.crypto_ops` del registro con ese verbo.
- `auditoria_de(session, metric_id)`: filas de `audit.audit_log` de la medición, en orden de `seq`.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.athletes import service
from app.modules.athletes.schemas import MetricIn, MetricOut

ATHLETES: Final = "/api/v1/athletes"
ENCRIPTADAS: Final[tuple[str, ...]] = ("weight_g", "height_cm", "body_fat_pct", "notes")
CLASE: Final = "athlete.metric"
TABLA: Final = "athletes.body_metrics"
FECHA: Final = date(2026, 10, 20)  # un día antes de `T0` (21 de octubre, 10:00 de Bogotá)


def ruta_metricas(member_id: UUID | str) -> str:
    return f"{ATHLETES}/{member_id}/metrics"


def cuerpo(**cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {
        "measured_on": FECHA.isoformat(),
        "weight_g": 62_500,
        "height_cm": 165,
        "body_fat_pct": 22,
        "notes": "Primera medición del año",
    }
    valores.update(cambios)
    return {campo: valor for campo, valor in valores.items() if valor is not None}


def entrada(**cambios: Any) -> MetricIn:
    return MetricIn.model_validate(cuerpo(**cambios))


async def alta(session: AsyncSession, actor: UUID, member_id: UUID, **cambios: Any) -> MetricOut:
    session.expunge_all()
    with actor_scope(actor):
        salida = await service.add_metric(session, member_id, entrada(**cambios), by=actor)
        await session.commit()
    return salida


async def fila_cruda(session: AsyncSession, metric_id: UUID) -> dict[str, Any]:
    consulta = text(f"SELECT * FROM {TABLA} WHERE id = :id")  # noqa: S608
    return dict((await session.execute(consulta, {"id": metric_id})).mappings().one())


async def ops_de(session: AsyncSession, metric_id: UUID, verb: str) -> list[dict[str, Any]]:
    consulta = text(
        "SELECT * FROM crypto.crypto_ops WHERE record_id = :r AND verb = :v ORDER BY at, id"
    )
    return [
        dict(f) for f in (await session.execute(consulta, {"r": metric_id, "v": verb})).mappings()
    ]


async def encripts_de_la_clase(session: AsyncSession) -> int:
    """Suma de `count` de las operaciones `encrypt` de `athlete.metric` (todas las mediciones)."""
    consulta = text(
        "SELECT coalesce(sum(count), 0) FROM crypto.crypto_ops "
        "WHERE verb = 'encrypt' AND data_class = :c"
    )
    return int(await session.scalar(consulta, {"c": CLASE}) or 0)


async def auditoria_de(session: AsyncSession, metric_id: UUID) -> list[dict[str, Any]]:
    consulta = text(
        "SELECT * FROM audit.audit_log WHERE table_name = :t AND record_id = :id ORDER BY seq"
    )
    return [
        dict(f) for f in (await session.execute(consulta, {"t": TABLA, "id": metric_id})).mappings()
    ]
