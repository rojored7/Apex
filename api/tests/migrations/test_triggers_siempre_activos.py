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
  (`limpiar_tras_dos_sesiones`), los tres triggers de `memberships.memberships` y los dos de
  `memberships.membership_freezes` (S3-B2) siguen en `'A'`; las congelaciones se borran en un
  bloque propio con su guarda `to_regclass` y antes que las membresías (FK).
S3-B3 (E1) agrega `LIMPIAR_PAYMENTS` (antes que `LIMPIAR_MEMBERSHIPS` en las dos limpiezas): apaga,
borra y enciende `payments_forbid_mutation` y `payments_forbid_truncate` con `ENABLE ALWAYS`, cada
uno bajo su guarda en `pg_trigger` (escrita cuando los triggers aún no existían).
S3-B4 (E1): con `0011_payments_immutability` los dos triggers de `payments.payments` son
obligatorios: tras las dos limpiezas existen y siguen en `'A'`, igual que los cinco de
`memberships` (la lista es exacta).
"""

from __future__ import annotations

import inspect

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.audit import AuditEntry
from tests.conftest import (
    LIMPIAR_MEMBERS,
    LIMPIAR_MEMBERSHIPS,
    LIMPIAR_PAYMENTS,
    LIMPIEZA_DE_SESION,
    TRIGGERS_DE_CONGELACIONES,
    TRIGGERS_DE_MEMBERSHIPS,
    TRIGGERS_DE_PAGOS,
    limpiar_tras_dos_sesiones,
)

TRIGGERS_MEMBRESIAS = (
    "memberships_guard_identity",
    "memberships_forbid_delete",
    "memberships_forbid_truncate",
)
TRIGGERS_CONGELACIONES = (
    "membership_freezes_append_only",
    "membership_freezes_forbid_truncate",
)
TRIGGERS = TRIGGERS_MEMBRESIAS + TRIGGERS_CONGELACIONES
TRIGGERS_PAGOS = ("payments_forbid_mutation", "payments_forbid_truncate")
ESTADO = text(
    "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
    "WHERE NOT tgisinternal AND tgname = ANY(:nombres)"
)


async def _estados(engine: AsyncEngine, nombres: tuple[str, ...] = TRIGGERS) -> dict[str, str]:
    async with engine.connect() as conexion:
        filas = await conexion.execute(ESTADO, {"nombres": list(nombres)})
        return {fila.tgname: fila.estado for fila in filas}


async def _pagos_en_always(engine: AsyncEngine) -> None:
    """S3-B4: los dos de `payments.payments` existen y siguen en `'A'` (obligatorios)."""
    assert await _estados(engine, TRIGGERS_PAGOS) == dict.fromkeys(TRIGGERS_PAGOS, "A")


def test_la_limpieza_enciende_cada_trigger_con_enable_always() -> None:
    assert tuple(TRIGGERS_DE_MEMBERSHIPS) == TRIGGERS_MEMBRESIAS
    assert tuple(TRIGGERS_DE_CONGELACIONES) == TRIGGERS_CONGELACIONES
    assert "to_regclass('memberships.memberships')" in LIMPIAR_MEMBERSHIPS
    assert "to_regclass('memberships.membership_freezes')" in LIMPIAR_MEMBERSHIPS
    assert "DISABLE TRIGGER USER" in LIMPIAR_MEMBERSHIPS
    for nombre in TRIGGERS:
        assert f"ENABLE ALWAYS TRIGGER {nombre};" in LIMPIAR_MEMBERSHIPS, nombre
    assert "ENABLE TRIGGER USER" not in LIMPIAR_MEMBERSHIPS


def test_las_congelaciones_se_borran_antes_que_las_membresias() -> None:
    """La FK de `membership_freezes` a `memberships` exige borrar primero las congelaciones."""
    borrar_congelaciones = LIMPIAR_MEMBERSHIPS.index("DELETE FROM memberships.membership_freezes;")
    borrar_membresias = LIMPIAR_MEMBERSHIPS.index("DELETE FROM memberships.memberships;")
    assert borrar_congelaciones < borrar_membresias
    for nombre in TRIGGERS_CONGELACIONES:
        assert f"membership_freezes ENABLE ALWAYS TRIGGER {nombre};" in LIMPIAR_MEMBERSHIPS


def test_la_limpieza_de_membresias_va_antes_que_la_de_socios() -> None:
    orden = list(LIMPIEZA_DE_SESION)
    assert orden.index(LIMPIAR_MEMBERSHIPS) < orden.index(LIMPIAR_MEMBERS)


def test_la_limpieza_de_pagos_enciende_sus_triggers_con_enable_always_sin_guarda() -> None:
    """S3-B3 (E1): `to_regclass` de la tabla; `ENABLE ALWAYS` por nombre y nunca `ENABLE TRIGGER
    USER`. PL7 de la revisión de Fase 4 del Sprint 3: sin la guarda en `pg_trigger` por trigger
    (`0011` ya existe): si una migración no instalara un trigger, la limpieza falla en lugar de
    esconderlo."""
    assert tuple(TRIGGERS_DE_PAGOS) == TRIGGERS_PAGOS
    assert "to_regclass('payments.payments')" in LIMPIAR_PAYMENTS
    assert "ALTER TABLE payments.payments DISABLE TRIGGER USER;" in LIMPIAR_PAYMENTS
    assert "DELETE FROM payments.payments;" in LIMPIAR_PAYMENTS
    for nombre in TRIGGERS_PAGOS:
        assert f"ENABLE ALWAYS TRIGGER {nombre};" in LIMPIAR_PAYMENTS, nombre
    assert "pg_trigger" not in LIMPIAR_PAYMENTS
    assert "ENABLE TRIGGER USER" not in LIMPIAR_PAYMENTS


def test_los_pagos_se_borran_antes_que_las_membresias_en_las_dos_limpiezas() -> None:
    orden = list(LIMPIEZA_DE_SESION)
    assert orden.index(LIMPIAR_PAYMENTS) < orden.index(LIMPIAR_MEMBERSHIPS)
    fuente = inspect.getsource(limpiar_tras_dos_sesiones)
    assert "text(LIMPIAR_PAYMENTS)" in fuente
    assert fuente.index("text(LIMPIAR_PAYMENTS)") < fuente.index("text(LIMPIAR_MEMBERSHIPS)")


async def test_tras_limpiar_pagos_y_membresias_los_triggers_siguen_en_always(
    engine: AsyncEngine,
) -> None:
    """Solo `LIMPIAR_PAYMENTS` y `LIMPIAR_MEMBERSHIPS` (no toda `LIMPIEZA_DE_SESION`, que borraría
    las llaves del bus de la corrida); los siete triggers quedan en `'A'`."""
    async with engine.begin() as conexion:
        await conexion.execute(text(LIMPIAR_PAYMENTS))
        await conexion.execute(text(LIMPIAR_MEMBERSHIPS))
    assert await _estados(engine) == dict.fromkeys(TRIGGERS, "A")
    await _pagos_en_always(engine)


@pytest.mark.usefixtures("migrated_database")
async def test_tras_la_limpieza_de_dos_sesiones_los_triggers_siguen_en_always(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as conexion:
        ultima = await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0)))
    await limpiar_tras_dos_sesiones(engine, int(ultima or 0))
    assert await _estados(engine) == dict.fromkeys(TRIGGERS, "A")
    await _pagos_en_always(engine)
