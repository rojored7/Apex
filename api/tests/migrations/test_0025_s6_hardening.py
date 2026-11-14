"""`0025_s6_hardening` (S7-W0-2; S7-D3, S6-D130, S6-D133, M-6, L-6). Rojo.

Padre `0024_crypto_rotation_from_api`; id de 32 caracteres o menos. Endurece lo que el Sprint 6
dejó como deuda:
- (a) FK `fk_attachments_key_id` de `attachments.attachments.key_id` a `crypto.crypto_keys(id)`
  `ON DELETE RESTRICT` (`NOT VALID` + `VALIDATE`);
- (b) `CHECK ((purpose = 'sign') = (public_key IS NOT NULL))` en lugar del unidireccional;
- (c) `CHECK (kind <> 'photo' OR NOT sensitive)`;
- (d) `guard_keys_update()`: `public_key` no nula es inmutable para todo rol (completar un nulo
  sigue permitido);
- (e) `guard_jobs_update()`: `apex_api` solo toca jobs `rotate`.
Cada consulta previa aborta nombrando la regla y el conteo, nunca los valores. Las filas violadoras
se siembran en la base de la prueba tras bajar a `0024` y se limpian al terminar.
"""

# ruff: noqa: S608
from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_ATTACHMENTS
from tests.factories.triggers import disable_user_sql, rearm_always_sql
from tests.migrations._apoyo_notificaciones import consultar
from tests.migrations.conftest import RolesDb
from tests.migrations.test_db_grants import _correr, intentar

REVISION = "0025_s6_hardening"
PADRE = "0024_crypto_rotation_from_api"
SYSTEM = "00000000-0000-0000-0000-000000000001"
GUARDA = "23514"  # check_violation
FK = "23503"  # foreign_key_violation
VERSIONES = Path(__file__).resolve().parents[2] / "migrations" / "versions"
MIGRACION_0024 = VERSIONES / "0024_crypto_rotation_from_api.py"
CLASE = "prueba.endurecer"
CLASE_PREVIA = "prueba.previa"


