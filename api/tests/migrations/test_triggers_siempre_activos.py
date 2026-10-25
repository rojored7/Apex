"""La limpieza de `db_test` deja los triggers inmutables en `ENABLE ALWAYS` (S3-B1; E1, S3-D49).

`ALTER TABLE ... ENABLE TRIGGER USER` deja `tgenabled = 'O'` y pisa el `'A'` que pone la
migración: bajo `session_replication_role = replica` el trigger dejaría de correr y las pruebas de
réplica de `test_0008` pasarían o fallarían según el orden de la corrida. Por eso
`LIMPIAR_MEMBERSHIPS` (en `LIMPIEZA_DE_SESION` y en el `finally` de `dos_sesiones`) apaga, borra y
vuelve a encender cada trigger por nombre con `ENABLE ALWAYS`.

Se comprueba:
- el texto de `LIMPIAR_MEMBERSHIPS`: un `ENABLE ALWAYS TRIGGER <nombre>` por trigger, ningún
  `ENABLE TRIGGER USER`, dentro de la guarda `to_regclass`; va en `LIMPIEZA_DE_SESION` antes de
  `LIMPIAR_MEMBERS`;
- tras ejecutar **solo** `LIMPIAR_MEMBERSHIPS` (no toda `LIMPIEZA_DE_SESION`, que borraría las
  llaves del bus de la corrida) y tras la limpieza de `dos_sesiones`
  (`limpiar_tras_dos_sesiones`), los tres triggers de `memberships.memberships` siguen en `'A'`.
B2 agrega los dos de `memberships.membership_freezes` y B3/B4 los dos de `payments.payments`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.audit import AuditEntry
from tests.conftest import (
    LIMPIAR_MEMBERS,
    LIMPIAR_MEMBERSHIPS,
    LIMPIEZA_DE_SESION,
    TRIGGERS_DE_MEMBERSHIPS,
    limpiar_tras_dos_sesiones,
)

TRIGGERS = (
    "memberships_guard_identity",
    "memberships_forbid_delete",
    "memberships_forbid_truncate",
)
ESTADO = text(
    "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
    "WHERE NOT tgisinternal AND tgname = ANY(:nombres)"
)


async def _estados(engine: AsyncEngine) -> dict[str, str]:
    async with engine.connect() as conexion:
        filas = await conexion.execute(ESTADO, {"nombres": list(TRIGGERS)})
        return {fila.tgname: fila.estado for fila in filas}


def test_la_limpieza_enciende_cada_trigger_con_enable_always() -> None:
    assert tuple(TRIGGERS_DE_MEMBERSHIPS) == TRIGGERS
    assert "to_regclass('memberships.memberships')" in LIMPIAR_MEMBERSHIPS
    assert "DISABLE TRIGGER USER" in LIMPIAR_MEMBERSHIPS
    for nombre in TRIGGERS:
        assert f"ENABLE ALWAYS TRIGGER {nombre};" in LIMPIAR_MEMBERSHIPS, nombre
    assert "ENABLE TRIGGER USER" not in LIMPIAR_MEMBERSHIPS


def test_la_limpieza_de_membresias_va_antes_que_la_de_socios() -> None:
    orden = list(LIMPIEZA_DE_SESION)
    assert orden.index(LIMPIAR_MEMBERSHIPS) < orden.index(LIMPIAR_MEMBERS)


async def test_tras_limpiar_membresias_los_triggers_siguen_en_always(
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as conexion:
        await conexion.execute(text(LIMPIAR_MEMBERSHIPS))
    assert await _estados(engine) == dict.fromkeys(TRIGGERS, "A")


@pytest.mark.usefixtures("migrated_database")
async def test_tras_la_limpieza_de_dos_sesiones_los_triggers_siguen_en_always(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as conexion:
        ultima = await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0)))
    await limpiar_tras_dos_sesiones(engine, int(ultima or 0))
    assert await _estados(engine) == dict.fromkeys(TRIGGERS, "A")
