"""Candado del socio (S3-D54, D3 y L-1): la única puerta para serializar las escrituras de un socio.

`lock_member(session, member_id)` toma `pg_advisory_xact_lock(hashtextextended(<uuid>, 0))` (la
semilla `MEMBER_LOCK_NAMESPACE` viaja como parámetro ligado `:ns`, PL2 de Fase 4 del Sprint 3): un
candado asesor de transacción (se libera solo al confirmar o revertir) cuya llave de 64 bits la
calcula PostgreSQL. El api no calcula la llave en Python: fuera de `core/crypto` y
`core/security` no se importa `hashlib` (bus de criptografía, regla 8).

Es el primer paso del orden único de candados de D3: socio, `FOR SHARE` del plan, fila de la
membresía, fila del pago y, al hacer flush, la cadena de auditoría (que toma el hook). Si la
espera supera `lock_timeout` (S3-D43), el 55P03 sale como `DatabaseBusy` (503 `busy`, S3-D67).

La sentencia es una constante de módulo (S608 y `test_sql_literals_constant.py`); el id y la
semilla viajan siempre como parámetros ligados (`:m` y `:ns`), nunca interpolados.

Advertencia (PL6 de la revisión de Fase 4 del Sprint 3, S3-D95): el candado de la cadena de
auditoría lo toma el hook de `core/audit.py` en `after_flush`, es decir, en el PRIMER flush
auditado de la transacción. Una transacción que ya hizo flush (tiene el candado de la cadena) y
DESPUÉS pide `lock_member` de un socio o el `FOR SHARE` de un plan invierte el orden de D3 y puede
interbloquearse con otra que siga el orden correcto. Regla: toda unidad que escribe sobre un
socio pide `lock_member` antes de su primer flush auditado, y un proceso por lotes (la importación
del CLI, por ejemplo) confirma una transacción por socio en lugar de encadenar socios en la misma.
Si igual ocurre, PostgreSQL corta el ciclo (40P01) y `get_session` responde 503 `busy`.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import DatabaseBusy, sqlstate_of

MEMBER_LOCK_NAMESPACE: Final = 0
"""Semilla de `hashtextextended` para las llaves de socio (distintas de `MIGRATION_LOCK_KEY` y
`AUDIT_CHAIN_LOCK_KEY`, que son enteros fijos)."""

MEMBER_LOCK_SQL: Final = "SELECT pg_advisory_xact_lock(hashtextextended(:m, :ns))"
"""Candado asesor de transacción por socio; `:m` es `str(member_id)` y `:ns` la semilla."""

LOCK_NOT_AVAILABLE: Final = "55P03"
"""SQLSTATE de `lock_timeout` agotado (`lock_not_available`)."""


async def lock_member(session: AsyncSession, member_id: UUID) -> None:
    """Toma el candado del socio dentro de la transacción de `session` (espera si otro lo tiene).

    Traduce la espera agotada (`lock_timeout`, 55P03) a `DatabaseBusy`; cualquier otro error sale
    intacto. El candado se libera solo al terminar la transacción.
    """
    try:
        await session.execute(
            text(MEMBER_LOCK_SQL), {"m": str(member_id), "ns": MEMBER_LOCK_NAMESPACE}
        )
    except DBAPIError as error:
        if sqlstate_of(error) != LOCK_NOT_AVAILABLE:
            raise
        raise DatabaseBusy() from error
