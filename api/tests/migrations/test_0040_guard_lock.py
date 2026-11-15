"""L-4 (revisión de C1, S8-C1b): la guarda de INSERT de `0040` lee al anterior CON candado.

`guard_wod_results_insert` comprueba que `supersedes_id` no apunte a un anulado. Sin `FOR SHARE`, un
INSERT concurrente con la anulación del anterior leía el estado previo (READ COMMITTED) y dejaba
pasar un sucesor de un anulado. Con el candado espera a la anulación y la ve. La fixture recrea la
función desde la migración (`downgrade` y `upgrade` de `0040`), así la prueba no depende de lo que
quedara aplicado en `db_test`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from uuid import uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config

from app.core.context import SYSTEM_USER_ID
from tests.conftest import LIMPIAR_WOD_RESULTS
from tests.migrations._apoyo_notificaciones import _dsn, consultar, existe
from tests.migrations.test_0023_attachments import _ejecutar
from tests.migrations.test_0036_results_wod_results import TABLA, fila
from tests.migrations.test_0037_results_immutability import GUARDA

PADRE = "0039_results_updated_guard"
ANULAR = (
    "UPDATE results.wod_results SET status = 'voided', is_current = false, voided_by = $2, "
    "voided_at = now(), void_reason = 'Registrado en el socio equivocado' WHERE id = $1"
)


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> Iterator[str]:
    command.downgrade(alembic_config, PADRE)
    command.upgrade(alembic_config, "head")
    try:
        yield migrated_database
    finally:
        if existe(migrated_database, TABLA):
            _ejecutar(migrated_database, LIMPIAR_WOD_RESULTS)


def test_la_funcion_de_insert_lee_al_anterior_con_for_share(base: str) -> None:
    definicion = consultar(
        base, "SELECT pg_get_functiondef('results.guard_wod_results_insert'::regproc) AS d"
    )[0]["d"]
    assert "FOR SHARE" in definicion


async def _carrera(url: str) -> str:
    """Anula al anterior sin confirmar y, mientras tanto, inserta su sucesor desde otra conexión.
    Devuelve el sqlstate del INSERT (`""` si pasó)."""
    anterior, sucesor = uuid4(), uuid4()
    sql_a, args_a = fila(id=anterior)
    sql_s, args_s = fila(id=sucesor, sup=anterior)
    una = await asyncpg.connect(_dsn(url))
    otra = await asyncpg.connect(_dsn(url))
    try:
        await una.execute(sql_a, *args_a)  # el anterior vigente, ya confirmado (autocommit)
        transaccion_a = una.transaction()
        await transaccion_a.start()
        await una.execute(ANULAR, anterior, SYSTEM_USER_ID)  # sin confirmar

        async def insertar() -> str:
            try:
                await otra.execute(sql_s, *args_s)
            except asyncpg.PostgresError as error:
                return str(error.sqlstate)
            return ""

        tarea = asyncio.create_task(insertar())
        await asyncio.sleep(0.5)
        await transaccion_a.commit()
        return await asyncio.wait_for(tarea, timeout=30)
    finally:
        await una.close()
        await otra.close()


def test_un_sucesor_concurrente_con_la_anulacion_del_anterior_es_rechazado(base: str) -> None:
    assert asyncio.run(_carrera(base)) == GUARDA
