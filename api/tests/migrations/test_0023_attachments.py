"""`0023_attachments` (S6-C1, US-147; S6-D25, S6-D108). Rojo C1.

Padre `0022_verify_signatures`; identificador de 31 caracteres o menos (S6-D103: cabe en el
`varchar(32)` de `alembic_version`). Crea:
- el esquema `attachments` y `attachments.attachments`: `id uuid` PK, `owner_table text` (CHECK solo
  `members`), `owner_id uuid` (sin FK entre esquemas), `kind text` (`photo|consent|other`),
  `filename_random text` único (CHECK de 32 hexadecimales en minúscula), `mime text` (tres tipos),
  `size_bytes bigint` (1 a 5.242.880), `sensitive boolean`, `key_id uuid` nulo,
  `storage_provider text` (`local|s3`), `uploaded_by uuid`, `created_at`, `updated_at`,
  `created_by`; CHECK que obliga `sensitive` con `kind = 'consent'` y CHECK
  `sensitive = (key_id IS NOT NULL)`; índice `(owner_table, owner_id, kind, created_at DESC)`;
- tres triggers `ENABLE ALWAYS` (`tgenabled = 'A'`): `attachments_guard_update` (un `UPDATE` solo
  puede cambiar `key_id` y `updated_at`), `attachments_forbid_delete` y
  `attachments_forbid_truncate`; sus funciones son `SECURITY INVOKER` con
  `SET search_path = pg_catalog` (como A1);
- S6-D108: el índice `ix_crypto_ops_user_id_at` sobre `crypto.crypto_ops (user_id, at DESC)`;
- S6-D112: el índice parcial `ix_attachments_key_id (key_id) WHERE key_id IS NOT NULL`.
`downgrade`: triggers, funciones, tabla, índices y esquema; ciclo `head -> base -> head`. Cada CHECK
se prueba con SQL crudo (asyncpg): 23514; la inmutabilidad con `P0001`. Sobre `apex_roles` (roles
reales): `apex_api` inserta y actualiza `key_id`, no borra ni cambia `kind`; `apex_worker` no lee.
"""

# ruff: noqa: S608
from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_ATTACHMENTS
from tests.factories.triggers import disable_user_sql, rearm_always_sql
from tests.migrations._apoyo_notificaciones import (
    CHECK_VIOLATION,
    UNIQUE_VIOLATION,
    columnas,
    consultar,
    existe,
    resultados,
)
from tests.migrations.conftest import RolesDb
from tests.migrations.test_db_grants import como, intentar, propietario

REVISION = "0023_attachments"
PADRE = "0022_verify_signatures"
TABLA = "attachments.attachments"
INMUTABLE = "P0001"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
LLAVE = UUID("00000000-0000-0000-0000-0000000000c1")
LLAVE_2 = UUID("00000000-0000-0000-0000-0000000000c2")
CLASE_LLAVES = "prueba.cero_veintitres"  # `0025` exige una llave real para `key_id` (FK)
AHORA = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
TRIGGERS = ("attachments_guard_update", "attachments_forbid_delete", "attachments_forbid_truncate")
INDICE_OPS = "ix_crypto_ops_user_id_at"

