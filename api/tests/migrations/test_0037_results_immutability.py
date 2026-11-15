"""`0037_results_immutability` (S8-B1, US-169; S8-D35, M-5). Rojo B1.

Padre `0036_results_wod_results`. Guardas de `results.wod_results`: `INSERT` solo vigente, `UPDATE`
solo `pending -> validated` (con la validación pasando de NULL a valor en el mismo `UPDATE`),
`is_current` de `true` a `false` y `updated_at`; `DELETE` y `TRUNCATE` prohibidos; y un trigger
diferido que exige sucesor a toda fila apagada al confirmar. Todos `ENABLE ALWAYS`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_WOD_RESULTS
from tests.migrations._apoyo_notificaciones import _dsn, consultar, existe, resultados
from tests.migrations.test_0023_attachments import _ejecutar
from tests.migrations.test_0036_results_wod_results import (
    AHORA,
    SYSTEM_USER_ID,
    TABLA,
    fila,
)

REVISION = "0037_results_immutability"
PADRE = "0036_results_wod_results"
GUARDA = "P0001"
TRIGGERS = (
    "wod_results_guard_insert",
    "wod_results_guard_update",
    "wod_results_forbid_delete",
    "wod_results_forbid_truncate",
    "wod_results_require_successor",
)


def _revision_existe(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> Iterator[str]:
    _revision_existe(alembic_config)
    try:
        yield migrated_database
    finally:
        if existe(migrated_database, TABLA):
            _ejecutar(migrated_database, LIMPIAR_WOD_RESULTS)


def _upd(rid: Any, asignacion: str, *args: Any) -> tuple[str, list[Any]]:
    sql = f"UPDATE results.wod_results SET {asignacion} WHERE id = $1"  # noqa: S608
    return sql, [rid, *args]


def test_cuelga_de_0036(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_insert_exige_is_current_true(base: str) -> None:
    salidas = resultados(base, [[fila(current=False)], [fila()]])
    assert salidas == [(GUARDA, None), ("", None)]


@pytest.mark.parametrize(
    "asignacion,args",
    [
        ("updated_at = now()", []),
        ("is_current = false", []),
        ("status = 'validated', validated_by = $2, validated_at = now()", [SYSTEM_USER_ID]),
    ],
    ids=["updated_at", "is_current_a_false", "pending_a_validated"],
)
def test_update_permitido_por_columna(base: str, asignacion: str, args: list[Any]) -> None:
    rid = uuid4()
    pendiente = fila(id=rid, status="pending", vby=None, vat=None)
    assert resultados(base, [[pendiente, _upd(rid, asignacion, *args)]]) == [("", None)]


@pytest.mark.parametrize(
    "asignacion,args",
    [
        ("wod_id = $2", [uuid4()]),
        ("member_id = $2", [uuid4()]),
        ("session_id = $2", [uuid4()]),
        ("wod_date = '2020-01-01'", []),
        ("benchmark_id = $2", [uuid4()]),
        ("level = 'scaled'", []),
        ("seconds = 1", []),
        ("rounds = 1", []),
        ("reps = 1", []),
        ("load_g = 1", []),
        ("capped = true", []),
        ("scaled_movement_ids = ARRAY[$2]::uuid[]", [uuid4()]),
        ("recorded_by = $2", [uuid4()]),
        ("supersedes_id = $2", [uuid4()]),
        ("source = 'kiosk'", []),
        ("created_by = $2", [uuid4()]),
        ("created_at = now() - interval '1 day'", []),
        ("id = $2", [uuid4()]),
    ],
    ids=lambda v: v.split(" ")[0] if isinstance(v, str) else "args",
)
def test_update_prohibido_por_columna(base: str, asignacion: str, args: list[Any]) -> None:
    rid = uuid4()
    assert resultados(base, [[fila(id=rid), _upd(rid, asignacion, *args)]]) == [(GUARDA, None)]


def test_validated_by_no_se_reescribe(base: str) -> None:
    rid = uuid4()
    salidas = resultados(
        base,
        [
            [fila(id=rid), _upd(rid, "validated_by = $2", uuid4())],
            [fila(id=rid), _upd(rid, "validated_at = now()")],
            [fila(id=rid), _upd(rid, "status = 'pending'")],
        ],
    )
    assert [s[0] for s in salidas] == [GUARDA, GUARDA, GUARDA]


def test_pending_a_validated_en_el_mismo_update(base: str) -> None:
    rid = uuid4()
    pendiente = fila(id=rid, status="pending", vby=None, vat=None)
    salidas = resultados(
        base,
        [
            [pendiente, _upd(rid, "status = 'validated'")],  # sin la validación: el CHECK falla
            [pendiente, _upd(rid, "validated_by = $2, validated_at = now()", SYSTEM_USER_ID)],
            [pendiente, _upd(rid, "status = 'validated', validated_by = $2, validated_at = now()",
                             SYSTEM_USER_ID)],
        ],
    )  # fmt: skip
    assert salidas[0][0] == "23514" and salidas[1][0] in {GUARDA, "23514"}
    assert salidas[2] == ("", None)


def test_is_current_no_vuelve_a_true(base: str) -> None:
    rid = uuid4()
    salidas = resultados(
        base,
        [[fila(id=rid), _upd(rid, "is_current = false"), _upd(rid, "is_current = true")]],
    )
    assert salidas == [(GUARDA, None)]


def _confirmar(url: str, pasos: list[tuple[str, list[Any]]]) -> str:
    """Corre los pasos en una transacción y la CONFIRMA; da el sqlstate del primer error."""

    async def correr() -> str:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            transaccion = conexion.transaction()
            await transaccion.start()
            try:
                for sql, args in pasos:
                    await conexion.execute(sql, *args)
                await transaccion.commit()
            except asyncpg.PostgresError as error:
                try:
                    await transaccion.rollback()
                except asyncpg.InterfaceError:  # el COMMIT ya falló: la transacción terminó
                    pass
                return str(error.sqlstate)
            return ""
        finally:
            await conexion.close()

    return asyncio.run(correr())


def test_fila_apagada_sin_sucesor_falla_al_confirmar(base: str) -> None:
    a, b = uuid4(), uuid4()
    sin_sucesor = _confirmar(base, [fila(id=a), _upd(a, "is_current = false")])
    assert sin_sucesor == GUARDA
    assert consultar(base, "SELECT count(*) AS n FROM results.wod_results")[0]["n"] == 0
    con_sucesor = _confirmar(base, [fila(id=a), _upd(a, "is_current = false"), fila(id=b, sup=a)])
    assert con_sucesor == ""
    vigentes = consultar(base, "SELECT id FROM results.wod_results WHERE is_current")
    assert [r["id"] for r in vigentes] == [b]


def test_delete_y_truncate_prohibidos(base: str) -> None:
    rid = uuid4()
    salidas = resultados(
        base,
        [
            [fila(id=rid), ("DELETE FROM results.wod_results WHERE id = $1", [rid])],
            [("TRUNCATE results.wod_results", [])],
        ],
    )
    assert [s[0] for s in salidas] == [GUARDA, GUARDA]


def test_tgenabled_always(base: str) -> None:
    filas = consultar(
        base,
        "SELECT tgname, tgenabled FROM pg_trigger "
        "WHERE tgrelid = 'results.wod_results'::regclass AND NOT tgisinternal",
    )
    assert {r["tgname"]: bytes(r["tgenabled"]).decode() for r in filas} == dict.fromkeys(
        TRIGGERS, "A"
    )


def test_ciclo_downgrade_upgrade(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert existe(base, TABLA)
        assert (
            consultar(
                base,
                "SELECT count(*) AS n FROM pg_trigger "
                "WHERE tgrelid = 'results.wod_results'::regclass AND NOT tgisinternal",
            )[0]["n"]
            == 0
        )
    finally:
        command.upgrade(alembic_config, "head")
    assert (
        len(
            consultar(
                base, "SELECT tgname FROM pg_trigger WHERE tgname = 'wod_results_guard_update'"
            )
        )
        == 1
    )
    _ = AHORA