def _revision_existe(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")


def test_cuelga_de_0024_tiene_id_corto_y_es_head(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 32  # `alembic_version.version_num` es varchar(32)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    assert scripts.get_heads() == [REVISION]


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> Iterator[str]:
    _revision_existe(alembic_config)
    yield migrated_database


@pytest.fixture(scope="module")
def dueno(apex_roles: RolesDb) -> str:
    """DSN del propietario sobre la base `apex_roles` (a `head`, con los roles reales)."""
    return apex_roles.dsn()


# SQL de apoyo -----------------------------------------------------------------------------------


def _llave(
    version: int = 1,
    estado: str = "active",
    *,
    purpose: str = "encrypt",
    clave_publica: str | None = None,
    clase: str = CLASE,
    id_: str | None = None,
) -> str:
    algoritmo = {"encrypt": "A256GCM", "index": "HMAC-SHA256", "sign": "Ed25519"}[purpose]
    publica = "NULL" if clave_publica is None else f"'{clave_publica}'"
    return (
        "INSERT INTO crypto.crypto_keys (id, created_by, purpose, data_class, algorithm, "
        "provider, version, state, wrapped_material, public_key) VALUES "
        f"('{id_ or uuid4()}', '{SYSTEM}', '{purpose}', '{clase}', '{algoritmo}', 'local', "
        f"{version}, '{estado}', '\\x01', {publica})"
    )


def _adjunto(
    key_id: str | None,
    *,
    kind: str = "consent",
    sensitive: bool = True,
    mime: str = "application/pdf",
) -> str:
    clave = "NULL" if key_id is None else f"'{key_id}'"
    return (
        "INSERT INTO attachments.attachments (id, owner_table, owner_id, kind, filename_random, "
        "mime, size_bytes, sensitive, key_id, storage_provider, uploaded_by, created_by) VALUES "
        f"('{uuid4()}', 'members', gen_random_uuid(), '{kind}', '{uuid4().hex}', '{mime}', 10, "
        f"{'true' if sensitive else 'false'}, {clave}, 'local', '{SYSTEM}', '{SYSTEM}')"
    )


def _trabajo(kind: str, clase: str | None = None) -> str:
    clase_sql = "NULL" if clase is None else f"'{clase}'"
    return (
        "INSERT INTO crypto.crypto_jobs (id, created_by, kind, data_class, status, total, done, "
        f"started_at) VALUES ('{uuid4()}', '{SYSTEM}', '{kind}', {clase_sql}, 'running', 5, 0, "
        "now())"
    )


def _sqlstate(error: object) -> str | None:
    return None if error is None else str(getattr(error, "sqlstate", None))


def _restriccion(error: object) -> str:
    return str(getattr(error, "constraint_name", None))


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


# (a) FK de attachments.key_id ---


def test_fk_rechaza_key_id_inexistente(dueno: str) -> None:
    error = intentar(dueno, _adjunto(str(uuid4())))
    assert _sqlstate(error) == FK, error
    assert _restriccion(error) == "fk_attachments_key_id"


def test_fk_acepta_una_llave_existente(dueno: str) -> None:
    llave = str(uuid4())
    assert intentar(dueno, _llave(id_=llave), _adjunto(llave)) is None


def test_fk_impide_borrar_llave_referida(dueno: str) -> None:
    llave = str(uuid4())
    pasos = [
        _llave(id_=llave),
        _adjunto(llave),
        # la guarda de `crypto_keys` prohíbe todo `DELETE`: se apaga solo dentro de esta
        # transacción (siempre se revierte) para que hable la FK `ON DELETE RESTRICT`.
        "ALTER TABLE crypto.crypto_keys DISABLE TRIGGER USER",
        f"DELETE FROM crypto.crypto_keys WHERE id = '{llave}'",
    ]
    error = intentar(dueno, *pasos)
    assert _sqlstate(error) == FK, error


def test_fk_validada_y_con_restrict(dueno: str) -> None:
    (fila,) = consultar(
        dueno,
        "SELECT convalidated AS validada, confdeltype::text AS borrado, "
        "confrelid::regclass::text AS destino FROM pg_constraint "
        "WHERE conname = 'fk_attachments_key_id'",
    )
    assert fila["validada"] is True
    assert fila["borrado"] == "r"  # RESTRICT
    assert fila["destino"] == "crypto.crypto_keys"


# (b) CHECK sign_iff_public_key ---


def test_sign_iff_public_key_rechaza_encrypt_con_clave_publica(dueno: str) -> None:
    error = intentar(dueno, _llave(purpose="encrypt", clave_publica="x"))
    assert _sqlstate(error) == GUARDA, error
    assert _restriccion(error) == "ck_crypto_keys_sign_iff_public_key"


def test_sign_iff_public_key_rechaza_sign_sin_clave(dueno: str) -> None:
    error = intentar(dueno, _llave(purpose="sign", clave_publica=None))
    assert _sqlstate(error) == GUARDA, error
    assert _restriccion(error) == "ck_crypto_keys_sign_iff_public_key"


def test_sign_con_clave_y_encrypt_sin_clave_conviven(dueno: str) -> None:
    pasos = [_llave(purpose="sign", clave_publica="x"), _llave(purpose="encrypt")]
    assert intentar(dueno, *pasos) is None


def test_el_check_unidireccional_ya_no_existe(dueno: str) -> None:
    nombres = {
        f["conname"]
        for f in consultar(
            dueno,
            "SELECT conname FROM pg_constraint WHERE conrelid = 'crypto.crypto_keys'::regclass",
        )
    }
    assert "ck_crypto_keys_sign_public_key" not in nombres
    assert "ck_crypto_keys_sign_iff_public_key" in nombres


# (c) CHECK photo_not_sensitive ---


def test_photo_not_sensitive(dueno: str) -> None:
    error = intentar(dueno, _adjunto(str(uuid4()), kind="photo", sensitive=True, mime="image/png"))
    assert _sqlstate(error) == GUARDA, error
    assert _restriccion(error) == "ck_attachments_photo_not_sensitive"


def test_una_foto_no_sensible_y_un_consentimiento_sensible_siguen_permitidos(dueno: str) -> None:
    llave = str(uuid4())
    pasos = [
        _llave(id_=llave),
        _adjunto(None, kind="photo", sensitive=False, mime="image/png"),
        _adjunto(llave, kind="consent", sensitive=True),
    ]
    assert intentar(dueno, *pasos) is None


# (d) public_key inmutable ---


def test_propietario_no_cambia_public_key_no_nula(dueno: str) -> None:
    id_ = str(uuid4())
    pasos = [
        _llave(purpose="sign", clave_publica="x", id_=id_),
        f"UPDATE crypto.crypto_keys SET public_key = 'otra', updated_at = now() WHERE id = '{id_}'",
    ]
    error = intentar(dueno, *pasos)
    assert _sqlstate(error) == GUARDA, error
    assert "public_key" in str(error)


def test_propietario_no_borra_public_key_no_nula(dueno: str) -> None:
    id_ = str(uuid4())
    pasos = [
        _llave(purpose="sign", clave_publica="x", id_=id_),
        f"UPDATE crypto.crypto_keys SET public_key = NULL, updated_at = now() WHERE id = '{id_}'",
    ]
    error = intentar(dueno, *pasos)
    assert _sqlstate(error) == GUARDA, error
    assert "public_key" in str(error)


def test_completar_public_key_nula_sigue_permitido(dueno: str) -> None:
    """D99: la guarda deja completar un nulo. Para aislarla del CHECK (b) se quita ese CHECK solo
    dentro de la transacción de la prueba, que siempre se revierte."""
    id_ = str(uuid4())
    pasos = [
        "ALTER TABLE crypto.crypto_keys DROP CONSTRAINT ck_crypto_keys_sign_iff_public_key",
        _llave(purpose="encrypt", id_=id_),
        f"UPDATE crypto.crypto_keys SET public_key = 'x', updated_at = now() WHERE id = '{id_}'",
    ]
    assert intentar(dueno, *pasos) is None


def test_la_migracion_de_proveedor_del_propietario_sigue_permitida(dueno: str) -> None:
    id_ = str(uuid4())
    pasos = [
        _llave(purpose="sign", clave_publica="x", id_=id_),
        "UPDATE crypto.crypto_keys SET provider = 'openbao', wrapped_material = '\\x02', "
        f"updated_at = now() WHERE id = '{id_}'",
    ]
    assert intentar(dueno, *pasos) is None


# (e) guard_jobs_update solo rotate ---


@pytest.mark.parametrize("kind", ["migrate_provider", "rewrap"])
def test_apex_api_no_reabre_job_migrate_provider_ni_rewrap(dueno: str, kind: str) -> None:
    pasos = [
        _trabajo(kind),
        "SET LOCAL ROLE apex_api",
        f"UPDATE crypto.crypto_jobs SET done = 3, updated_at = now() WHERE kind = '{kind}' "
        "AND status = 'running'",
    ]
    error = intentar(dueno, *pasos)
    assert _sqlstate(error) == GUARDA, error
    assert "rotate" in str(error)


def test_apex_api_sigue_actualizando_un_job_rotate(dueno: str) -> None:
    pasos = [
        _trabajo("rotate", CLASE),
        "SET LOCAL ROLE apex_api",
        "UPDATE crypto.crypto_jobs SET done = 3, updated_at = now() WHERE kind = 'rotate' "
        f"AND data_class = '{CLASE}'",
    ]
    assert intentar(dueno, *pasos) is None


def test_el_propietario_sigue_tocando_cualquier_job(dueno: str) -> None:
    pasos = [
        _trabajo("migrate_provider"),
        "UPDATE crypto.crypto_jobs SET done = 3, updated_at = now() "
        "WHERE kind = 'migrate_provider' AND status = 'running'",
    ]
    assert intentar(dueno, *pasos) is None


# Consulta previa (L-6) ---


def _ejecutar(url: str, *sentencias: str) -> None:
    async def trabajo(c: asyncpg.Connection) -> None:
        for sentencia in sentencias:
            await c.execute(sentencia)

    _correr(_dsn(url), trabajo)


def _siembra(regla: str, valor: str) -> list[str]:
    """Una fila que viola la regla, tal como pudo quedar con `0024` (sin el endurecimiento)."""
    if regla == "fk_attachments_key_id":
        return [_adjunto(valor)]
    if regla == "sign_iff_public_key":
        return [_llave(purpose="encrypt", clave_publica=valor, clase=CLASE_PREVIA)]
    llave = str(uuid4())  # photo_not_sensitive: una llave real, para no tropezar con (a)
    return [
        _llave(id_=llave, clase=CLASE_PREVIA),
        _adjunto(llave, kind="photo", sensitive=True, mime="image/png"),
    ]


def _limpiar_siembra(url: str) -> None:
    _ejecutar(
        url,
        LIMPIAR_ATTACHMENTS,
        disable_user_sql("crypto.crypto_keys"),
        f"DELETE FROM crypto.crypto_keys WHERE data_class = '{CLASE_PREVIA}'",
        rearm_always_sql("crypto.crypto_keys"),
    )


@pytest.mark.parametrize(
    "regla", ["fk_attachments_key_id", "sign_iff_public_key", "photo_not_sensitive"]
)
def test_consulta_previa_aborta_con_regla_y_conteo_sin_valores(
    alembic_config: Config, base: str, regla: str
) -> None:
    centinela = str(uuid4())
    valor = "centinela-publico" if regla == "sign_iff_public_key" else centinela
    try:
        command.downgrade(alembic_config, PADRE)
        _ejecutar(base, *_siembra(regla, valor))
        with pytest.raises(Exception) as excepcion:
            command.upgrade(alembic_config, "head")
        mensaje = str(excepcion.value)
        assert regla in mensaje, mensaje
        assert "violan 1 fila" in mensaje, mensaje  # el conteo
        assert valor not in mensaje and centinela not in mensaje, (
            "la consulta previa filtró un valor"
        )
        version = consultar(base, "SELECT version_num FROM alembic_version")[0]["version_num"]
        assert version == PADRE  # la migración es transaccional: no quedó a medias
    finally:
        _limpiar_siembra(base)
        command.upgrade(alembic_config, "head")


# Forma y ciclo ---


def _cuerpo_0024(nombre: str) -> str:
    spec = importlib.util.spec_from_file_location("m0024", MIGRACION_0024)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    sql: str = {"keys": modulo.KEYS_UPGRADE_SQL, "jobs": modulo.JOBS_UPDATE_SQL}[nombre]
    return sql[sql.index("$$") + 2 : sql.rindex("$$")].strip()


def _prosrc(url: str, funcion: str) -> str:
    (fila,) = consultar(
        url,
        "SELECT p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'crypto' AND p.proname = $1",
        funcion,
    )
    return str(fila["prosrc"]).strip()


def test_las_guardas_cambian_y_conservan_los_triggers_always(base: str) -> None:
    assert _prosrc(base, "guard_keys_update") != _cuerpo_0024("keys")
    assert _prosrc(base, "guard_jobs_update") != _cuerpo_0024("jobs")
    filas = consultar(
        base,
        "SELECT t.tgname, t.tgenabled::text AS estado FROM pg_trigger t "
        "WHERE t.tgname IN ('crypto_keys_guard', 'crypto_keys_guard_cierre', "
        "'crypto_jobs_guard_update', 'crypto_jobs_guard_insert')",
    )
    assert len(filas) == 4
    assert {f["estado"] for f in filas} == {"A"}, filas


def test_ciclo_downgrade_upgrade(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert not consultar(
            base, "SELECT 1 FROM pg_constraint WHERE conname = 'fk_attachments_key_id'"
        )
        nombres = {
            f["conname"]
            for f in consultar(
                base,
                "SELECT conname FROM pg_constraint WHERE conname IN "
                "('ck_crypto_keys_sign_public_key', 'ck_crypto_keys_sign_iff_public_key', "
                "'ck_attachments_photo_not_sensitive')",
            )
        }
        assert nombres == {"ck_crypto_keys_sign_public_key"}
        assert _prosrc(base, "guard_keys_update") == _cuerpo_0024("keys")
        assert _prosrc(base, "guard_jobs_update") == _cuerpo_0024("jobs")
    finally:
        command.upgrade(alembic_config, "head")
    assert consultar(base, "SELECT 1 FROM pg_constraint WHERE conname = 'fk_attachments_key_id'")
    assert _prosrc(base, "guard_jobs_update") != _cuerpo_0024("jobs")