COLUMNAS = {
    "id": ("uuid", "NO"),
    "owner_table": ("text", "NO"),
    "owner_id": ("uuid", "NO"),
    "kind": ("text", "NO"),
    "filename_random": ("text", "NO"),
    "mime": ("text", "NO"),
    "size_bytes": ("bigint", "NO"),
    "sensitive": ("boolean", "NO"),
    "key_id": ("uuid", "YES"),
    "storage_provider": ("text", "NO"),
    "uploaded_by": ("uuid", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
    "created_by": ("uuid", "NO"),
}


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _ejecutar(url: str, *sentencias: str) -> None:
    async def correr() -> None:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            for sql in sentencias:
                await conexion.execute(sql)
        finally:
            await conexion.close()

    asyncio.run(correr())


def _sql_llave(id_: UUID) -> str:
    """Una llave `retired` con ese id (versión única por id), para cumplir la FK de `0025`."""
    return (
        "INSERT INTO crypto.crypto_keys (id, created_by, purpose, data_class, algorithm, "
        f"provider, version, state, wrapped_material) VALUES ('{id_}', '{SYSTEM_USER_ID}', "
        f"'encrypt', '{CLASE_LLAVES}', 'A256GCM', 'local', {int(id_.int % 2_000_000_000) + 1}, "
        "'retired', decode('01', 'hex')) ON CONFLICT (id) DO NOTHING"
    )


def _llave_real(url: str, *ids: UUID) -> None:
    _ejecutar(url, *[_sql_llave(i) for i in ids])


def _borrar_llaves(url: str) -> None:
    _ejecutar(
        url,
        disable_user_sql("crypto.crypto_keys"),
        f"DELETE FROM crypto.crypto_keys WHERE data_class = '{CLASE_LLAVES}'",
        rearm_always_sql("crypto.crypto_keys"),
    )


def _sqlstate(url: str, *sentencias: str) -> str | None:
    try:
        _ejecutar(url, *sentencias)
    except asyncpg.PostgresError as error:
        return str(error.sqlstate)
    return None


def _fila(**cambios: Any) -> dict[str, Any]:
    """Una foto válida: no sensible, sin llave, local."""
    fila: dict[str, Any] = {
        "id": uuid4(),
        "owner_table": "members",
        "owner_id": uuid4(),
        "kind": "photo",
        "filename_random": uuid4().hex,
        "mime": "image/jpeg",
        "size_bytes": 1024,
        "sensitive": False,
        "key_id": None,
        "storage_provider": "local",
        "uploaded_by": SYSTEM_USER_ID,
        "created_at": AHORA,
        "updated_at": AHORA,
        "created_by": SYSTEM_USER_ID,
    }
    fila.update(cambios)
    return fila


def _sensible(**cambios: Any) -> dict[str, Any]:
    return _fila(kind="consent", mime="application/pdf", sensitive=True, key_id=LLAVE, **cambios)


def _paso(fila: dict[str, Any]) -> tuple[str, list[Any]]:
    cols = list(fila)
    marcas = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
    sql = f"INSERT INTO {TABLA} ({', '.join(cols)}) VALUES ({marcas})"
    return sql, [fila[c] for c in cols]


def _insertar(url: str, fila: dict[str, Any] | None = None) -> UUID:
    fila = fila or _fila()
    sql, args = _paso(fila)

    async def correr() -> None:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            await conexion.execute(sql, *args)
        finally:
            await conexion.close()

    asyncio.run(correr())
    return UUID(str(fila["id"]))


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
    """La base migrada con `0023`; borra los adjuntos que la prueba deje."""
    _revision_existe(alembic_config)
    _llave_real(migrated_database, LLAVE)
    try:
        yield migrated_database
    finally:
        if existe(migrated_database, TABLA):
            _ejecutar(migrated_database, LIMPIAR_ATTACHMENTS)
        _borrar_llaves(migrated_database)


# Revisión ---------------------------------------------------------------------------------------


def test_la_revision_cuelga_de_0022_tiene_id_corto_y_esta_en_la_cadena(
    alembic_config: Config,
) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 31  # S6-D103: `alembic_version.version_num` es varchar(32)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_el_esquema_attachments_existe(base: str) -> None:
    assert consultar(base, "SELECT 1 FROM pg_namespace WHERE nspname = 'attachments'")


# Forma de la tabla -------------------------------------------------------------------------------


def test_columnas_tipos_y_nulabilidad(base: str) -> None:
    assert columnas(base, TABLA) == COLUMNAS


def test_indices_pk_filename_unico_y_el_de_consulta_por_dueno(base: str) -> None:
    filas = consultar(
        base,
        "SELECT indexdef FROM pg_indexes WHERE schemaname = 'attachments' "
        "AND tablename = 'attachments'",
    )
    definiciones = [f["indexdef"] for f in filas]
    assert len(filas) == 4, definiciones  # PK, `filename_random` único, dueño y `key_id` parcial
    assert any(
        d.startswith("CREATE UNIQUE INDEX") and d.endswith("(filename_random)")
        for d in definiciones
    )
    assert any(
        "UNIQUE" not in d and d.endswith("(owner_table, owner_id, kind, created_at DESC)")
        for d in definiciones
    )
    assert any(  # S6-D112
        "ix_attachments_key_id" in d and d.endswith("(key_id) WHERE (key_id IS NOT NULL)")
        for d in definiciones
    )


def test_una_foto_valida_y_una_autorizacion_valida_entran(base: str) -> None:
    _insertar(base, _fila())
    _insertar(base, _sensible())
    _insertar(base, _fila(kind="other", mime="image/png", storage_provider="s3"))
    _insertar(base, _fila(size_bytes=1))
    _insertar(base, _fila(size_bytes=5_242_880))
    total = consultar(base, f"SELECT count(*) AS n FROM {TABLA}")[0]["n"]
    assert total == 5


def test_el_nombre_aleatorio_repetido_viola_el_indice_unico(base: str) -> None:
    nombre = uuid4().hex
    _insertar(base, _fila(filename_random=nombre))
    estado, _ = resultados(base, [[_paso(_fila(filename_random=nombre))]])[0]
    assert estado == UNIQUE_VIOLATION


# CHECKs (23514) ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fila", "motivo"),
    [
        (_fila(owner_table="plans"), "owner_table_ajena"),
        (_fila(owner_table="Members"), "owner_table_en_mayusculas"),
        (_fila(kind="avatar"), "kind_ajeno"),
        (_fila(kind="PHOTO"), "kind_en_mayusculas"),
        (_fila(filename_random="a" * 31), "nombre_de_31"),
        (_fila(filename_random="a" * 33), "nombre_de_33"),
        (_fila(filename_random="A" * 32), "nombre_en_mayusculas"),
        (_fila(filename_random="g" * 32), "nombre_no_hexadecimal"),
        (_fila(filename_random="a" * 31 + "/"), "nombre_con_barra"),
        (_fila(filename_random="a" * 32 + "\n"), "nombre_con_salto"),
        (_fila(mime="image/gif"), "mime_ajeno"),
        (_fila(mime="text/html"), "mime_html"),
        (_fila(size_bytes=0), "tamano_cero"),
        (_fila(size_bytes=-1), "tamano_negativo"),
        (_fila(size_bytes=5_242_881), "tamano_sobre_el_tope"),
        (_fila(storage_provider="gcs"), "proveedor_ajeno"),
        (_fila(kind="consent", mime="application/pdf"), "consent_no_sensible"),
        (_fila(sensitive=True, key_id=None), "sensible_sin_llave"),
        (_fila(sensitive=False, key_id=LLAVE), "no_sensible_con_llave"),
    ],
    ids=lambda x: x if isinstance(x, str) else "",
)
def test_cada_check_rechaza(base: str, fila: dict[str, Any], motivo: str) -> None:
    estado, _ = resultados(base, [[_paso(fila)]])[0]
    assert estado == CHECK_VIOLATION, motivo


