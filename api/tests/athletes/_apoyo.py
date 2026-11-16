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
- `ruta_reveal`, `revelar` (service como una petición), `reveals_de` y `IP` (S9-A2).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.athletes import service
from app.modules.athletes.schemas import MetricIn, MetricOut, MetricRevealOut

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


# S9-A2 (US-179): reveal de una medida ---------------------------------------------------------

IP: Final = "198.51.100.9"
"""La IP que el service recibe y la auditoría guarda en las pruebas de `reveal`."""


def ruta_reveal(member_id: UUID | str, metric_id: UUID | str) -> str:
    return f"{ATHLETES}/{member_id}/metrics/{metric_id}/reveal"


async def revelar(
    session: AsyncSession,
    actor: UUID,
    member_id: UUID,
    metric_id: UUID,
    field: str,
    *,
    role: str = "coach",
    ip: str = IP,
) -> MetricRevealOut:
    """`service.reveal_metric` como una petición: sesión vacía, `actor_scope`, `commit` si sale
    bien y `rollback` si no (el `get_session` real). Los ids se pasan ya leídos: un rollback
    expira los objetos de la sesión compartida."""
    session.expunge_all()
    with actor_scope(actor):
        try:
            salida = await service.reveal_metric(
                session, member_id, metric_id, field, ip=ip, role=role
            )
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
    return salida


async def reveals_de(session: AsyncSession, metric_id: UUID) -> list[dict[str, Any]]:
    """Filas `reveal` de la auditoría de la medición, en orden de `seq`."""
    return [f for f in await auditoria_de(session, metric_id) if f["action"] == "reveal"]


# S9-A3 (US-178): anular una medición -----------------------------------------------------------


def ruta_anular(member_id: UUID | str, metric_id: UUID | str) -> str:
    return f"{ATHLETES}/{member_id}/metrics/{metric_id}/void"


async def anular(
    session: AsyncSession,
    actor: UUID,
    member_id: UUID,
    metric_id: UUID,
    *,
    role: str = "admin",
) -> MetricOut:
    """`service.void_metric` como una petición: sesión vacía, `actor_scope`, `commit` si sale bien
    y `rollback` si no. Los ids se pasan ya leídos (un rollback expira los objetos)."""
    session.expunge_all()
    with actor_scope(actor):
        try:
            salida = await service.void_metric(session, member_id, metric_id, by=actor, role=role)
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
    return salida


async def actualizaciones_de(session: AsyncSession, metric_id: UUID) -> list[dict[str, Any]]:
    """Filas `update` de la auditoría de la medición, en orden de `seq`."""
    return [f for f in await auditoria_de(session, metric_id) if f["action"] == "update"]


# Búsqueda de claros sin falsos positivos (S9-A3, D50) ---------------------------------------


def claros_en(valores: dict[str, Any], claros: tuple[str, ...]) -> list[str]:
    """Los `claros` que aparecen en los valores de una fila o de un `before`/`after` de auditoría.

    Un blob `apx1.…` es base64 aleatorio y un id o una marca de tiempo llevan dígitos: `"165"`
    buscado como subcadena de todo eso falla al azar. Así que se saltan los blobs, los números y los
    textos solo se comparan por IGUALDAD si el claro son dígitos, y por subcadena solo si el claro
    lleva letras (un UUID en hexadecimal no puede contener, por ejemplo, `Primera`)."""
    halladas: list[str] = []
    for claro in claros:
        for valor in valores.values():
            texto = str(valor)
            if texto.startswith("apx1."):
                continue
            if texto == claro or (not claro.isdigit() and claro in texto):
                halladas.append(claro)
                break
    return halladas
