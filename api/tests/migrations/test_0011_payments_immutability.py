"""`0011_payments_immutability` (S3-B4, US-096; blueprint B4; D13, M-6, L-10, S3-D49).

Padre `0010_payments`; es head. Agrega:
- la función `payments.forbid_mutation()` (`plpgsql`, `SECURITY INVOKER`, `SET search_path =
  pg_catalog`; su comportamiento lo prueba `tests/payments/test_immutability.py`);
- los triggers `payments_forbid_mutation` (`BEFORE UPDATE OR DELETE ... FOR EACH ROW`) y
  `payments_forbid_truncate` (`BEFORE TRUNCATE ... FOR EACH STATEMENT`), los dos con
  `ENABLE ALWAYS` (`tgenabled = 'A'`, M-6): `session_replication_role = replica` no los salta.
`pg_get_triggerdef` reordena los eventos: imprime `BEFORE DELETE OR UPDATE`.
El `downgrade` borra los dos triggers y la función y no toca filas: el ciclo se prueba con un pago
confirmado que se cuenta (y se relee) antes del `downgrade`, entre medio y después del `upgrade`.
Al terminar, `LIMPIAR_PAYMENTS` lo borra y vuelve a encender los triggers con `ENABLE ALWAYS`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_PAYMENTS

REVISION = "0011_payments_immutability"
PADRE = "0010_payments"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
PAGADO = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
TRIGGERS = ("payments_forbid_mutation", "payments_forbid_truncate")


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _revision_existe(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:  # alembic.util.CommandError o ResolutionError
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")


def _consultar(url: str, sql: str, *args: Any) -> list[asyncpg.Record]:
    async def correr() -> list[asyncpg.Record]:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            return list(await conexion.fetch(sql, *args))
        finally:
            await conexion.close()

    return asyncio.run(correr())


def _ejecutar(url: str, sql: str, *args: Any) -> None:
    async def correr() -> None:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            await conexion.execute(sql, *args)
        finally:
            await conexion.close()

    asyncio.run(correr())


def _estado(url: str) -> dict[str, Any]:
    funciones = _consultar(
        url,
        "SELECT p.prosecdef, p.proconfig, l.lanname FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace JOIN pg_language l ON l.oid = p.prolang "
        "WHERE n.nspname = 'payments' AND p.proname = 'forbid_mutation'",
    )
    triggers = _consultar(
        url,
        "SELECT tgname, tgenabled::text AS estado, pg_get_triggerdef(oid) AS def FROM pg_trigger "
        "WHERE tgrelid = 'payments.payments'::regclass AND NOT tgisinternal",
    )
    return {
        "funcion": [dict(f) for f in funciones],
        "triggers": {t["tgname"]: (t["estado"], t["def"]) for t in triggers},
    }


def _filas(url: str) -> list[dict[str, Any]]:
    return [
        dict(f) for f in _consultar(url, "SELECT * FROM payments.payments ORDER BY created_at, id")
    ]


def _insertar_confirmado(url: str) -> UUID:
    pago_id = uuid4()
    _ejecutar(
        url,
        "INSERT INTO payments.payments (id, created_by, membership_id, member_id, amount_cop, "
        "method, paid_at, registered_by) VALUES ($1, $2, $3, $4, 120000, 'cash', $5, $2)",
        pago_id,
        SYSTEM_USER_ID,
        uuid4(),
        uuid4(),
        PAGADO,
    )
    return pago_id


def test_la_revision_existe_cuelga_de_0010_y_es_head(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    assert scripts.get_heads() == [REVISION]


def test_la_funcion_existe_como_security_invoker_plpgsql(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    funcion = _estado(migrated_database)["funcion"]
    assert len(funcion) == 1, funcion
    assert funcion[0]["prosecdef"] is False
    assert funcion[0]["lanname"] == "plpgsql"
    assert list(funcion[0]["proconfig"] or []) == ["search_path=pg_catalog"]


def test_los_dos_triggers_existen_en_enable_always(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    triggers = _estado(migrated_database)["triggers"]
    assert set(triggers) == set(TRIGGERS)
    assert {nombre: estado for nombre, (estado, _) in triggers.items()} == dict.fromkeys(
        TRIGGERS, "A"
    )
    fila = triggers["payments_forbid_mutation"][1]
    assert "BEFORE DELETE OR UPDATE" in fila and "FOR EACH ROW" in fila
    assert "payments.forbid_mutation()" in fila
    vaciado = triggers["payments_forbid_truncate"][1]
    assert "BEFORE TRUNCATE" in vaciado and "FOR EACH STATEMENT" in vaciado
    assert "payments.forbid_mutation()" in vaciado


def test_ciclo_de_0011_sin_tocar_filas(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    pago_id = _insertar_confirmado(migrated_database)
    try:
        antes = _filas(migrated_database)
        assert pago_id in {f["id"] for f in antes}
        command.downgrade(alembic_config, PADRE)
        sin_inmutabilidad = _estado(migrated_database)
        assert sin_inmutabilidad == {"funcion": [], "triggers": {}}
        assert _filas(migrated_database) == antes
        command.upgrade(alembic_config, "head")
        assert _filas(migrated_database) == antes
        triggers = _estado(migrated_database)["triggers"]
        assert {n: e for n, (e, _) in triggers.items()} == dict.fromkeys(TRIGGERS, "A")
    finally:
        command.upgrade(alembic_config, "head")
        _ejecutar(migrated_database, LIMPIAR_PAYMENTS)
    assert _filas(migrated_database) == []
    triggers = _estado(migrated_database)["triggers"]
    assert {n: e for n, (e, _) in triggers.items()} == dict.fromkeys(TRIGGERS, "A")
