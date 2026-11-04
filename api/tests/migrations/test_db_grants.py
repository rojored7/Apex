"""Roles de aplicación y `grants.sql` (S4B-W0-3; S4B-D7, D9, D61, D71, D72, D101).

Todo corre contra la base `apex_roles` de `db_test` (fixture `apex_roles`, con `roles.sql` y
`grants.sql` REALES aplicados por `psql`) y conexiones por rol con `asyncpg`. Las sentencias que
escriben van dentro de una transacción que siempre se revierte.

La matriz `PRIVILEGIOS` es el inventario de W0-3.1 (greps de `delete(`, `update(`,
`with_for_update`, `begin_nested` y `text(` sobre `api/src/app`, más el catálogo real de la base):
qué rol tiene qué verbo por tabla y qué columnas puede actualizar. Una tabla que falte aquí o en
el encabezado de `grants.sql` rompe la prueba de clasificación (fallo cerrado).

Formato que `grants.sql` debe cumplir en su encabezado: una línea de comentario
`-- clasificada: <esquema>.<tabla>` por tabla clasificada (la lista literal que el bloque final
`DO $$ ... RAISE EXCEPTION 'tabla sin clasificar: %' $$` también recorre).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Iterator
from typing import Any
from uuid import uuid4

import asyncpg
import pytest

from app.core.config import Settings
from tests.migrations.conftest import (
    CLAVES,
    INFRA_DB,
    ROLES,
    RolesDb,
    aplicar_archivo,
    entorno_de_claves,
    psql_en_db_test,
)

SYSTEM = "00000000-0000-0000-0000-000000000001"
PRIVACION = "42501"  # insufficient_privilege

ESQUEMAS = (
    "audit",
    "auth",
    "crypto",
    "members",
    "memberships",
    "payments",
    "plans",
    "settings",
    "worker",
    "public",
)

TODAS = "*"  # UPDATE de todas las columnas (privilegio de tabla)

# tabla -> rol -> (verbos de tabla, columnas con UPDATE ("*" = todas, () = ninguna))
PRIVILEGIOS: dict[str, dict[str, tuple[frozenset[str], frozenset[str]]]] = {
    "audit.audit_log": {
        "apex_api": (frozenset({"SELECT", "INSERT"}), frozenset()),
        "apex_worker": (frozenset({"SELECT", "INSERT"}), frozenset()),
    },
    "audit.verifications": {
        "apex_api": (frozenset({"SELECT", "INSERT"}), frozenset()),
        "apex_worker": (frozenset(), frozenset()),
    },
    "auth.one_time_tokens": {
        "apex_api": (frozenset({"SELECT", "INSERT"}), frozenset({TODAS})),
        "apex_worker": (frozenset(), frozenset()),
    },
    "auth.refresh_tokens": {
        "apex_api": (frozenset({"SELECT", "INSERT", "DELETE"}), frozenset({TODAS})),
        "apex_worker": (frozenset(), frozenset()),
    },
    "auth.users": {
        "apex_api": (frozenset({"SELECT", "INSERT"}), frozenset({TODAS})),
        "apex_worker": (frozenset({"SELECT"}), frozenset()),
    },
    "crypto.crypto_jobs": {
        "apex_api": (frozenset({"SELECT"}), frozenset()),
        "apex_worker": (frozenset({"SELECT"}), frozenset()),
    },
    "crypto.crypto_keys": {
        "apex_api": (frozenset({"SELECT", "INSERT"}), frozenset({"updated_at"})),
        "apex_worker": (frozenset(), frozenset()),
    },
    "crypto.crypto_ops": {
        "apex_api": (frozenset({"SELECT", "INSERT"}), frozenset()),
        "apex_worker": (frozenset({"SELECT", "INSERT"}), frozenset()),
    },
    "members.members": {
        "apex_api": (frozenset({"SELECT", "INSERT"}), frozenset({TODAS})),
        "apex_worker": (frozenset({"SELECT"}), frozenset()),
    },
    "memberships.membership_freezes": {
        "apex_api": (frozenset({"SELECT", "INSERT"}), frozenset()),
        "apex_worker": (frozenset({"SELECT"}), frozenset()),
    },
    "memberships.memberships": {
        "apex_api": (
            frozenset({"SELECT", "INSERT"}),
            frozenset(
                {
                    "end_date",
                    "classes_remaining",
                    "status",
                    "cancel_reason",
                    "cancelled_by",
                    "cancelled_at",
                    "updated_at",
                }
            ),
        ),
        "apex_worker": (frozenset({"SELECT"}), frozenset({"status", "updated_at"})),
    },
    "payments.payments": {
        "apex_api": (
            frozenset({"SELECT", "INSERT"}),
            frozenset({"voided", "void_reason", "voided_by", "voided_at", "updated_at"}),
        ),
        "apex_worker": (frozenset(), frozenset()),
    },
    "plans.plans": {
        "apex_api": (frozenset({"SELECT", "INSERT"}), frozenset({TODAS})),
        "apex_worker": (frozenset({"SELECT"}), frozenset()),
    },
    "public.alembic_version": {
        "apex_api": (frozenset({"SELECT"}), frozenset()),
        "apex_worker": (frozenset(), frozenset()),
    },
    "settings.settings_sections": {
        "apex_api": (frozenset({"SELECT", "INSERT"}), frozenset({TODAS})),
        "apex_worker": (frozenset({"SELECT"}), frozenset()),
    },
    "worker.job_runs": {
        "apex_api": (frozenset({"SELECT"}), frozenset()),
        "apex_worker": (frozenset({"SELECT", "INSERT"}), frozenset({TODAS})),
    },
}
VERBOS_DE_TABLA = ("SELECT", "INSERT", "DELETE", "TRUNCATE", "TRIGGER", "REFERENCES")

LIMITE_CONEXIONES = {"apex_api": 20, "apex_worker": 5, "apex_backup": 2}


# Ayudas -----------------------------------------------------------------------------------------


def _correr(dsn: str, trabajo: Callable[[asyncpg.Connection], Any]) -> Any:
    async def corre() -> Any:
        conexion = await asyncpg.connect(dsn)
        try:
            return await trabajo(conexion)
        finally:
            await conexion.close()

    return asyncio.run(corre())


def consultar(dsn: str, sql: str, *args: Any) -> list[asyncpg.Record]:
    async def trabajo(c: asyncpg.Connection) -> list[asyncpg.Record]:
        return list(await c.fetch(sql, *args))

    return list(_correr(dsn, trabajo))


def intentar(dsn: str, *sentencias: str) -> asyncpg.PostgresError | None:
    """Corre las sentencias en una transacción que SIEMPRE se revierte; devuelve el primer
    error de PostgreSQL o `None` si todas funcionaron."""

    async def trabajo(c: asyncpg.Connection) -> asyncpg.PostgresError | None:
        transaccion = c.transaction()
        await transaccion.start()
        try:
            for sentencia in sentencias:
                await c.execute(sentencia)
        except asyncpg.PostgresError as error:
            return error
        finally:
            await transaccion.rollback()
        return None

    resultado: asyncpg.PostgresError | None = _correr(dsn, trabajo)
    return resultado


def como(apex: RolesDb, rol: str) -> str:
    return apex.dsn(rol)


def propietario(apex: RolesDb, *sentencias: str) -> None:
    async def trabajo(c: asyncpg.Connection) -> None:
        for sentencia in sentencias:
            await c.execute(sentencia)

    _correr(apex.dsn(), trabajo)


@pytest.fixture(scope="module")
def filas_base(apex_roles: RolesDb) -> dict[str, str]:
    """Un socio y un plan reales (como propietario) para ejercitar `INSERT` en membresías."""
    socio, plan = str(uuid4()), str(uuid4())
    propietario(
        apex_roles,
        "INSERT INTO members.members (id, created_by, first_name, last_name, document, "  # noqa: S608
        f"document_idx) VALUES ('{socio}', '{SYSTEM}', 'Ana', 'Prueba', 'apx1.x', "
        f"'idx-{socio}')",
        "INSERT INTO plans.plans (id, created_by, name, price_cop, kind, duration_days) "  # noqa: S608
        f"VALUES ('{plan}', '{SYSTEM}', 'Plan {plan}', 100000, 'days', 30)",
    )
    return {"socio": socio, "plan": plan}


def _audit_log_insert() -> str:
    return (
        "INSERT INTO audit.audit_log (id, seq, at, user_id, action, table_name, prev_hash, hash, "  # noqa: S608
        f"created_at, updated_at, created_by) VALUES ('{uuid4()}', "
        "(SELECT coalesce(max(seq), 0) + 1 FROM audit.audit_log), now(), "
        f"'{SYSTEM}', 'login', 'auth.users', '{'ab' * 32}', '{'ab' * 32}', now(), now(), "
        f"'{SYSTEM}')"
    )


def _crypto_op_insert() -> str:
    return (
        "INSERT INTO crypto.crypto_ops (id, created_by, user_id, verb, result) "  # noqa: S608
        f"VALUES ('{uuid4()}', '{SYSTEM}', '{SYSTEM}', 'encrypt', 'ok')"
    )


def _job_run_insert() -> str:
    return (
        "INSERT INTO worker.job_runs (id, created_by, job_name, run_date, started_at, result) "  # noqa: S608
        f"VALUES ('{uuid4()}', '{SYSTEM}', 'prueba_roles', current_date, now(), 'running')"
    )


def _membership_insert(filas: dict[str, str]) -> str:
    return (
        "INSERT INTO memberships.memberships (id, created_by, member_id, plan_id, "  # noqa: S608
        "agreed_price_cop, start_date, end_date, status) "
        f"VALUES ('{uuid4()}', '{SYSTEM}', '{filas['socio']}', '{filas['plan']}', 100000, "
        "current_date, current_date + 30, 'active')"
    )


def _crypto_key_insert() -> str:
    return (
        "INSERT INTO crypto.crypto_keys (id, created_by, purpose, data_class, algorithm, "  # noqa: S608
        f"provider, version, state, wrapped_material) VALUES ('{uuid4()}', '{SYSTEM}', "
        "'encrypt', 'prueba.cero_cat', 'A256GCM', 'local', 1, 'decrypt_only', '\\x00')"
    )


# Roles ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ROLES)
def test_los_roles_no_tienen_atributos_peligrosos(apex_roles: RolesDb, rol: str) -> None:
    fila = consultar(
        apex_roles.dsn(),
        "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication, rolinherit, "
        "rolcanlogin, rolconnlimit FROM pg_roles WHERE rolname = $1",
        rol,
    )
    assert len(fila) == 1, f"el rol {rol} no existe"
    r = fila[0]
    assert (r["rolsuper"], r["rolcreaterole"], r["rolcreatedb"]) == (False, False, False)
    assert (r["rolbypassrls"], r["rolreplication"], r["rolinherit"]) == (False, False, False)
    assert r["rolcanlogin"] is True
    assert r["rolconnlimit"] == LIMITE_CONEXIONES[rol]


@pytest.mark.parametrize("rol", ROLES)
def test_los_roles_no_son_dueños_de_nada(apex_roles: RolesDb, rol: str) -> None:
    dueño = consultar(
        apex_roles.dsn(),
        "SELECT count(*) AS n FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner "
        "WHERE r.rolname = $1",
        rol,
    )
    assert dueño[0]["n"] == 0
    esquemas = consultar(
        apex_roles.dsn(),
        "SELECT count(*) AS n FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner "
        "WHERE r.rolname = $1",
        rol,
    )
    assert esquemas[0]["n"] == 0


def test_apex_backup_es_miembro_de_pg_read_all_data_y_de_nada_mas(apex_roles: RolesDb) -> None:
    miembros = consultar(
        apex_roles.dsn(),
        "SELECT m.rolname AS miembro, g.rolname AS grupo, a.inherit_option AS hereda "
        "FROM pg_auth_members a "
        "JOIN pg_roles m ON m.oid = a.member JOIN pg_roles g ON g.oid = a.roleid "
        "WHERE m.rolname = ANY($1::text[])",
        list(ROLES),
    )
    assert {(f["miembro"], f["grupo"]) for f in miembros} == {("apex_backup", "pg_read_all_data")}
    # PG16: con NOINHERIT en el rol, la membresía solo sirve con WITH INHERIT TRUE.
    assert all(f["hereda"] for f in miembros)


@pytest.mark.parametrize(
    ("rol", "valor"),
    [
        (rol, ajuste)
        for rol in ROLES
        for ajuste in (
            ("statement_timeout", Settings.model_fields["DB_STATEMENT_TIMEOUT_MS"].default),
            (
                "idle_in_transaction_session_timeout",
                Settings.model_fields["DB_IDLE_IN_TX_TIMEOUT_MS"].default,
            ),
        )
    ],
)
def test_los_tiempos_de_espera_por_rol_igualan_los_de_settings(
    apex_roles: RolesDb, rol: str, valor: tuple[str, int]
) -> None:
    nombre, milisegundos = valor
    fila = consultar(apex_roles.dsn(rol), "SELECT setting FROM pg_settings WHERE name = $1", nombre)
    assert fila[0]["setting"] == str(milisegundos)


# Privilegios por tabla y columna (la matriz del inventario) ------------------------------------


def _casos_de_privilegios() -> Iterator[Any]:
    for tabla, por_rol in PRIVILEGIOS.items():
        for rol, esperado in por_rol.items():
            yield pytest.param(tabla, rol, esperado, id=f"{rol}-{tabla}")


@pytest.mark.parametrize(("tabla", "rol", "esperado"), list(_casos_de_privilegios()))
def test_privilegios_de_tabla_y_columna_exactos(
    apex_roles: RolesDb,
    tabla: str,
    rol: str,
    esperado: tuple[frozenset[str], frozenset[str]],
) -> None:
    verbos, columnas_update = esperado
    reales = {
        verbo
        for verbo in VERBOS_DE_TABLA
        if consultar(
            apex_roles.dsn(), "SELECT has_table_privilege($1, $2, $3) AS v", rol, tabla, verbo
        )[0]["v"]
    }
    assert reales == set(verbos), f"{rol} sobre {tabla}: {sorted(reales)} != {sorted(verbos)}"
    todas = [
        f["column_name"]
        for f in consultar(
            apex_roles.dsn(),
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema || '.' || table_name = $1",
            tabla,
        )
    ]
    con_update = {
        c
        for c in todas
        if consultar(
            apex_roles.dsn(),
            "SELECT has_column_privilege($1, $2, $3, 'UPDATE') AS v",
            rol,
            tabla,
            c,
        )[0]["v"]
    }
    esperadas = set(todas) if TODAS in columnas_update else set(columnas_update)
    assert con_update == esperadas, f"{rol} UPDATE en {tabla}: {sorted(con_update)}"


@pytest.mark.parametrize("tabla", sorted(PRIVILEGIOS))
def test_apex_backup_lee_todo_y_no_escribe_nada(apex_roles: RolesDb, tabla: str) -> None:
    dsn = apex_roles.dsn()
    assert consultar(dsn, "SELECT has_table_privilege('apex_backup', $1, 'SELECT') AS v", tabla)[0][
        "v"
    ]
    for verbo in ("INSERT", "DELETE", "TRUNCATE", "TRIGGER", "REFERENCES", "UPDATE"):
        assert not consultar(
            dsn, "SELECT has_table_privilege('apex_backup', $1, $2) AS v", tabla, verbo
        )[0]["v"], f"apex_backup no debe tener {verbo} en {tabla}"


def test_delete_solo_existe_para_apex_api_en_refresh_tokens(apex_roles: RolesDb) -> None:
    con_delete = [
        (rol, tabla)
        for tabla in PRIVILEGIOS
        for rol in ROLES
        if consultar(
            apex_roles.dsn(), "SELECT has_table_privilege($1, $2, 'DELETE') AS v", rol, tabla
        )[0]["v"]
    ]
    assert con_delete == [("apex_api", "auth.refresh_tokens")]


def test_ningun_rol_tiene_ddl_ni_create_en_los_esquemas(apex_roles: RolesDb) -> None:
    for rol in ROLES:
        for esquema in ESQUEMAS:
            tiene = consultar(
                apex_roles.dsn(),
                "SELECT has_schema_privilege($1, $2, 'CREATE') AS v",
                rol,
                esquema,
            )[0]["v"]
            assert not tiene, f"{rol} puede crear en {esquema}"
        assert not consultar(
            apex_roles.dsn(),
            "SELECT has_database_privilege($1, $2, 'CREATE') AS v",
            rol,
            "apex_roles",
        )[0]["v"]


def test_public_no_conserva_privilegios_de_tablas_ni_del_esquema_public(
    apex_roles: RolesDb,
) -> None:
    """REVOKE ... FROM PUBLIC antes de conceder (M-3.7): PUBLIC no lee ni escribe tablas."""
    fugas = consultar(
        apex_roles.dsn(),
        "SELECT n.nspname || '.' || c.relname AS t FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace, "
        "LATERAL aclexplode(c.relacl) a WHERE a.grantee = 0 AND n.nspname = ANY($1::text[]) "
        "AND c.relkind = 'r'",
        list(ESQUEMAS),
    )
    assert fugas == []
    assert not consultar(
        apex_roles.dsn(), "SELECT has_schema_privilege('public', 'public', 'CREATE') AS v"
    )[0]["v"]
    otorgados = consultar(
        apex_roles.dsn(),
        "SELECT has_database_privilege($1, 'apex_roles', 'CONNECT') AS v",
        "apex_api",
    )
    assert otorgados[0]["v"], "apex_api debe poder conectarse a su base"


# Lo permitido funciona, lo prohibido falla con 42501 -------------------------------------------


def test_apex_api_hace_lo_que_necesita(apex_roles: RolesDb, filas_base: dict[str, str]) -> None:
    dsn = como(apex_roles, "apex_api")
    permitidas = [
        "SELECT count(*) FROM members.members",
        _audit_log_insert(),
        _crypto_op_insert(),
        _membership_insert(filas_base),  # ejercita el índice gist de exclusión (btree_gist)
        "SELECT version_num FROM public.alembic_version",
        "SELECT count(*) FROM worker.job_runs",
        "SELECT id FROM plans.plans FOR SHARE",
        "SELECT id FROM plans.plans FOR UPDATE",
        "UPDATE auth.users SET failed_login_count = 1 WHERE false",
        "DELETE FROM auth.refresh_tokens WHERE false",
        "UPDATE payments.payments SET voided = true, void_reason = 'x', voided_by = NULL, "
        "voided_at = NULL, updated_at = now() WHERE false",
        "UPDATE crypto.crypto_keys SET updated_at = now() WHERE false",
    ]
    for sentencia in permitidas:
        assert intentar(dsn, sentencia) is None, sentencia


def test_for_share_sobre_crypto_keys_funciona_con_apex_api(apex_roles: RolesDb) -> None:
    """El listener de cifrado (`core/crypto/types.py`) hace `SELECT ... FOR SHARE`; exige
    `UPDATE` sobre al menos una columna (aquí `updated_at`). Si PostgreSQL no lo exigiera, el
    `GRANT UPDATE (updated_at)` sobraría y se quitaría en el Verde con esta prueba."""
    dsn = como(apex_roles, "apex_api")
    assert (
        intentar(dsn, "SELECT id FROM crypto.crypto_keys WHERE state = 'active' FOR SHARE") is None
    )


def test_for_update_de_memberships_funciona_con_apex_worker_y_el_de_members_no(
    apex_roles: RolesDb,
) -> None:
    """Ningún código del worker escribe en `members.members` (`lock_member` es un candado asesor):
    el worker no tiene `UPDATE` allí y por eso tampoco `FOR UPDATE` (DB-3 de la revisión)."""
    dsn = como(apex_roles, "apex_worker")
    assert intentar(dsn, "SELECT id FROM memberships.memberships FOR UPDATE") is None
    error = intentar(dsn, "SELECT id FROM members.members FOR UPDATE")
    assert error is not None and error.sqlstate == PRIVACION


def test_apex_worker_hace_lo_que_necesita(apex_roles: RolesDb) -> None:
    dsn = como(apex_roles, "apex_worker")
    permitidas = [
        "UPDATE memberships.memberships SET status = status WHERE false",
        _audit_log_insert(),
        _crypto_op_insert(),
        _job_run_insert(),
        "SELECT count(*) FROM settings.settings_sections",
        "SELECT count(*) FROM auth.users",
        "SELECT count(*) FROM plans.plans",
        "SELECT count(*) FROM memberships.membership_freezes",
    ]
    for sentencia in permitidas:
        assert intentar(dsn, sentencia) is None, sentencia


def test_apex_backup_lee_y_no_escribe(apex_roles: RolesDb) -> None:
    dsn = como(apex_roles, "apex_backup")
    for tabla in PRIVILEGIOS:
        assert intentar(dsn, f"SELECT count(*) FROM {tabla}") is None, tabla  # noqa: S608
    for sentencia in (
        _audit_log_insert(),
        _crypto_op_insert(),
        _job_run_insert(),
        "UPDATE members.members SET updated_at = now() WHERE false",
        "DELETE FROM auth.refresh_tokens WHERE false",
        "CREATE TABLE public.x_backup()",
    ):
        error = intentar(dsn, sentencia)
        assert error is not None and error.sqlstate == PRIVACION, sentencia


PROHIBIDAS_API = [
    "ALTER TABLE audit.audit_log DISABLE TRIGGER ALL",
    "ALTER TABLE payments.payments DISABLE TRIGGER payments_forbid_mutation",
    "SET session_replication_role = replica",
    "TRUNCATE audit.audit_log",
    "TRUNCATE crypto.crypto_ops",
    "DELETE FROM payments.payments",
    "DELETE FROM audit.audit_log",
    "DELETE FROM members.members",
    "DELETE FROM memberships.memberships",
    "DELETE FROM crypto.crypto_keys",
    "UPDATE audit.audit_log SET action = 'x'",
    "UPDATE audit.verifications SET ok = false",
    "UPDATE crypto.crypto_keys SET state = 'retired'",
    "UPDATE crypto.crypto_ops SET result = 'error'",
    "UPDATE payments.payments SET amount_cop = 1",
    "UPDATE payments.payments SET registered_by = created_by",
    "UPDATE memberships.memberships SET agreed_price_cop = 1",
    "UPDATE memberships.memberships SET member_id = member_id",
    "UPDATE public.alembic_version SET version_num = 'x'",
    "INSERT INTO public.alembic_version (version_num) VALUES ('x')",
    "INSERT INTO worker.job_runs (id) VALUES (gen_random_uuid())",
    "UPDATE worker.job_runs SET result = 'ok'",
    "CREATE TABLE public.x()",
    "CREATE TABLE members.x()",
    "CREATE SCHEMA ataque",
    "CREATE ROLE intruso",
    "ALTER TABLE members.members ADD COLUMN x int",
    "DROP TABLE members.members",
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
]


@pytest.mark.parametrize("sentencia", PROHIBIDAS_API)
def test_apex_api_no_puede(apex_roles: RolesDb, sentencia: str) -> None:
    error = intentar(como(apex_roles, "apex_api"), sentencia)
    assert error is not None, f"debía fallar: {sentencia}"
    assert error.sqlstate == PRIVACION, f"{sentencia}: {error.sqlstate} {error}"


PROHIBIDAS_WORKER = [
    "UPDATE members.members SET updated_at = now()",
    "UPDATE members.members SET first_name = 'x'",
    "UPDATE members.members SET deleted_at = now()",
    "UPDATE memberships.memberships SET end_date = end_date",
    "UPDATE memberships.memberships SET classes_remaining = 0",
    "SELECT count(*) FROM payments.payments",
    "SELECT count(*) FROM crypto.crypto_keys",
    "SELECT count(*) FROM auth.refresh_tokens",
    "INSERT INTO members.members (id) VALUES (gen_random_uuid())",
    "DELETE FROM worker.job_runs",
    "TRUNCATE worker.job_runs",
    "ALTER TABLE audit.audit_log DISABLE TRIGGER ALL",
    "SET session_replication_role = replica",
    "UPDATE audit.audit_log SET action = 'x'",
    "CREATE TABLE public.x()",
]


@pytest.mark.parametrize("sentencia", PROHIBIDAS_WORKER)
def test_apex_worker_no_puede(apex_roles: RolesDb, sentencia: str) -> None:
    error = intentar(como(apex_roles, "apex_worker"), sentencia)
    assert error is not None, f"debía fallar: {sentencia}"
    assert error.sqlstate == PRIVACION, f"{sentencia}: {error.sqlstate} {error}"


def test_residual_d61_apex_api_puede_insertar_una_llave_decrypt_only_pero_no_cambiar_state(
    apex_roles: RolesDb,
) -> None:
    """Residual aceptado y documentado (S4B-D61 punto 4): `ensure_keys` exige `INSERT` en
    `crypto_keys`, así que se puede insertar una fila `decrypt_only` de una clase inexistente.
    Lo que no se puede es `UPDATE (state)`."""
    dsn = como(apex_roles, "apex_api")
    assert intentar(dsn, _crypto_key_insert()) is None
    error = intentar(dsn, _crypto_key_insert(), "UPDATE crypto.crypto_keys SET state = 'retired'")
    assert error is not None and error.sqlstate == PRIVACION


def test_apex_api_no_inserta_en_job_runs(apex_roles: RolesDb) -> None:
    """S4B-D71 (L-3), parte del rol: el api solo lee `worker.job_runs`."""
    error = intentar(como(apex_roles, "apex_api"), _job_run_insert())
    assert error is not None and error.sqlstate == PRIVACION


# Clasificación y fallo cerrado ------------------------------------------------------------------


def _clasificadas_en_el_encabezado() -> set[str]:
    texto = (INFRA_DB / "grants.sql").read_text(encoding="utf-8")
    return set(re.findall(r"^--\s*clasificada:\s*([a-z_]+\.[a-z_0-9]+)\s*$", texto, re.MULTILINE))


def test_toda_tabla_de_la_base_esta_clasificada(apex_roles: RolesDb) -> None:
    filas = consultar(
        apex_roles.dsn(),
        "SELECT table_schema || '.' || table_name AS t FROM information_schema.tables "
        "WHERE table_type = 'BASE TABLE' AND table_schema = ANY($1::text[])",
        list(ESQUEMAS),
    )
    tablas = {f["t"] for f in filas}
    assert tablas == set(PRIVILEGIOS), (
        f"tablas sin fila en la matriz o sobrantes: {sorted(tablas ^ set(PRIVILEGIOS))}"
    )
    assert _clasificadas_en_el_encabezado() == tablas, (
        "el encabezado de grants.sql debe listar `-- clasificada: esquema.tabla` de cada tabla"
    )


@pytest.fixture
def tabla_sin_clasificar(apex_roles: RolesDb) -> Iterator[None]:
    propietario(apex_roles, "CREATE TABLE members.sin_permiso()")
    try:
        yield
    finally:
        propietario(apex_roles, "DROP TABLE IF EXISTS members.sin_permiso")
        reaplicado = aplicar_archivo("apex_roles", "grants.sql")
        assert reaplicado.returncode == 0, reaplicado.stderr


def test_grants_falla_cerrado_con_una_tabla_sin_clasificar(
    apex_roles: RolesDb, tabla_sin_clasificar: None
) -> None:
    resultado = aplicar_archivo("apex_roles", "grants.sql")
    assert resultado.returncode != 0
    assert "tabla sin clasificar" in resultado.stderr
    assert "members.sin_permiso" in resultado.stderr


@pytest.mark.parametrize(
    ("nombre", "ddl"),
    [
        (
            "tabla en un esquema nuevo",
            ["CREATE SCHEMA esquema_nuevo", "CREATE TABLE esquema_nuevo.t()"],
        ),
        (
            "vista de un esquema de la aplicacion",
            ["CREATE VIEW members.vista_nueva AS SELECT 1 AS x"],
        ),
        ("secuencia en public", ["CREATE SEQUENCE public.secuencia_nueva"]),
    ],
)
def test_grants_falla_cerrado_con_objetos_fuera_de_la_lista_aunque_no_sean_tablas_conocidas(
    apex_roles: RolesDb, nombre: str, ddl: list[str]
) -> None:
    """DB-1 de la revisión: el recorrido cubre todo esquema que no sea del sistema y las vistas,
    vistas materializadas, secuencias y tablas foráneas, no solo `relkind` r/p en diez esquemas."""
    propietario(apex_roles, *ddl)
    try:
        resultado = aplicar_archivo("apex_roles", "grants.sql")
        assert resultado.returncode != 0, nombre
        assert "tabla sin clasificar" in resultado.stderr, nombre
    finally:
        propietario(
            apex_roles,
            "DROP SCHEMA IF EXISTS esquema_nuevo CASCADE",
            "DROP VIEW IF EXISTS members.vista_nueva",
            "DROP SEQUENCE IF EXISTS public.secuencia_nueva",
        )
        reaplicado = aplicar_archivo("apex_roles", "grants.sql")
        assert reaplicado.returncode == 0, reaplicado.stderr


def test_grants_no_se_queja_de_los_objetos_de_una_extension(apex_roles: RolesDb) -> None:
    """Los objetos de `btree_gist` viven en `public` y dependen de la extensión (deptype e)."""
    resultado = aplicar_archivo("apex_roles", "grants.sql")
    assert resultado.returncode == 0, resultado.stderr


def test_grants_es_idempotente(apex_roles: RolesDb) -> None:
    for _ in range(2):
        resultado = aplicar_archivo("apex_roles", "grants.sql")
        assert resultado.returncode == 0, resultado.stderr


def test_roles_es_idempotente_y_las_conexiones_siguen_funcionando(apex_roles: RolesDb) -> None:
    for _ in range(2):
        resultado = aplicar_archivo("apex_roles", "roles.sql")
        assert resultado.returncode == 0, resultado.stderr
    for rol in ROLES:
        assert intentar(como(apex_roles, rol), "SELECT 1") is None


def test_roles_sql_vuelve_a_fijar_la_contraseña_y_no_la_imprime(apex_roles: RolesDb) -> None:
    nuevas = {rol: f"{clave}-rotada" for rol, clave in CLAVES.items()}
    resultado = psql_en_db_test(
        "apex_roles",
        (INFRA_DB / "roles.sql").read_text(encoding="utf-8"),
        entorno=entorno_de_claves(nuevas),
    )
    try:
        assert resultado.returncode == 0, resultado.stderr
        salida = resultado.stdout + resultado.stderr
        assert all(clave not in salida for clave in (*CLAVES.values(), *nuevas.values()))

        async def viejo() -> None:
            await asyncpg.connect(apex_roles.dsn("apex_api"))

        with pytest.raises(asyncpg.InvalidPasswordError):
            asyncio.run(viejo())
    finally:
        restaurado = aplicar_archivo("apex_roles", "roles.sql")
        assert restaurado.returncode == 0, restaurado.stderr


def test_revoke_deja_el_cluster_sin_roles_es_idempotente_y_se_puede_reaplicar(
    apex_roles: RolesDb,
) -> None:
    try:
        for _ in range(2):  # apply -> revoke -> revoke
            resultado = aplicar_archivo("apex_roles", "revoke.sql")
            assert resultado.returncode == 0, resultado.stderr
        restantes = consultar(
            apex_roles.dsn(),
            "SELECT rolname FROM pg_roles WHERE rolname = ANY($1::text[])",
            list(ROLES),
        )
        assert restantes == []
        with pytest.raises(asyncpg.PostgresError):
            asyncio.run(asyncpg.connect(apex_roles.dsn("apex_api")))
    finally:
        for archivo in ("roles.sql", "grants.sql"):  # ... -> apply
            reaplicado = aplicar_archivo("apex_roles", archivo)
            assert reaplicado.returncode == 0, reaplicado.stderr
    for rol in ROLES:
        assert intentar(como(apex_roles, rol), "SELECT 1") is None


# Archivos de infra/db (estáticos) --------------------------------------------------------------


def _leer(nombre: str) -> str:
    ruta = INFRA_DB / nombre
    assert ruta.is_file(), f"no existe infra/db/{nombre}"
    return ruta.read_text(encoding="utf-8")


def test_roles_sql_usa_getenv_gexec_y_no_registra_contraseñas() -> None:
    texto = _leer("roles.sql")
    for ancla in ("\\getenv", "\\gexec", "%L"):
        assert ancla in texto, ancla
    for variable in ("APEX_API_DB_PASSWORD", "APEX_WORKER_DB_PASSWORD", "APEX_BACKUP_DB_PASSWORD"):
        assert variable in texto
    inicio = texto.split("CREATE ROLE", 1)[0].split("ALTER ROLE", 1)[0]
    assert "log_min_error_statement = panic" in inicio
    assert "log_statement = 'none'" in inicio
    for atributo in (
        "NOSUPERUSER",
        "NOCREATEDB",
        "NOCREATEROLE",
        "NOINHERIT",
        "NOBYPASSRLS",
        "LOGIN",
    ):
        assert atributo in texto, atributo
    assert "CONNECTION LIMIT" in texto and "statement_timeout" in texto
    assert not re.search(r"PASSWORD\s+'[^']", texto), "ninguna contraseña literal"


def test_grants_sql_es_sql_puro_con_fallo_cerrado_y_sin_default_privileges() -> None:
    texto = _leer("grants.sql")
    assert "ALTER DEFAULT PRIVILEGES" not in texto
    assert "RAISE EXCEPTION" in texto and "tabla sin clasificar" in texto
    assert re.search(r"REVOKE\s+ALL\s+ON\s+DATABASE\s+.*FROM\s+PUBLIC", texto, re.IGNORECASE)
    assert re.search(
        r"REVOKE\s+CREATE\s+ON\s+SCHEMA\s+public\s+FROM\s+PUBLIC", texto, re.IGNORECASE
    )
    assert "pg_read_all_data" in texto
    assert not re.search(r"GRANT\s+[^;]*\bTO\s+PUBLIC\b", texto, re.IGNORECASE)
    assert not re.search(
        r"GRANT\s+[^;]*\b(TRUNCATE|TRIGGER|REFERENCES|ALL)\b[^;]*\bTO\s+apex_", texto, re.IGNORECASE
    )
    assert "\\getenv" not in texto, "las contraseñas son de roles.sql"


def _tablas_del_array_final() -> set[str]:
    texto = _leer("grants.sql")
    patron = r"clasificadas\s+constant\s+text\[\]\s*:=\s*ARRAY\[(.*?)\];"
    bloque = re.search(patron, texto, re.DOTALL)
    assert bloque is not None, "grants.sql debe declarar el ARRAY `clasificadas` del bloque final"
    return set(re.findall(r"'([a-z_]+\.[a-z_0-9]+)'", bloque.group(1)))


def _tablas_con_grant() -> set[str]:
    texto = _leer("grants.sql")
    esquemas = "|".join(ESQUEMAS)
    tablas: set[str] = set()
    for grant in re.findall(r"^GRANT\s+(?!USAGE|CONNECT|pg_read_all_data)[^;]*?;", texto, re.M):
        destino = re.split(r"\bON\b", grant, maxsplit=1)[1].split(" TO ")[0]
        tablas |= set(re.findall(rf"\b((?:{esquemas})\.[a-z_0-9]+)\b", destino))
    return tablas


def test_las_tres_listas_de_tablas_de_grants_sql_coinciden() -> None:
    """S4B-D201: matriz (`-- clasificada:`), ARRAY del DO final y GRANTs son el mismo conjunto."""
    array = _tablas_del_array_final()
    assert len(array) == len(PRIVILEGIOS)
    assert array == _clasificadas_en_el_encabezado(), "ARRAY != líneas `-- clasificada:`"
    assert array == _tablas_con_grant(), "ARRAY != tablas con GRANT"
    assert array == set(PRIVILEGIOS), "grants.sql != la matriz ejecutable de esta prueba"


def test_apply_sh_cuenta_las_tablas_del_array_que_valida_no_los_comentarios() -> None:
    texto = _leer("apply.sh")
    assert "-- clasificada" not in texto, "el conteo no puede salir de los comentarios"
    assert "clasificadas constant" in texto, "el conteo debe leerse del ARRAY del DO final"


def test_revoke_sql_es_idempotente_por_construccion() -> None:
    texto = _leer("revoke.sql")
    assert "DROP OWNED BY" in texto
    assert re.search(r"DROP\s+ROLE\s+IF\s+EXISTS", texto, re.IGNORECASE)
    assert "IF EXISTS" in texto
    for rol in ROLES:
        assert rol in texto
