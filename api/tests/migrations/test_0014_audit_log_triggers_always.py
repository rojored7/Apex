"""`0014_audit_log_triggers_always` (S4B-W0-2; S4B-D4 corregida por E5, S4B-D5, S4B-D6).

Padre `0013_audit_verifications`; desde S5-W0-3 el head es `0015` y esta queda en su cadena.
No crea tablas ni índices. Hace dos cosas:
- `CREATE OR REPLACE FUNCTION audit.forbid_mutation()` con `TG_TABLE_SCHEMA`/`TG_TABLE_NAME`. La
  usan **solo cuatro** triggers (`audit_log_forbid_*` de `0002` y `verifications_forbid_*` de
  `0013`); su único efecto real es que al mutar `audit.verifications` el mensaje deja de decir
  `audit.audit_log` (E5). `crypto.crypto_ops` usa `crypto.forbid_ops_mutation()` con texto fijo,
  y `crypto_keys_guard` y `crypto_jobs_guard` tienen funciones propias: no cambian.
- `ENABLE ALWAYS` por nombre en los ocho triggers de `audit.audit_log` (2) y de las tres tablas
  `crypto.*` (6). Con los dos de `audit.verifications` (ya en `'A'` desde `0013`) son diez.
`downgrade -1`: los ocho vuelven a `'O'`, los de `verifications` siguen en `'A'` y la función
recupera el texto literal de `0002`.
Las filas que cada prueba inserta se borran al terminar con el ayudante `tests.factories.triggers`
(apagar, borrar y encender por nombre con `ALWAYS`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.factories.triggers import (
    ALWAYS_TRIGGERS,
    AUDIT_LOG_TRIGGERS,
    CRYPTO_TRIGGERS,
    VERIFICATIONS_TRIGGERS,
    disable_user_sql,
    rearm_always_sql,
)

REVISION = "0014_audit_log_triggers_always"
PADRE = "0013_audit_verifications"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
INMUTABLE = "P0001"
CHECK_VIOLATION = "23514"  # `crypto.*` usa ERRCODE check_violation (0003)
AHORA = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
HASH = "ab" * 32

TRIGGERS_DE_AUDIT = (*AUDIT_LOG_TRIGGERS, *VERIFICATIONS_TRIGGERS)
TRIGGERS_QUE_CAMBIAN = (
    *AUDIT_LOG_TRIGGERS,
    *(nombre for nombres in CRYPTO_TRIGGERS.values() for nombre in nombres),
)
TODOS = tuple(nombre for nombres in ALWAYS_TRIGGERS.values() for nombre in nombres)


# Ayudas -----------------------------------------------------------------------------------------


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


def _ejecutar(url: str, *sentencias: str) -> None:
    async def correr() -> None:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            for sql in sentencias:
                await conexion.execute(sql)
        finally:
            await conexion.close()

    asyncio.run(correr())


def _error(url: str, *sentencias: str) -> asyncpg.PostgresError | None:
    """El error de la última sentencia (las anteriores preparan la sesión), o `None`."""
    try:
        _ejecutar(url, *sentencias)
    except asyncpg.PostgresError as error:
        return error
    return None


UPDATE_VERIFICATION = (
    "UPDATE audit.verifications SET ok = false, broken_at_seq = 1 WHERE id = '@ID'"
)


def _por_id(plantilla: str, tabla: str, fila: UUID) -> str:
    """Rellena `@T` (tabla de la lista cerrada) y `@ID` (UUID generado por la propia prueba)."""
    return plantilla.replace("@T", tabla).replace("@ID", str(fila))


def _estados(url: str, nombres: tuple[str, ...]) -> dict[str, str]:
    filas = _consultar(
        url,
        "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
        "WHERE NOT tgisinternal AND tgname = ANY($1::text[])",
        list(nombres),
    )
    return {f["tgname"]: f["estado"] for f in filas}


def _borrar_fila(url: str, tabla: str, fila: UUID) -> None:
    """Limpieza: apaga, borra por `id` y vuelve a encender por nombre con `ENABLE ALWAYS`."""
    _ejecutar(
        url,
        disable_user_sql(tabla),
        _por_id("DELETE FROM @T WHERE id = '@ID'", tabla, fila),
        rearm_always_sql(tabla),
    )


@dataclass(frozen=True)
class Tabla:
    nombre: str
    insertar: Any  # (url) -> UUID
    update: str  # sentencia que debe rechazarse (con `{id}`)
    mensaje: str  # texto exacto del RAISE

    @property
    def sqlstate(self) -> str:
        return CHECK_VIOLATION if self.nombre.startswith("crypto.") else INMUTABLE


def _insertar_audit_log(url: str) -> UUID:
    fila = uuid4()
    _ejecutar_con_args(
        url,
        "INSERT INTO audit.audit_log (id, seq, at, user_id, action, table_name, prev_hash, hash, "
        "created_at, updated_at, created_by) VALUES ($1, "
        "(SELECT coalesce(max(seq), 0) + 1 FROM audit.audit_log), $2, $3, 'login', 'auth.users', "
        "$4, $4, $2, $2, $3)",
        fila,
        AHORA,
        SYSTEM_USER_ID,
        HASH,
    )
    return fila


def _insertar_verification(url: str) -> UUID:
    fila = uuid4()
    _ejecutar_con_args(
        url,
        "INSERT INTO audit.verifications (id, started_at, finished_at, through_seq, through_hash, "
        "rows_checked, ok, triggered_by, source, created_by) "
        "VALUES ($1, $2, $2, 1, $3, 1, true, $4, 'api', $4)",
        fila,
        AHORA,
        HASH,
        SYSTEM_USER_ID,
    )
    return fila


def _insertar_crypto_op(url: str) -> UUID:
    fila = uuid4()
    _ejecutar_con_args(
        url,
        "INSERT INTO crypto.crypto_ops (id, created_by, user_id, verb, result) "
        "VALUES ($1, $2, $2, 'encrypt', 'ok')",
        fila,
        SYSTEM_USER_ID,
    )
    return fila


def _insertar_crypto_key(url: str) -> UUID:
    fila = uuid4()
    _ejecutar_con_args(
        url,
        "INSERT INTO crypto.crypto_keys (id, created_by, purpose, data_class, algorithm, "
        "provider, version, state, wrapped_material) "
        "VALUES ($1, $2, 'encrypt', 'prueba.cero_cat', 'A256GCM', 'local', 1, 'active', '\\x00')",
        fila,
        SYSTEM_USER_ID,
    )
    return fila


def _insertar_crypto_job(url: str) -> UUID:
    fila = uuid4()
    _ejecutar_con_args(
        url,
        "INSERT INTO crypto.crypto_jobs (id, created_by, kind, status) "
        "VALUES ($1, $2, 'rotate', 'done')",
        fila,
        SYSTEM_USER_ID,
    )
    return fila


def _ejecutar_con_args(url: str, sql: str, *args: Any) -> None:
    async def correr() -> None:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            await conexion.execute(sql, *args)
        finally:
            await conexion.close()

    asyncio.run(correr())


TABLAS = (
    Tabla(
        "audit.audit_log",
        _insertar_audit_log,
        "UPDATE audit.audit_log SET action = 'verify' WHERE id = '{id}'",
        "audit.audit_log es append-only",
    ),
    Tabla(
        "audit.verifications",
        _insertar_verification,
        "UPDATE audit.verifications SET ok = false, broken_at_seq = 1 WHERE id = '{id}'",
        "audit.verifications es append-only",
    ),
    Tabla(
        "crypto.crypto_ops",
        _insertar_crypto_op,
        "UPDATE crypto.crypto_ops SET verb = 'decrypt' WHERE id = '{id}'",
        "crypto.crypto_ops es append-only",
    ),
    Tabla(
        "crypto.crypto_keys",
        _insertar_crypto_key,
        "UPDATE crypto.crypto_keys SET data_class = 'otra.clase' WHERE id = '{id}'",
        "crypto.crypto_keys: solo cambian state, rotated_*, provider y wrapped_material",
    ),
    Tabla(
        "crypto.crypto_jobs",
        _insertar_crypto_job,
        "UPDATE crypto.crypto_jobs SET kind = 'rewrap' WHERE id = '{id}'",
        "crypto.crypto_jobs: solo cambia el progreso",
    ),
)
IDS = [t.nombre for t in TABLAS]


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> str:
    """La base migrada a head; falla con "no existe la revisión" hasta que exista `0014`."""
    _revision_existe(alembic_config)
    return migrated_database


@pytest.fixture(params=TABLAS, ids=IDS)
def fila(request: pytest.FixtureRequest, base: str) -> Iterator[tuple[str, Tabla, UUID]]:
    tabla: Tabla = request.param
    identificador = tabla.insertar(base)
    try:
        yield base, tabla, identificador
    finally:
        _borrar_fila(base, tabla.nombre, identificador)


# Revisión ---------------------------------------------------------------------------------------


def test_la_revision_existe_cuelga_de_0013_y_esta_en_la_cadena_de_head(
    alembic_config: Config,
) -> None:
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    # S5-W0-3: 0015 es el head; 0014 queda en su cadena.
    assert REVISION in {r.revision for r in scripts.walk_revisions(base="base", head="heads")}
    assert scripts.get_heads() != [REVISION]


# Estado de los triggers -------------------------------------------------------------------------


def test_los_diez_triggers_inmutables_estan_en_always(base: str) -> None:
    assert len(TODOS) == 10
    assert _estados(base, TODOS) == dict.fromkeys(TODOS, "A")


@pytest.mark.parametrize("tabla", list(ALWAYS_TRIGGERS), ids=list(ALWAYS_TRIGGERS))
def test_cada_tabla_tiene_exactamente_sus_triggers_y_todos_en_always(base: str, tabla: str) -> None:
    filas = _consultar(
        base,
        "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
        "WHERE tgrelid = $1::regclass AND NOT tgisinternal",
        tabla,
    )
    assert {f["tgname"]: f["estado"] for f in filas} == dict.fromkeys(ALWAYS_TRIGGERS[tabla], "A")


# Funciones --------------------------------------------------------------------------------------


def test_los_cuatro_triggers_de_audit_siguen_sobre_audit_forbid_mutation(base: str) -> None:
    filas = _consultar(
        base,
        "SELECT tgname, tgfoid = 'audit.forbid_mutation()'::regprocedure AS misma "
        "FROM pg_trigger WHERE NOT tgisinternal AND tgname = ANY($1::text[])",
        list(TRIGGERS_DE_AUDIT),
    )
    assert {f["tgname"]: f["misma"] for f in filas} == dict.fromkeys(TRIGGERS_DE_AUDIT, True)


def test_los_triggers_de_crypto_conservan_sus_funciones_propias(base: str) -> None:
    esperadas = {
        "crypto_ops_forbid_mutation": "crypto.forbid_ops_mutation",
        "crypto_ops_forbid_truncate": "crypto.forbid_ops_mutation",
        "crypto_keys_guard": "crypto.guard_keys_update",
        "crypto_keys_forbid_truncate": "crypto.guard_keys_update",
        "crypto_jobs_guard": "crypto.guard_jobs_mutation",
        "crypto_jobs_forbid_truncate": "crypto.guard_jobs_mutation",
    }
    filas = _consultar(
        base,
        "SELECT t.tgname, n.nspname || '.' || p.proname AS funcion FROM pg_trigger t "
        "JOIN pg_proc p ON p.oid = t.tgfoid JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE NOT t.tgisinternal AND t.tgname = ANY($1::text[])",
        list(esperadas),
    )
    assert {f["tgname"]: f["funcion"] for f in filas} == esperadas


def test_la_funcion_compartida_usa_el_nombre_de_la_tabla_que_dispara(base: str) -> None:
    fuente = _consultar(
        base, "SELECT prosrc FROM pg_proc WHERE oid = 'audit.forbid_mutation()'::regprocedure"
    )[0]["prosrc"]
    assert "TG_TABLE_SCHEMA" in fuente and "TG_TABLE_NAME" in fuente
    assert "audit.audit_log es append-only" not in fuente


# Mensajes (E5) ----------------------------------------------------------------------------------


def test_mutar_audit_verifications_nombra_a_audit_verifications(base: str) -> None:
    identificador = _insertar_verification(base)
    try:
        error = _error(
            base,
            _por_id(UPDATE_VERIFICATION, "", identificador),
        )
    finally:
        _borrar_fila(base, "audit.verifications", identificador)
    assert error is not None and error.sqlstate == INMUTABLE
    assert error.message == "audit.verifications es append-only"


def test_mutar_audit_log_sigue_diciendo_audit_log(base: str) -> None:
    identificador = _insertar_audit_log(base)
    try:
        error = _error(
            base,
            _por_id(
                "UPDATE audit.audit_log SET action = 'verify' WHERE id = '@ID'", "", identificador
            ),
        )
    finally:
        _borrar_fila(base, "audit.audit_log", identificador)
    assert error is not None and error.sqlstate == INMUTABLE
    assert error.message == "audit.audit_log es append-only"


def test_mutar_crypto_ops_da_el_texto_fijo_de_su_propia_funcion(base: str) -> None:
    """Independiente del `CREATE OR REPLACE` de `audit.forbid_mutation`: igual antes y después."""
    identificador = _insertar_crypto_op(base)
    try:
        error = _error(
            base,
            _por_id(
                "UPDATE crypto.crypto_ops SET verb = 'decrypt' WHERE id = '@ID'", "", identificador
            ),
        )
    finally:
        _borrar_fila(base, "crypto.crypto_ops", identificador)
    assert error is not None and error.sqlstate == CHECK_VIOLATION
    assert "append-only" in error.message
    assert error.message == "crypto.crypto_ops es append-only"


# Inmutabilidad, también bajo replica ------------------------------------------------------------

REPLICA = "SET session_replication_role = replica"


def test_update_se_rechaza(fila: tuple[str, Tabla, UUID]) -> None:
    url, tabla, identificador = fila
    error = _error(url, tabla.update.format(id=identificador))
    assert error is not None and error.sqlstate == tabla.sqlstate
    assert error.message == tabla.mensaje


def test_delete_se_rechaza(fila: tuple[str, Tabla, UUID]) -> None:
    url, tabla, identificador = fila
    error = _error(url, _por_id("DELETE FROM @T WHERE id = '@ID'", tabla.nombre, identificador))
    assert error is not None and error.sqlstate == tabla.sqlstate


def test_truncate_se_rechaza(fila: tuple[str, Tabla, UUID]) -> None:
    url, tabla, _ = fila
    error = _error(url, f"TRUNCATE {tabla.nombre}")
    assert error is not None and error.sqlstate == tabla.sqlstate


def test_update_se_rechaza_bajo_replica(fila: tuple[str, Tabla, UUID]) -> None:
    url, tabla, identificador = fila
    error = _error(url, REPLICA, tabla.update.format(id=identificador))
    assert error is not None and error.sqlstate == tabla.sqlstate


def test_delete_se_rechaza_bajo_replica(fila: tuple[str, Tabla, UUID]) -> None:
    url, tabla, identificador = fila
    error = _error(
        url, REPLICA, _por_id("DELETE FROM @T WHERE id = '@ID'", tabla.nombre, identificador)
    )
    assert error is not None and error.sqlstate == tabla.sqlstate


def test_truncate_se_rechaza_bajo_replica(fila: tuple[str, Tabla, UUID]) -> None:
    url, tabla, _ = fila
    error = _error(url, REPLICA, f"TRUNCATE {tabla.nombre}")
    assert error is not None and error.sqlstate == tabla.sqlstate


# Forma ------------------------------------------------------------------------------------------


POSTERIORES_A_0014 = ("member_channel_preferences",)


def _inventario(url: str) -> list[tuple[str, str]]:
    tablas = _consultar(
        url,
        "SELECT schemaname || '.' || tablename AS nombre FROM pg_tables "
        "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') ORDER BY 1",
    )
    indices = _consultar(
        url,
        "SELECT schemaname || '.' || indexname AS nombre FROM pg_indexes "
        "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') ORDER BY 1",
    )
    inventario = [("tabla", f["nombre"]) for f in tablas]
    inventario += [("indice", f["nombre"]) for f in indices]
    # Tablas de migraciones POSTERIORES a 0014 (el downgrade a su padre pasa por ellas y las borra):
    # fuera del inventario, que compara solo lo que 0014 deja intacto (S5-B5, P-MIG 9).
    return [(t, n) for t, n in inventario if not any(x in n for x in POSTERIORES_A_0014)]


# Ciclo ------------------------------------------------------------------------------------------


def test_downgrade_deja_ocho_en_o_verifications_en_a_y_la_funcion_de_0002(
    alembic_config: Config, base: str
) -> None:
    antes = _inventario(base)
    try:
        command.downgrade(alembic_config, PADRE)
        estados = _estados(base, TODOS)
        assert estados == {
            **dict.fromkeys(TRIGGERS_QUE_CAMBIAN, "O"),
            **dict.fromkeys(VERIFICATIONS_TRIGGERS, "A"),
        }
        fuente = _consultar(
            base,
            "SELECT prosrc FROM pg_proc WHERE oid = 'audit.forbid_mutation()'::regprocedure",
        )[0]["prosrc"]
        assert "TG_TABLE_NAME" not in fuente
        assert "audit.audit_log es append-only" in fuente
        # El mensaje de `verifications` vuelve a nombrar `audit.audit_log` (la deuda de V6).
        identificador = _insertar_verification(base)
        try:
            error = _error(
                base,
                _por_id(UPDATE_VERIFICATION, "", identificador),
            )
        finally:
            _borrar_fila(base, "audit.verifications", identificador)
        assert error is not None and error.message == "audit.audit_log es append-only"
        # Sin tablas ni índices nuevos: el inventario es el mismo antes y después.
        assert _inventario(base) == antes
    finally:
        command.upgrade(alembic_config, "head")
    assert _estados(base, TODOS) == dict.fromkeys(TODOS, "A")
    assert _inventario(base) == antes
