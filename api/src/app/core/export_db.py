"""Piezas de las exportaciones CSV que tocan la base (S5-D257; S5-D248, S5-B12).

- `keyset_after(consulta, columnas, despues_de)`: el filtro de paginación por llave compuesta
  `(columnas) > despues_de`, sin OFFSET, con los literales tipados según cada columna; el orden y
  el límite los pone quien llama.
- `record_close(table, export_id, by, *, completed, rows_sent)`: la fila `export` de cierre en
  sesión propia (`db.get_sessionmaker()`), blindada contra la cancelación del cliente; un fallo
  se registra y avisa (`export_close_lost`, con la tabla en la clave `job` de `alerts`) sin tapar
  el motivo del corte.

Sin `app.modules`: `members/exports.py` y `payments/exports.py` solo pasan tabla y columnas. Va
aparte de `core/export.py` porque `test_core_import_direction` fija ese archivo a la biblioteca
estándar más `core.errors`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import anyio
from sqlalchemy import Select, literal, tuple_
from sqlalchemy.orm import InstrumentedAttribute

from app.core import audit, db
from app.core.alerts import alert

logger = logging.getLogger("app.core.export")


def keyset_after[T](
    consulta: Select[T],
    columnas: Sequence[InstrumentedAttribute[Any]],
    despues_de: Sequence[Any] | None,
) -> Select[T]:
    """Filtra `(columnas) > despues_de` (comparación de tupla, sin OFFSET) con los literales
    tipados según cada columna. Sin `despues_de` devuelve la consulta intacta."""
    if despues_de is None:
        return consulta
    actual = tuple_(*columnas)
    pasado = tuple_(*(literal(v, c.type) for c, v in zip(columnas, despues_de, strict=True)))
    return consulta.where(actual > pasado)


async def record_close(
    table: str, export_id: UUID, by: UUID, *, completed: bool, rows_sent: int
) -> None:
    """La fila de cierre en sesión propia; blindada contra la cancelación del cliente (S5-D248).
    Un fallo no tapa el motivo del corte: se registra y se avisa."""
    with anyio.CancelScope(shield=True):
        try:
            async with db.get_sessionmaker()() as sesion:
                await audit.record(
                    sesion,
                    action="export",
                    table_name=table,
                    record_id=export_id,
                    before=None,
                    after={"completed": completed, "rows_sent": rows_sent},
                    user_id=by,
                )
                await sesion.commit()
        except Exception as error:
            tipo = type(error).__name__
            logger.error("export: cierre sin registrar", extra={"table": table, "error_type": tipo})
            alert("export_close_lost", job=table, error_type=tipo)
