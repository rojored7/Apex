"""`0022_verify_signatures` (S6-A3, US-142; S6-D10, S6-D99). Rojo A3.

Padre `0021_audit_signatures`; es head. Contrato:
- `audit.verifications` gana seis columnas NULAS: `signatures_checked` integer,
  `signatures_valid` integer, `first_invalid_signature_seq` bigint, `last_valid_signature_seq`
  bigint, `last_valid_signature_at` timestamptz y `last_valid_signature_algorithm` text; las trece
  columnas de `0013` no cambian y las filas previas quedan intactas (las seis en NULL);
- los triggers `verifications_forbid_*` (de `0013`/`0014`) y `signatures_forbid_*` (de `0021`)
  siguen en `tgenabled = 'A'` sobre sus funciones; la tabla sigue siendo append-only también para
  las columnas nuevas;
- S6-D99: `VALIDATE CONSTRAINT ck_crypto_keys_sign_public_key` (nació `NOT VALID` en `0021`): tras
  `0022` está validado y la migración aborta, sin cambiar de revisión, si queda una fila `sign`
  sin clave pública (se completa antes con `init-keys --data-class audit.signature`);
- `downgrade` quita las seis columnas y nada más; el ciclo `head -> base -> head` cierra.
Las verificaciones que dejan las pruebas se borran con `LIMPIAR_VERIFICATIONS`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_LLAVES, LIMPIAR_VERIFICATIONS
from tests.factories.triggers import disable_user_sql, rearm_always_sql
from tests.migrations._apoyo_notificaciones import columnas, consultar, existe

REVISION = "0022_verify_signatures"
PADRE = "0021_audit_signatures"
ABUELO = "0020_notifications_indexes"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
INMUTABLE = "P0001"
HASH = "0123456789abcdef" * 4
INICIO = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
FIN = INICIO + timedelta(seconds=2)
TABLA = "audit.verifications"
CONSTRAINT = "ck_crypto_keys_sign_public_key"
TRIGGERS_VERIFICACIONES = ("verifications_forbid_mutation", "verifications_forbid_truncate")
TRIGGERS_FIRMAS = ("signatures_forbid_mutation", "signatures_forbid_truncate")

NUEVAS = {
    "signatures_checked": ("integer", "YES"),
    "signatures_valid": ("integer", "YES"),
    "first_invalid_signature_seq": ("bigint", "YES"),
    "last_valid_signature_seq": ("bigint", "YES"),
    "last_valid_signature_at": ("timestamp with time zone", "YES"),
    "last_valid_signature_algorithm": ("text", "YES"),
}
ORIGINALES = {
    "id": ("uuid", "NO"),
    "started_at": ("timestamp with time zone", "NO"),
    "finished_at": ("timestamp with time zone", "NO"),
    "through_seq": ("bigint", "NO"),
    "through_hash": ("character", "NO"),
    "rows_checked": ("bigint", "NO"),
    "ok": ("boolean", "NO"),
    "broken_at_seq": ("bigint", "YES"),
    "triggered_by": ("uuid", "NO"),
    "source": ("text", "NO"),
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


def _sqlstate(url: str, *sentencias: str) -> str | None:
    try:
        _ejecutar(url, *sentencias)
    except asyncpg.PostgresError as error:
        return str(error.sqlstate)
    return None


def _insertar(url: str, **extra: Any) -> UUID:
    """Una verificación; `extra` agrega columnas de firmas (solo con la base en `0022`)."""
    valores: dict[str, Any] = {
        "id": uuid4(),
        "started_at": INICIO,
        "finished_at": FIN,
        "through_seq": 10,
        "through_hash": HASH,
        "rows_checked": 10,
        "ok": True,
        "triggered_by": SYSTEM_USER_ID,
        "source": "api",
        "created_by": SYSTEM_USER_ID,
        **extra,
    }
    nombres = ", ".join(valores)
    marcas = ", ".join(f"${i}" for i in range(1, len(valores) + 1))

    async def correr() -> None:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            await conexion.execute(
                f"INSERT INTO audit.verifications ({nombres}) VALUES ({marcas})",  # noqa: S608
                *valores.values(),
            )
        finally:
            await conexion.close()

    asyncio.run(correr())
    return UUID(str(valores["id"]))


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
    """La base migrada con `0022`; borra verificaciones y llaves que la prueba deje."""
    _revision_existe(alembic_config)
    try:
        yield migrated_database
    finally:
        _ejecutar(migrated_database, LIMPIAR_VERIFICATIONS)


# Revisión ---------------------------------------------------------------------------------------


def test_la_revision_cuelga_de_0021_y_es_head(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    assert scripts.get_heads() == [REVISION]


# Forma ------------------------------------------------------------------------------------------


def test_las_seis_columnas_nuevas_son_nulas_y_con_el_tipo_del_plan(base: str) -> None:
    actuales = columnas(base, TABLA)
    assert {k: actuales.get(k) for k in NUEVAS} == NUEVAS


def test_las_trece_columnas_originales_no_cambian(base: str) -> None:
    actuales = columnas(base, TABLA)
    assert {k: actuales.get(k) for k in ORIGINALES} == ORIGINALES
    assert set(actuales) == set(ORIGINALES) | set(NUEVAS)


def test_las_columnas_nuevas_no_tienen_valor_por_omision(base: str) -> None:
    filas = consultar(
        base,
        "SELECT column_name, column_default FROM information_schema.columns "
        "WHERE table_schema = 'audit' AND table_name = 'verifications' "
        "AND column_name = ANY($1::text[])",
        list(NUEVAS),
    )
    assert len(filas) == len(NUEVAS)
    assert all(f["column_default"] is None for f in filas)


def test_una_verificacion_sin_firmas_entra_con_las_seis_en_null(base: str) -> None:
    identificador = _insertar(base)

    (fila,) = consultar(base, "SELECT * FROM audit.verifications WHERE id = $1", identificador)

    assert all(fila[k] is None for k in NUEVAS)


def test_una_verificacion_con_firmas_guarda_las_seis(base: str) -> None:
    identificador = _insertar(
        base,
        signatures_checked=3,
        signatures_valid=2,
        first_invalid_signature_seq=70,
        last_valid_signature_seq=50,
        last_valid_signature_at=INICIO,
        last_valid_signature_algorithm="Ed25519",
    )

    (fila,) = consultar(base, "SELECT * FROM audit.verifications WHERE id = $1", identificador)

    assert (fila["signatures_checked"], fila["signatures_valid"]) == (3, 2)
    assert (fila["first_invalid_signature_seq"], fila["last_valid_signature_seq"]) == (70, 50)
    assert fila["last_valid_signature_at"] == INICIO
    assert fila["last_valid_signature_algorithm"] == "Ed25519"


def test_las_filas_previas_quedan_intactas_con_las_seis_en_null(
    alembic_config: Config, base: str
) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        previa = _insertar(base, ok=False, broken_at_seq=7, source="cli")
        antes = consultar(base, "SELECT * FROM audit.verifications WHERE id = $1", previa)
        command.upgrade(alembic_config, "head")
        (despues,) = consultar(base, "SELECT * FROM audit.verifications WHERE id = $1", previa)
        assert {k: despues[k] for k in antes[0].keys()} == dict(antes[0])
        assert all(despues[k] is None for k in NUEVAS)
    finally:
        command.upgrade(alembic_config, "head")


# Inmutabilidad conservada ------------------------------------------------------------------------


def test_los_triggers_de_verificaciones_y_de_firmas_siguen_en_always(base: str) -> None:
    filas = consultar(
        base,
        "SELECT c.relname, t.tgname, t.tgenabled::text AS estado "
        "FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "WHERE c.relname IN ('verifications', 'signatures') AND NOT t.tgisinternal",
    )
    por_nombre = {f["tgname"]: f["estado"] for f in filas}
    assert set(por_nombre) == {*TRIGGERS_VERIFICACIONES, *TRIGGERS_FIRMAS}
    assert set(por_nombre.values()) == {"A"}


@pytest.mark.parametrize(
    "sentencia",
    [
        "UPDATE audit.verifications SET signatures_checked = 9",
        "UPDATE audit.verifications SET last_valid_signature_algorithm = 'x'",
        "DELETE FROM audit.verifications",
        "TRUNCATE audit.verifications",
    ],
    ids=["update_contador", "update_algoritmo", "delete", "truncate"],
)
def test_la_tabla_sigue_siendo_append_only_tambien_en_las_columnas_nuevas(
    base: str, sentencia: str
) -> None:
    _insertar(base, signatures_checked=1)
    assert _sqlstate(base, sentencia) == INMUTABLE
    assert len(consultar(base, "SELECT id FROM audit.verifications")) == 1


def test_bajo_replica_los_triggers_de_verificaciones_siguen_disparando(base: str) -> None:
    _insertar(base)
    estado = _sqlstate(
        base,
        "SET session_replication_role = replica",
        "UPDATE audit.verifications SET signatures_valid = 1",
    )
    assert estado == INMUTABLE


# S6-D99: VALIDATE CONSTRAINT ---------------------------------------------------------------------


def test_el_check_de_la_clave_publica_queda_validado(base: str) -> None:
    (fila,) = consultar(
        base,
        "SELECT convalidated FROM pg_constraint "
        "WHERE conrelid = 'crypto.crypto_keys'::regclass AND conname = $1",
        CONSTRAINT,
    )
    assert fila["convalidated"] is True


def test_con_una_fila_sign_sin_clave_publica_la_0022_aborta_y_queda_en_0021(
    alembic_config: Config, base: str
) -> None:
    """La fila huérfana de S6-D99 solo puede existir si nació antes de `0021`."""
    huerfana = uuid4()
    _ejecutar(base, *LIMPIAR_LLAVES)  # ninguna otra fila `sign` de otras pruebas
    try:
        command.downgrade(alembic_config, ABUELO)
        sql = (
            "INSERT INTO crypto.crypto_keys (id, created_by, purpose, data_class, algorithm, "  # noqa: S608
            "provider, version, state, wrapped_material) VALUES "
            f"('{huerfana}', '{SYSTEM_USER_ID}', 'sign', 'test.cero_veintidos_firma', "
            "'Ed25519', 'local', 1, 'active', decode('00', 'hex'))"
        )
        _ejecutar(base, sql)
        command.upgrade(alembic_config, PADRE)  # el CHECK nace NOT VALID: tolera la fila
        with pytest.raises(Exception, match=r"(?i)ck_crypto_keys_sign_public_key|violat|check"):
            command.upgrade(alembic_config, "head")
        (version,) = consultar(base, "SELECT version_num FROM public.alembic_version")
        assert version["version_num"] == PADRE
        assert "signatures_checked" not in columnas(base, TABLA)
    finally:
        _ejecutar(
            base,
            disable_user_sql("crypto.crypto_keys"),
            f"DELETE FROM crypto.crypto_keys WHERE id = '{huerfana}'",  # noqa: S608
            rearm_always_sql("crypto.crypto_keys"),
        )
        command.upgrade(alembic_config, "head")
    assert "signatures_checked" in columnas(base, TABLA)


# Ciclo ------------------------------------------------------------------------------------------


def test_downgrade_quita_las_seis_columnas_y_nada_mas(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        actuales = columnas(base, TABLA)
        assert not set(NUEVAS) & set(actuales)
        assert {k: actuales.get(k) for k in ORIGINALES} == ORIGINALES
        assert existe(base, "audit.signatures")  # la 0021 sigue aplicada
        assert existe(base, TABLA)
        triggers = consultar(
            base,
            "SELECT tgname FROM pg_trigger WHERE tgname = ANY($1::text[])",
            [*TRIGGERS_VERIFICACIONES, *TRIGGERS_FIRMAS],
        )
        assert len(triggers) == 4
    finally:
        command.upgrade(alembic_config, "head")
    assert set(NUEVAS) <= set(columnas(base, TABLA))


def test_ciclo_head_base_head(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, "base")
        assert not existe(base, TABLA)
    finally:
        command.upgrade(alembic_config, "head")
    assert set(NUEVAS) <= set(columnas(base, TABLA))