def test_other_puede_ser_sensible_o_no_pero_siempre_coherente_con_key_id(base: str) -> None:
    estados = resultados(
        base,
        [
            [_paso(_fila(kind="other", mime="application/pdf"))],
            [_paso(_fila(kind="other", mime="application/pdf", sensitive=True, key_id=LLAVE))],
        ],
    )
    assert [e for e, _ in estados] == ["", ""]


# Inmutabilidad -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "columna",
    [
        "owner_table = 'members'",
        "owner_id = gen_random_uuid()",
        "kind = 'other'",
        "filename_random = 'f' || substr(filename_random, 2)",
        "mime = 'image/png'",
        "size_bytes = size_bytes + 1",
        "storage_provider = 's3'",
        "uploaded_by = gen_random_uuid()",
        "created_by = gen_random_uuid()",
        "created_at = now()",
        "id = gen_random_uuid()",
        "key_id = key_id, kind = 'other'",
        "updated_at = now(), mime = 'image/png'",
    ],
    ids=[
        "owner_table",
        "owner_id",
        "kind",
        "filename_random",
        "mime",
        "size_bytes",
        "storage_provider",
        "uploaded_by",
        "created_by",
        "created_at",
        "id",
        "key_id_y_kind",
        "updated_at_y_mime",
    ],
)
def test_un_update_que_toque_otra_columna_que_key_id_o_updated_at_se_rechaza(
    base: str, columna: str
) -> None:
    _insertar(base, _fila())
    assert _sqlstate(base, f"UPDATE {TABLA} SET {columna}") == INMUTABLE


def test_update_de_sensitive_se_rechaza_con_el_trigger_no_solo_con_el_check(base: str) -> None:
    _insertar(base, _fila(kind="other", mime="image/png"))
    sentencia = f"UPDATE {TABLA} SET sensitive = true, key_id = gen_random_uuid()"
    assert _sqlstate(base, sentencia) == INMUTABLE


def test_el_recifrado_puede_cambiar_key_id_y_updated_at(base: str) -> None:
    id_ = _insertar(base, _sensible())
    nueva = uuid4()
    _llave_real(base, nueva)
    assert _sqlstate(base, f"UPDATE {TABLA} SET key_id = '{nueva}' WHERE id = '{id_}'") is None
    assert _sqlstate(base, f"UPDATE {TABLA} SET updated_at = now() WHERE id = '{id_}'") is None
    fila = consultar(base, f"SELECT key_id FROM {TABLA} WHERE id = $1", id_)[0]
    assert fila["key_id"] == nueva


