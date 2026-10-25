"""Candado del socio (S3-D54, D3 y L-1): la única puerta para serializar las escrituras de un socio.

`lock_member(session, member_id)` toma `pg_advisory_xact_lock(hashtextextended(<uuid>, 0))`: un
candado asesor de transacción (se libera solo al confirmar o revertir) cuya llave de 64 bits la
calcula PostgreSQL. El api no calcula la llave en Python: fuera de `core/crypto` y
`core/security` no se importa `hashlib` (bus de criptografía, regla 8).

Es el primer paso del orden único de candados de D3: socio, `FOR SHARE` del plan, fila de la
membresía, fila del pago y, al hacer flush, la cadena de auditoría (que toma el hook). Si la
espera supera `lock_timeout` (S3-D43), el 55P03 sale como `DatabaseBusy` (503 `busy`, S3-D67).

La sentencia es una constante de módulo (S608 y `test_sql_literals_constant.py`); el id viaja
siempre como parámetro ligado `:m`, nunca interpolado.
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

MEMBER_LOCK_SQL: Final = "SELECT pg_advisory_xact_lock(hashtextextended(:m, 0))"
"""Candado asesor de transacción por socio; `:m` es `str(member_id)`."""

LOCK_NOT_AVAILABLE: Final = "55P03"
"""SQLSTATE de `lock_timeout` agotado (`lock_not_available`)."""


async def lock_member(session: AsyncSession, member_id: UUID) -> None:
    """Toma el candado del socio dentro de la transacción de `session` (espera si otro lo tiene).

    Traduce la espera agotada (`lock_timeout`, 55P03) a `DatabaseBusy`; cualquier otro error sale
    intacto. El candado se libera solo al terminar la transacción.
    """
    try:
        await session.execute(text(MEMBER_LOCK_SQL), {"m": str(member_id)})
    except DBAPIError as error:
        if sqlstate_of(error) != LOCK_NOT_AVAILABLE:
            raise
        raise DatabaseBusy() from error
