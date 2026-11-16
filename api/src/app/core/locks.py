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

Orden ampliado con el check-in (S7-C1, S7-D12): socio (`lock_member`), SESIÓN (`SELECT ... FOR
UPDATE` de `classes.class_sessions`, el mismo candado de fila que toman las cancelaciones),
MEMBRESÍA (la bloquea el puerto `checkin_view`, antes del primer flush) y, al hacer flush, la
cadena. Fuera de `core/locks.py`, el orden de los candados asesores de `classes` es 4_270_005
(franjas), 4_270_006 (generación) y, al primer flush auditado, 4_270_002 (cadena; S7-D37).

Orden del registro de resultados (S8-B1, S8-D36, M-6): socio (`lock_member`), SESIÓN (`FOR SHARE`,
con `status = scheduled`), WOD (`FOR SHARE`), resultado vigente (`FOR UPDATE`) y, al hacer flush,
la cadena. `PATCH /class-sessions/{id}` pide la sesión `FOR UPDATE` y lee el WOD después; `PATCH
/wods/{id}` pide el WOD `FOR UPDATE`: ambos esperan a que el resultado confirme. Nunca se toma el
WOD antes que la sesión ni el resultado antes que el WOD.

Candado de aviso en vuelo (S9-D44, S9-D45): `NOTIFY_LOCK_NS` (4_270_010, en
`modules/notifications/sending.py`) es la primera de DOS claves `int4` de
`pg_try_advisory_xact_lock(ns, k)`; `k` son los 32 bits bajos del id del aviso. Invariantes: es
siempre un TRY (nunca espera), vive en su propia sesión y transacción (sin filas ni otros candados),
y esa sesión nunca pide otro candado, así que no puede entrar en un ciclo. `skip` lo prueba en la
transacción del admin ANTES de bloquear la fila; si no lo obtiene responde 409
`notification_in_flight`.

Los suscriptores de `SessionCancelled`, `SessionGenerated` y `MemberCheckedIn` se ejecutan con
la cadena de auditoría (4_270_002) YA tomada (el evento se emite después del flush): no pueden
pedir candados de socio, de membresía, de sesión ni asesores, porque invertirían este orden y
abrirían un ciclo (S7-B3b). Lo que necesiten bloquear lo bloquea el emisor o un puerto ANTES del
primer flush, como hace el check-in con la membresía.
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