def test_el_recifrado_no_puede_dejar_un_sensible_sin_llave(base: str) -> None:
    id_ = _insertar(base, _sensible())
    assert _sqlstate(base, f"UPDATE {TABLA} SET key_id = NULL WHERE id = '{id_}'") == (
        CHECK_VIOLATION
    )


@pytest.mark.parametrize("sentencia", [f"DELETE FROM {TABLA}", f"TRUNCATE {TABLA}"])
def test_delete_y_truncate_se_rechazan(base: str, sentencia: str) -> None:
    _insertar(base, _fila())
    assert _sqlstate(base, sentencia) == INMUTABLE
    assert len(consultar(base, f"SELECT id FROM {TABLA}")) == 1


@pytest.mark.parametrize(
    "sentencia",
    [f"UPDATE {TABLA} SET kind = 'other'", f"DELETE FROM {TABLA}", f"TRUNCATE {TABLA}"],
    ids=["update", "delete", "truncate"],
)
def test_bajo_replica_los_triggers_siguen_disparando(base: str, sentencia: str) -> None:
    _insertar(base, _fila())
    estado = _sqlstate(base, "SET session_replication_role = replica", sentencia)
    assert estado == INMUTABLE
    assert len(consultar(base, f"SELECT id FROM {TABLA}")) == 1


def test_los_tres_triggers_estan_en_always_con_la_definicion_esperada(base: str) -> None:
    filas = consultar(
        base,
        "SELECT t.tgname, t.tgenabled::text AS estado, pg_get_triggerdef(t.oid) AS def, "
        "n.nspname AS esquema FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid "
        "JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE t.tgrelid = 'attachments.attachments'::regclass AND NOT t.tgisinternal",
    )
    por_nombre = {f["tgname"]: f for f in filas}
    assert set(por_nombre) == set(TRIGGERS)
    assert {f["estado"] for f in filas} == {"A"}
    assert "BEFORE UPDATE" in por_nombre["attachments_guard_update"]["def"]
    assert "FOR EACH ROW" in por_nombre["attachments_guard_update"]["def"]
    assert "BEFORE DELETE" in por_nombre["attachments_forbid_delete"]["def"]
    assert "FOR EACH ROW" in por_nombre["attachments_forbid_delete"]["def"]
    assert "BEFORE TRUNCATE" in por_nombre["attachments_forbid_truncate"]["def"]
    assert {f["esquema"] for f in filas} == {"attachments"}


def test_las_funciones_del_esquema_son_security_invoker_con_search_path_fijo(base: str) -> None:
    funciones = consultar(
        base,
        "SELECT p.proname, p.prosecdef AS definer, p.proconfig AS config "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'attachments'",
    )
    assert funciones, "el esquema attachments debe tener las funciones de los triggers"
    assert "guard_update" in {f["proname"] for f in funciones}
    for funcion in funciones:
        # `pg_get_functiondef` omite `SECURITY INVOKER`: se lee `prosecdef`.
        assert funcion["definer"] is False, funcion["proname"]
        assert "search_path=pg_catalog" in (funcion["config"] or []), funcion["proname"]


def test_no_hay_llave_foranea_hacia_otros_esquemas(base: str) -> None:
    """`owner_id` es una referencia lógica (sin FK); `key_id` la reforzó `0025` hacia `crypto`."""
    filas = consultar(
        base,
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = 'attachments.attachments'::regclass AND contype = 'f'",
    )
    assert [f["conname"] for f in filas] == ["fk_attachments_key_id"]


# S6-D108: índice de la bitácora de operaciones ---------------------------------------------------


def test_el_indice_user_id_at_de_crypto_ops_nace_con_la_0023(base: str) -> None:
    filas = consultar(
        base,
        "SELECT indexdef FROM pg_indexes WHERE schemaname = 'crypto' "
        "AND tablename = 'crypto_ops' AND indexname = $1",
        INDICE_OPS,
    )
    assert len(filas) == 1
    assert filas[0]["indexdef"].endswith("(user_id, at DESC)")
    assert "UNIQUE" not in filas[0]["indexdef"]


# Ciclo ------------------------------------------------------------------------------------------


def _funciones(url: str) -> list[str]:
    return [
        f["proname"]
        for f in consultar(
            url,
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'attachments'",
        )
    ]


