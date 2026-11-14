"""`0024_crypto_rotation_from_api` (S6-R1, US-145; S6-D43, S6-D61, H-2, E2, E6). Rojo R1.

Padre `0023_attachments`; identificador de 31 caracteres o menos (S6-D103). Guardas por rol:
- `crypto.guard_keys_update()` (reemplazo, como `0015`): con `current_user = 'apex_api'` solo pasa
  `active -> decrypt_only` de una llave `encrypt`, con otra fila `active` de `version` mayor en la
  misma clase, un `crypto_jobs` `running` de esa clase y `rotated_by` un usuario real de
  `auth.users` distinto de `SYSTEM_USER_ID`. Nada cambia para el propietario ni para filas `sign`
  (E2);
- `crypto.guard_jobs_insert()` (E6): el api solo inserta `kind = rotate`, `status = running`,
  `data_class` no nula, `total > 0`, `done = 0`, `error` nulo y `created_by` real;
- `crypto.guard_jobs_update()`: `done` no decrece, `total` no cambia, `status = done` exige
  `done = total`; el api solo toca `done`, `status`, `error`, `started_at`, `finished_at`,
  `updated_at` (grants por columna, archivo `grants` de infra/db).
Las tres funciones son `SECURITY INVOKER`; las dos nuevas con `SET search_path = pg_catalog`; los
tres triggers `ENABLE ALWAYS` (`tgenabled = 'A'`).

Hallazgo del Rojo (cuaderno, R1): el índice único parcial `uq_crypto_keys_active` obliga a pasar la
anterior a `decrypt_only` ANTES de insertar la nueva, así que la condición «existe otra fila
`active` de versión mayor» no se puede comprobar en un trigger de fila inmediato al `UPDATE`: debe
comprobarse diferida (por ejemplo `CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED`). Estas
pruebas ejecutan la secuencia real (job, `UPDATE` de la anterior, `INSERT` de la nueva) y cierran
con `SET CONSTRAINTS ALL IMMEDIATE`, que dispara los controles diferidos sin hacer commit; todo
corre en una transacción que se revierte (`intentar`).

Sobre `apex_roles` (roles reales; modelo `test_0023_attachments.py`). Los casos de bloqueo por
privilegio esperan `42501`; los de la guarda, `23514` (`check_violation`, como `0003` y `0015`).
"""

# ruff: noqa: S608
from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.migrations._apoyo_notificaciones import consultar, existe
from tests.migrations.conftest import RolesDb
from tests.migrations.test_db_grants import como, intentar, propietario

REVISION = "0024_crypto_rotation_from_api"
PADRE = "0023_attachments"
SYSTEM = "00000000-0000-0000-0000-000000000001"
CLASE = "prueba.rotacion"
GUARDA = "23514"  # check_violation
PRIVACION = "42501"
DUPLICADO = "23505"
FUNCIONES = ("guard_keys_update", "guard_jobs_update", "guard_jobs_insert")
NUEVAS = ("guard_jobs_update", "guard_jobs_insert")
MIGRACION_0015 = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "0015_crypto_provider_migration.py"
)

# Revisión ---