def test_downgrade_quita_tabla_triggers_funciones_indices_y_esquema(
    alembic_config: Config, base: str
) -> None:
    assert existe(base, TABLA)
    try:
        command.downgrade(alembic_config, PADRE)
        assert not existe(base, TABLA)
        assert _funciones(base) == []
        assert (
            consultar(
                base, "SELECT tgname FROM pg_trigger WHERE tgname = ANY($1::text[])", list(TRIGGERS)
            )
            == []
        )
        assert consultar(base, "SELECT 1 FROM pg_namespace WHERE nspname = 'attachments'") == []
        assert consultar(base, "SELECT 1 FROM pg_indexes WHERE indexname = $1", INDICE_OPS) == []
        # Lo anterior no se toca: la cadena de auditoría y `crypto_ops` siguen ahí.
        assert existe(base, "audit.audit_log") and existe(base, "crypto.crypto_ops")
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA) and len(_funciones(base)) >= 1
    assert consultar(base, "SELECT 1 FROM pg_indexes WHERE indexname = $1", INDICE_OPS)


def test_ciclo_head_base_head(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, "base")
        assert not existe(base, TABLA)
        assert consultar(base, "SELECT 1 FROM pg_namespace WHERE nspname = 'attachments'") == []
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)


def test_el_downgrade_con_filas_no_las_conserva_y_no_deja_objetos_de_trigger(
    alembic_config: Config, base: str
) -> None:
    """Rollback de `0023` (RUNBOOK §6): las filas se pierden con la tabla; los objetos del volumen
    quedan huérfanos y los detecta `attachments-check`. El trigger de `DELETE` no frena el
    `DROP TABLE` del downgrade."""
    _insertar(base, _fila())
    try:
        command.downgrade(alembic_config, PADRE)
        assert not existe(base, TABLA)
    finally:
        command.upgrade(alembic_config, "head")
    assert consultar(base, f"SELECT count(*) AS n FROM {TABLA}")[0]["n"] == 0


# Roles reales (apex_roles) ------------------------------------------------------------------------

FILA_SQL = (
    "INSERT INTO attachments.attachments (id, owner_table, owner_id, kind, filename_random, mime, "
    "size_bytes, sensitive, key_id, storage_provider, uploaded_by, created_by) VALUES "
    "('{id}', 'members', gen_random_uuid(), 'consent', '{nombre}', 'application/pdf', 10, true, "
    "'{llave}', 'local', '{u}', '{u}')"
)


@pytest.fixture(scope="module")
def llaves_roles(apex_roles: RolesDb) -> None:
    """Dos llaves reales en `apex_roles`: el api inserta y recifra con `key_id` válido (FK)."""
    propietario(apex_roles, _sql_llave(LLAVE), _sql_llave(LLAVE_2))


def _insert_sql() -> str:
    return FILA_SQL.format(id=uuid4(), nombre=uuid4().hex, u=SYSTEM_USER_ID, llave=LLAVE)


@pytest.mark.usefixtures("llaves_roles")
def test_apex_api_inserta_y_actualiza_key_id_pero_no_borra_ni_cambia_kind(
    apex_roles: RolesDb,
) -> None:
    dsn = como(apex_roles, "apex_api")
    assert intentar(dsn, _insert_sql()) is None
    assert (
        intentar(
            dsn,
            _insert_sql(),
            f"UPDATE {TABLA} SET key_id = '{LLAVE_2}', updated_at = now()",
        )
        is None
    )
    for prohibida in (
        f"UPDATE {TABLA} SET kind = 'other'",
        f"UPDATE {TABLA} SET filename_random = 'x'",
        f"DELETE FROM {TABLA}",
        f"TRUNCATE {TABLA}",
    ):
        error = intentar(dsn, _insert_sql(), prohibida)
        assert error is not None and error.sqlstate == "42501", prohibida  # insufficient_privilege


def test_apex_worker_no_lee_ni_escribe_adjuntos(apex_roles: RolesDb) -> None:
    dsn = como(apex_roles, "apex_worker")
    for sentencia in (
        f"SELECT count(*) FROM {TABLA}",
        _insert_sql(),
        f"UPDATE {TABLA} SET key_id = NULL",
        f"DELETE FROM {TABLA}",
    ):
        error = intentar(dsn, sentencia)
        assert error is not None and error.sqlstate == "42501", sentencia


def test_apex_backup_lee_los_adjuntos_y_no_escribe(apex_roles: RolesDb) -> None:
    dsn = como(apex_roles, "apex_backup")
    assert intentar(dsn, f"SELECT count(*) FROM {TABLA}") is None
    error = intentar(dsn, _insert_sql())
    assert error is not None and error.sqlstate == "42501"