def _revision_existe(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")


def test_la_revision_cuelga_de_0023_y_esta_en_la_cadena_de_head(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 31  # S6-D103: `alembic_version.version_num` es varchar(32)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (cabeza,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(cabeza, "base")}


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> Iterator[str]:
    _revision_existe(alembic_config)
    yield migrated_database


@pytest.fixture(scope="module")
def usuario(apex_roles: RolesDb) -> str:
    """Un usuario real de `auth.users` (distinto del técnico) para `rotated_by` y `created_by`."""
    nuevo = str(uuid4())
    propietario(
        apex_roles,
        "INSERT INTO auth.users (id, created_by, email, role) "
        f"VALUES ('{nuevo}', '{SYSTEM}', 'rotador-{nuevo}@test.apex', 'admin')",
    )
    return nuevo


# SQL de apoyo -----------------------------------------------------------------------------------


def _llave(
    version: int,
    estado: str,
    *,
    clase: str = CLASE,
    purpose: str = "encrypt",
    por: str = SYSTEM,
    material: str = "\\x01",
    proveedor: str = "local",
) -> str:
    algoritmo = {"encrypt": "A256GCM", "index": "HMAC-SHA256", "sign": "Ed25519"}[purpose]
    clave_publica = "'x'" if purpose == "sign" else "NULL"
    return (
        "INSERT INTO crypto.crypto_keys (id, created_by, purpose, data_class, algorithm, "
        "provider, version, state, wrapped_material, public_key) VALUES "
        f"('{uuid4()}', '{por}', '{purpose}', '{clase}', '{algoritmo}', '{proveedor}', "
        f"{version}, '{estado}', '{material}', {clave_publica})"
    )


def _trabajo(
    por: str,
    *,
    clase: str | None = CLASE,
    kind: str = "rotate",
    estado: str = "running",
    total: int = 5,
    hecho: int = 0,
    error: str | None = None,
) -> str:
    clase_sql = "NULL" if clase is None else f"'{clase}'"
    error_sql = "NULL" if error is None else f"'{error}'"
    return (
        "INSERT INTO crypto.crypto_jobs (id, created_by, kind, data_class, status, total, done, "
        f"error, started_at) VALUES ('{uuid4()}', '{por}', '{kind}', {clase_sql}, '{estado}', "
        f"{total}, {hecho}, {error_sql}, now())"
    )


def _pasar_a(estado: str, rotado_por: str | None, clase: str = CLASE, version: int = 1) -> str:
    por = "NULL" if rotado_por is None else f"'{rotado_por}'"
    return (
        f"UPDATE crypto.crypto_keys SET state = '{estado}', rotated_at = now(), "
        f"rotated_by = {por}, updated_at = now() "
        f"WHERE data_class = '{clase}' AND version = {version}"
    )


CIERRE = "SET CONSTRAINTS ALL IMMEDIATE"


def _rotacion(
    por: str,
    *,
    purpose: str = "encrypt",
    destino: str = "decrypt_only",
    con_trabajo: bool = True,
    con_nueva: bool = True,
    rotado_por: str | None = "",
    nueva_version: int = 2,
) -> list[str]:
    """La secuencia que ejecutará `start_from_screen` como `apex_api`: el job `running`, la
    anterior a `destino` y la nueva `active`. `rotado_por=""` significa «el usuario real»."""
    quien = por if rotado_por == "" else rotado_por
    pasos = [_llave(1, "active", purpose=purpose, por=por)]
    if con_trabajo:
        pasos.append(_trabajo(por))
    pasos.append(_pasar_a(destino, quien))
    if con_nueva:
        pasos.append(_llave(nueva_version, "active", purpose=purpose, por=por))
    pasos.append(CIERRE)
    return pasos


def _como_api(apex: RolesDb, *pasos: str) -> object:
    return intentar(como(apex, "apex_api"), *pasos)


def _sqlstate(error: object) -> str | None:
    return None if error is None else str(getattr(error, "sqlstate", None))


# H-2: guarda de crypto_keys para apex_api ---


def test_apex_api_pasa_active_a_decrypt_only_con_nueva_activa_job_running_y_usuario_real(
    apex_roles: RolesDb, usuario: str
) -> None:
    error = _como_api(apex_roles, *_rotacion(usuario))
    assert error is None, error


def test_sin_la_fila_nueva_active_de_version_mayor_falla(apex_roles: RolesDb, usuario: str) -> None:
    error = _como_api(apex_roles, *_rotacion(usuario, con_nueva=False))
    assert _sqlstate(error) == GUARDA, error


def test_una_nueva_de_version_igual_o_menor_no_cuenta(apex_roles: RolesDb, usuario: str) -> None:
    """«Versión mayor»: una `active` con la misma versión (otra clase) o menor no sirve. El índice
    único `(purpose, data_class, version)` impide repetir versión en la clase, así que se prueba
    con la fila nueva en OTRA clase: tener `active` en otra clase no autoriza esta rotación."""
    pasos = [
        _llave(1, "active", por=usuario),
        _trabajo(usuario),
        _llave(2, "active", clase="prueba.otra", por=usuario),
        _pasar_a("decrypt_only", usuario),
        CIERRE,
    ]
    assert _sqlstate(_como_api(apex_roles, *pasos)) == GUARDA


def test_sin_job_running_de_la_clase_falla(apex_roles: RolesDb, usuario: str) -> None:
    error = _como_api(apex_roles, *_rotacion(usuario, con_trabajo=False))
    assert _sqlstate(error) == GUARDA, error


def test_un_job_running_de_otra_clase_no_autoriza(apex_roles: RolesDb, usuario: str) -> None:
    pasos = _rotacion(usuario, con_trabajo=False)
    pasos.insert(1, _trabajo(usuario, clase="prueba.otra"))
    assert _sqlstate(_como_api(apex_roles, *pasos)) == GUARDA


@pytest.mark.parametrize("purpose", ["index", "sign"])
def test_solo_las_llaves_encrypt_se_rotan_desde_el_api(
    apex_roles: RolesDb, usuario: str, purpose: str
) -> None:
    error = _como_api(apex_roles, *_rotacion(usuario, purpose=purpose))
    assert _sqlstate(error) == GUARDA, (purpose, error)


@pytest.mark.parametrize(
    "rotado_por",
    [SYSTEM, None, "00000000-0000-0000-0000-0000000000aa"],
    ids=["usuario_tecnico", "nulo", "inexistente_en_auth_users"],
)
def test_rotated_by_debe_ser_un_usuario_real_distinto_del_tecnico(
    apex_roles: RolesDb, usuario: str, rotado_por: str | None
) -> None:
    error = _como_api(apex_roles, *_rotacion(usuario, rotado_por=rotado_por))
    assert _sqlstate(error) == GUARDA, (rotado_por, error)


def test_el_api_no_puede_retirar_una_llave_active(apex_roles: RolesDb, usuario: str) -> None:
    error = _como_api(apex_roles, *_rotacion(usuario, destino="retired"))
    assert _sqlstate(error) == GUARDA, error


def test_el_api_no_puede_retirar_una_llave_decrypt_only(apex_roles: RolesDb, usuario: str) -> None:
    pasos = [
        _llave(1, "decrypt_only", por=usuario),
        _trabajo(usuario),
        _pasar_a("retired", usuario),
    ]
    assert _sqlstate(_como_api(apex_roles, *pasos)) == GUARDA


def test_el_api_no_puede_reactivar_una_llave_decrypt_only(
    apex_roles: RolesDb, usuario: str
) -> None:
    pasos = [_llave(1, "decrypt_only", por=usuario), _trabajo(usuario), _pasar_a("active", usuario)]
    assert _sqlstate(_como_api(apex_roles, *pasos)) == GUARDA


@pytest.mark.parametrize(
    "cambio",
    [
        "provider = 'openbao'",
        "wrapped_material = '\\x02'",
        "version = 9",
        "data_class = 'prueba.otra'",
        "public_key = 'x'",
        "algorithm = 'A256GCM'",
        "purpose = 'index'",
    ],
    ids=[
        "provider",
        "wrapped_material",
        "version",
        "data_class",
        "public_key",
        "algorithm",
        "purpose",
    ],
)
def test_el_api_no_cambia_ninguna_otra_columna_de_crypto_keys(
    apex_roles: RolesDb, usuario: str, cambio: str
) -> None:
    pasos = [_llave(1, "active", por=usuario), f"UPDATE crypto.crypto_keys SET {cambio}"]
    assert _sqlstate(_como_api(apex_roles, *pasos)) == PRIVACION, cambio


def test_la_guarda_no_toca_a_las_filas_sign_el_propietario_sigue_migrando_de_proveedor(
    apex_roles: RolesDb,
) -> None:
    """E2: `local -> openbao` con referencia nueva (la rama de `0015`) sigue admitida para el
    propietario aunque la fila sea `sign` y no haya job ni fila nueva."""
    pasos = [
        _llave(1, "active", purpose="sign", material="apex-sign-audit"),
        "UPDATE crypto.crypto_keys SET provider = 'openbao', "
        "wrapped_material = 'apex-sign-audit-2' "
        f"WHERE data_class = '{CLASE}'",
        CIERRE,
    ]
    assert intentar(apex_roles.dsn(), *pasos) is None


def test_el_api_no_toca_una_fila_sign_ni_con_todas_las_condiciones(
    apex_roles: RolesDb, usuario: str
) -> None:
    for destino in ("decrypt_only", "retired"):
        error = _como_api(apex_roles, *_rotacion(usuario, purpose="sign", destino=destino))
        assert _sqlstate(error) == GUARDA, (destino, error)
    cambio = ["UPDATE crypto.crypto_keys SET provider = 'openbao', wrapped_material = '\\x02'"]
    error = _como_api(apex_roles, _llave(1, "active", purpose="sign", por=usuario), *cambio)
    assert _sqlstate(error) == PRIVACION


def test_el_propietario_rota_sin_job_ni_usuario_real_como_hace_el_cli(apex_roles: RolesDb) -> None:
    """El CLI corre como propietario: pasa la anterior a `decrypt_only` ANTES de abrir el job y con
    `rotated_by` el actor de la CLI (aquí el técnico); `retired` también (retire-key)."""
    pasos = [
        _llave(1, "active"),
        _pasar_a("decrypt_only", SYSTEM),
        _llave(2, "active"),
        _trabajo(SYSTEM),
        _pasar_a("retired", SYSTEM),
        CIERRE,
    ]
    assert intentar(apex_roles.dsn(), *pasos) is None


# E6: guard_jobs_insert ---


def test_apex_api_inserta_un_job_rotate_running_valido(apex_roles: RolesDb, usuario: str) -> None:
    assert _como_api(apex_roles, _trabajo(usuario)) is None


@pytest.mark.parametrize(
    "variante",
    [
        {"estado": "pending"},
        {"estado": "done", "hecho": 5},
        {"estado": "failed", "error": "x"},
        {"total": 0},
        {"hecho": 1},
        {"kind": "migrate_provider", "clase": None},
        {"kind": "rewrap", "clase": None},
        {"kind": "reencrypt"},
        {"clase": None},
        {"error": "algo"},
    ],
    ids=[
        "pending",
        "done",
        "failed",
        "total_cero",
        "done_mayor_que_cero",
        "migrate_provider",
        "rewrap",
        "reencrypt",
        "sin_clase",
        "con_error",
    ],
)
def test_apex_api_no_inserta_un_job_fuera_del_molde(
    apex_roles: RolesDb, usuario: str, variante: dict[str, object]
) -> None:
    error = _como_api(apex_roles, _trabajo(usuario, **variante))  # type: ignore[arg-type]
    assert _sqlstate(error) == GUARDA, (variante, error)


def test_apex_api_no_inserta_un_job_a_nombre_del_usuario_tecnico(apex_roles: RolesDb) -> None:
    assert _sqlstate(_como_api(apex_roles, _trabajo(SYSTEM))) == GUARDA


def test_apex_api_no_inserta_un_job_a_nombre_de_un_usuario_inexistente(apex_roles: RolesDb) -> None:
    fantasma = "00000000-0000-0000-0000-0000000000bb"
    assert _sqlstate(_como_api(apex_roles, _trabajo(fantasma))) == GUARDA


def test_un_segundo_job_running_de_la_misma_clase_viola_el_indice_de_jobs_en_curso(
    apex_roles: RolesDb, usuario: str
) -> None:
    error = _como_api(apex_roles, _trabajo(usuario), _trabajo(usuario))
    assert _sqlstate(error) == DUPLICADO, error


def test_un_job_de_otra_clase_convive(apex_roles: RolesDb, usuario: str) -> None:
    assert _como_api(apex_roles, _trabajo(usuario), _trabajo(usuario, clase="prueba.otra")) is None


def test_el_propietario_inserta_cualquier_job(apex_roles: RolesDb) -> None:
    """El CLI no cambia: `migrate-provider`, `rewrap`, `pending`, `done`, `total = 0`, con el
    usuario técnico."""
    pasos = [
        _trabajo(SYSTEM, kind="migrate_provider", clase=None, total=0),
        _trabajo(SYSTEM, kind="rewrap", clase="prueba.uno", estado="pending", total=0),
        _trabajo(SYSTEM, clase="prueba.dos", estado="done", total=3, hecho=3),
    ]
    assert intentar(apex_roles.dsn(), *pasos) is None


# guard_jobs_update ---

ID_TRABAJO = "(SELECT id FROM crypto.crypto_jobs WHERE data_class = 'prueba.rotacion')"


def _actualizar(asignacion: str) -> str:
    return f"UPDATE crypto.crypto_jobs SET {asignacion} WHERE id = {ID_TRABAJO}"


@pytest.mark.parametrize(
    "asignacion",
    [
        "done = 3, updated_at = now()",
        "status = 'failed', error = 'timeout', finished_at = now(), updated_at = now()",
        "status = 'done', done = total, finished_at = now(), updated_at = now()",
        "started_at = now()",
        "finished_at = now()",
        "status = 'failed', error = 'x', finished_at = now()",
    ],
    ids=[
        "done",
        "status_failed_con_error",
        "status_done_con_done_igual_a_total",
        "started_at",
        "finished_at",
        "failed_con_finished_at",
    ],
)
def test_apex_api_actualiza_las_columnas_de_progreso(
    apex_roles: RolesDb, usuario: str, asignacion: str
) -> None:
    error = _como_api(apex_roles, _trabajo(usuario), _actualizar(asignacion))
    assert error is None, (asignacion, error)


def test_un_job_running_no_lleva_error(apex_roles: RolesDb, usuario: str) -> None:
    error = _como_api(apex_roles, _trabajo(usuario), _actualizar("error = 'batch_failed'"))
    assert _sqlstate(error) == GUARDA, error


def test_reanudar_sin_limpiar_el_error_falla(apex_roles: RolesDb, usuario: str) -> None:
    pasos = [
        _trabajo(usuario),
        _actualizar("status = 'failed', error = 'x'"),
        _actualizar("status = 'running'"),
    ]
    assert _sqlstate(_como_api(apex_roles, *pasos)) == GUARDA


def test_failed_exige_error(apex_roles: RolesDb, usuario: str) -> None:
    error = _como_api(apex_roles, _trabajo(usuario), _actualizar("status = 'failed'"))
    assert _sqlstate(error) == GUARDA, error


def test_reanudar_un_failed_limpiando_el_error_pasa(apex_roles: RolesDb, usuario: str) -> None:
    pasos = [
        _trabajo(usuario),
        _actualizar("status = 'failed', error = 'x', finished_at = now()"),
        _actualizar("status = 'running', error = NULL, finished_at = NULL"),
    ]
    assert _como_api(apex_roles, *pasos) is None


def test_rotated_at_es_obligatorio_en_la_rotacion_del_api(
    apex_roles: RolesDb, usuario: str
) -> None:
    pasos = _rotacion(usuario)
    pasos[2] = pasos[2].replace("rotated_at = now()", "rotated_at = NULL")
    assert _sqlstate(_como_api(apex_roles, *pasos)) == GUARDA


def test_done_nunca_decrece(apex_roles: RolesDb, usuario: str) -> None:
    pasos = [_trabajo(usuario), _actualizar("done = 3"), _actualizar("done = 2")]
    assert _sqlstate(_como_api(apex_roles, *pasos)) == GUARDA


def test_total_no_cambia(apex_roles: RolesDb, usuario: str) -> None:
    """Sin `UPDATE (total)` por grant el api recibe `42501`; si el Verde lo concediera, la guarda
    responde `23514`: en los dos casos el valor no cambia."""
    error = _como_api(apex_roles, _trabajo(usuario), _actualizar("total = 1"))
    assert _sqlstate(error) in {PRIVACION, GUARDA}, error


@pytest.mark.parametrize("asignacion", ["status = 'done'", "status = 'done', done = 2"])
def test_status_done_exige_done_igual_a_total(
    apex_roles: RolesDb, usuario: str, asignacion: str
) -> None:
    error = _como_api(apex_roles, _trabajo(usuario), _actualizar(asignacion))
    assert _sqlstate(error) == GUARDA, (asignacion, error)


@pytest.mark.parametrize(
    "asignacion",
    [
        "kind = 'rewrap'",
        "data_class = 'prueba.otra'",
        "created_by = created_by",
        "id = gen_random_uuid()",
    ],
    ids=["kind", "data_class", "created_by", "id"],
)
def test_el_api_no_cambia_kind_ni_data_class_ni_identidad(
    apex_roles: RolesDb, usuario: str, asignacion: str
) -> None:
    error = _como_api(apex_roles, _trabajo(usuario), _actualizar(asignacion))
    assert _sqlstate(error) == PRIVACION, (asignacion, error)


def test_el_api_no_borra_ni_trunca_jobs(apex_roles: RolesDb, usuario: str) -> None:
    for sentencia in ("DELETE FROM crypto.crypto_jobs", "TRUNCATE crypto.crypto_jobs"):
        error = _como_api(apex_roles, _trabajo(usuario), sentencia)
        assert _sqlstate(error) == PRIVACION, sentencia


# Forma de los objetos ---


def _funcion(url: str, nombre: str) -> object:
    filas = consultar(
        url,
        "SELECT p.prosecdef AS definer, p.proconfig AS config, p.prosrc AS cuerpo "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'crypto' AND p.proname = $1",
        nombre,
    )
    assert len(filas) == 1, f"falta crypto.{nombre}"
    return filas[0]


def test_las_tres_funciones_son_security_invoker_y_las_nuevas_fijan_search_path(base: str) -> None:
    for nombre in FUNCIONES:
        funcion = _funcion(base, nombre)
        assert funcion["definer"] is False, nombre  # type: ignore[index]
    for nombre in FUNCIONES:  # también la guarda de llaves reescrita
        config = _funcion(base, nombre)["config"] or []  # type: ignore[index]
        assert "search_path=pg_catalog" in config, nombre


def test_los_tres_triggers_estan_en_always_y_son_de_fila(base: str) -> None:
    filas = consultar(
        base,
        "SELECT p.proname, t.tgenabled::text AS estado, pg_get_triggerdef(t.oid) AS def "
        "FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid "
        "WHERE NOT t.tgisinternal AND p.proname = ANY($1::text[])",
        list(FUNCIONES),
    )
    por_funcion = {f["proname"]: f for f in filas}
    assert set(por_funcion) == set(FUNCIONES), sorted(por_funcion)
    assert {f["estado"] for f in filas} == {"A"}, [(f["proname"], f["estado"]) for f in filas]
    assert "BEFORE INSERT" in por_funcion["guard_jobs_insert"]["def"]
    assert "ON crypto.crypto_jobs" in por_funcion["guard_jobs_insert"]["def"]
    assert "BEFORE UPDATE" in por_funcion["guard_jobs_update"]["def"]
    assert "ON crypto.crypto_jobs" in por_funcion["guard_jobs_update"]["def"]
    assert "FOR EACH ROW" in por_funcion["guard_jobs_update"]["def"]


def test_el_trigger_de_cierre_es_diferido_after_update_y_always(base: str) -> None:
    (fila,) = consultar(
        base,
        "SELECT t.tgdeferrable AS diferible, t.tginitdeferred AS diferido, "
        "t.tgenabled::text AS estado, pg_get_triggerdef(t.oid) AS def "
        "FROM pg_trigger t WHERE t.tgname = 'crypto_keys_guard_cierre' AND NOT t.tgisinternal",
    )
    assert fila["diferible"] is True and fila["diferido"] is True
    assert fila["estado"] == "A"
    assert "AFTER UPDATE" in fila["def"] and "ON crypto.crypto_keys" in fila["def"]


def _cuerpo_0015() -> str:
    spec = importlib.util.spec_from_file_location("m0015", MIGRACION_0015)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    sql: str = modulo.UPGRADE_SQL
    return sql[sql.index("$$") + 2 : sql.rindex("$$")].strip()


def test_la_guarda_de_llaves_ya_no_es_la_de_0015_y_nombra_al_rol_api(base: str) -> None:
    cuerpo = str(_funcion(base, "guard_keys_update")["cuerpo"]).strip()  # type: ignore[index]
    assert cuerpo != _cuerpo_0015()
    assert "apex_api" in cuerpo


def test_las_guardas_nuevas_distinguen_al_rol_y_no_estorban_al_propietario(base: str) -> None:
    for nombre in NUEVAS:
        assert "apex_api" in str(_funcion(base, nombre)["cuerpo"]), nombre  # type: ignore[index]


# Ciclo ---


def _funciones_nuevas(url: str) -> list[str]:
    return [
        f["proname"]
        for f in consultar(
            url,
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'crypto' AND p.proname = ANY($1::text[])",
            list(NUEVAS),
        )
    ]


def test_downgrade_restaura_el_cuerpo_de_0015_y_borra_las_dos_guardas(
    alembic_config: Config, base: str
) -> None:
    assert sorted(_funciones_nuevas(base)) == sorted(NUEVAS)
    try:
        command.downgrade(alembic_config, PADRE)
        assert _funciones_nuevas(base) == []
        quedan = consultar(
            base,
            "SELECT t.tgname FROM pg_trigger t WHERE NOT t.tgisinternal "
            "AND t.tgrelid = 'crypto.crypto_jobs'::regclass ORDER BY t.tgname",
        )
        # solo quedan los de 0003; los de 0024 (guard_jobs_insert/update) se borraron
        assert [f["tgname"] for f in quedan] == ["crypto_jobs_forbid_truncate", "crypto_jobs_guard"]
        assert str(_funcion(base, "guard_keys_update")["cuerpo"]).strip() == _cuerpo_0015()  # type: ignore[index]
        assert not consultar(
            base, "SELECT 1 FROM pg_trigger WHERE tgname = 'crypto_keys_guard_cierre'"
        )
        # El resto sigue: el trigger de llaves de 0003/0014 y las tablas.
        assert existe(base, "crypto.crypto_keys") and existe(base, "crypto.crypto_jobs")
    finally:
        command.upgrade(alembic_config, "head")
    assert sorted(_funciones_nuevas(base)) == sorted(NUEVAS)


def test_ciclo_head_base_head(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, "base")
        assert _funciones_nuevas(base) == []
    finally:
        command.upgrade(alembic_config, "head")
    assert sorted(_funciones_nuevas(base)) == sorted(NUEVAS)


def test_los_ids_de_las_pruebas_son_uuid_validos() -> None:
    """Guarda de las constantes de este archivo."""
    assert UUID(SYSTEM)
