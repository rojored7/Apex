"""`0021_audit_signatures` (S6-A1, US-140; S6-D2, S6-D7, S6-D81). # Rojo A1

Padre `0020_notifications_indexes`; en la cadena hasta head (S6-A3: la `0022` cuelga de ella).
Crea `audit.signatures` y añade `crypto.crypto_keys.public_key`:
- `audit.signatures`: `id uuid` PK; `through_seq bigint NOT NULL` con índice único; `hash char(64)
  NOT NULL` (CHECK `^[0-9a-f]{64}$`); `signature text NOT NULL`; `key_id uuid NOT NULL` (FK lógica);
  `algorithm text NOT NULL` (CHECK en `Ed25519`, `ML-DSA-65`); `payload_version smallint NOT NULL
  DEFAULT 1` (CHECK >= 1); `signed_at timestamptz NOT NULL`; `created_at`, `updated_at`,
  `created_by`; índice `signed_at DESC`;
- triggers `signatures_forbid_mutation` (BEFORE UPDATE OR DELETE, por fila) y
  `signatures_forbid_truncate` (BEFORE TRUNCATE) con `ENABLE ALWAYS` (`tgenabled = 'A'`) sobre la
  función `audit.forbid_signature_mutation()`;
- `crypto_keys.public_key text` nula con CHECK `(purpose <> 'sign') OR (public_key IS NOT NULL)`;
  las filas existentes quedan intactas; `apex_api` y `apex_worker` no tienen `UPDATE` sobre ella.
`downgrade`: trigger(s), función, tabla, CHECK y columna. Cada CHECK se prueba con SQL crudo
(asyncpg): 23514; la inmutabilidad con el SQLSTATE `P0001` de la función. Las filas que dejan las
pruebas se borran con `LIMPIAR_SIGNATURES` / `LIMPIAR_LLAVES`.
"""

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

from tests.conftest import LIMPIAR_SIGNATURES
from tests.factories.triggers import disable_user_sql, rearm_always_sql
from tests.migrations._apoyo_notificaciones import (
    CHECK_VIOLATION,
    UNIQUE_VIOLATION,
    columnas,
    consultar,
    existe,
    resultados,
)

REVISION = "0021_audit_signatures"
PADRE = "0020_notifications_indexes"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
INMUTABLE = "P0001"  # `RAISE ... USING ERRCODE = 'P0001'` (como `audit.forbid_mutation()`)
HASH = "0123456789abcdef" * 4
KEY_ID = UUID("00000000-0000-0000-0000-0000000000a1")  # llave real de las firmas (FK de `key_id`)
CLASE_LLAVE = "test.cero_veintiuno_firma"
AHORA = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
TRIGGERS = ("signatures_forbid_mutation", "signatures_forbid_truncate")
FUNCION = "forbid_signature_mutation"
TABLA = "audit.signatures"

COLUMNAS = {
    "id": ("uuid", "NO"),
    "through_seq": ("bigint", "NO"),
    "hash": ("character", "NO"),
    "signature": ("text", "NO"),
    "key_id": ("uuid", "NO"),
    "algorithm": ("text", "NO"),
    "payload_version": ("smallint", "NO"),
    "signed_at": ("timestamp with time zone", "NO"),
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


def _firma(**cambios: Any) -> dict[str, Any]:
    fila: dict[str, Any] = {
        "id": uuid4(),
        "through_seq": 10,
        "hash": HASH,
        "signature": "apx1." + str(uuid4()) + ".Ed25519.c2lnbmF0dXJh",
        "key_id": KEY_ID,
        "algorithm": "Ed25519",
        "payload_version": 1,
        "signed_at": AHORA,
        "created_by": SYSTEM_USER_ID,
    }
    fila.update(cambios)
    return fila


def _paso_firma(fila: dict[str, Any]) -> tuple[str, list[Any]]:
    cols = list(fila)
    marcas = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
    sql = f"INSERT INTO audit.signatures ({', '.join(cols)}) VALUES ({marcas})"  # noqa: S608
    return sql, [fila[c] for c in cols]


def _insertar_firma(url: str, **cambios: Any) -> UUID:
    fila = _firma(**cambios)
    sql, args = _paso_firma(fila)

    async def correr() -> None:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            await conexion.execute(sql, *args)
        finally:
            await conexion.close()

    asyncio.run(correr())
    return UUID(str(fila["id"]))


def _llave(**cambios: Any) -> dict[str, Any]:
    fila: dict[str, Any] = {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "purpose": "encrypt",
        "data_class": "test.cero_veintiuno",
        "algorithm": "A256GCM",
        "provider": "local",
        "version": 1,
        "state": "active",
        "wrapped_material": b"\x00" * 8,
    }
    fila.update(cambios)
    return fila


def _paso_llave(fila: dict[str, Any]) -> tuple[str, list[Any]]:
    cols = list(fila)
    marcas = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
    sql = f"INSERT INTO crypto.crypto_keys ({', '.join(cols)}) VALUES ({marcas})"  # noqa: S608
    return sql, [fila[c] for c in cols]


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
    """La base migrada con `0021`; borra las firmas que la prueba deje."""
    _revision_existe(alembic_config)
    sql, args = _paso_llave(_llave(id=KEY_ID, data_class=CLASE_LLAVE))

    async def sembrar() -> None:
        conexion = await asyncpg.connect(_dsn(migrated_database))
        try:
            await conexion.execute(sql, *args)
        finally:
            await conexion.close()

    asyncio.run(sembrar())
    try:
        yield migrated_database
    finally:
        if existe(migrated_database, TABLA):
            _ejecutar(migrated_database, LIMPIAR_SIGNATURES)
        _ejecutar(
            migrated_database,
            disable_user_sql("crypto.crypto_keys"),
            f"DELETE FROM crypto.crypto_keys WHERE data_class = '{CLASE_LLAVE}'",  # noqa: S608
            rearm_always_sql("crypto.crypto_keys"),
        )


# Revisión ---------------------------------------------------------------------------------------


def test_la_revision_cuelga_de_0020_y_esta_en_la_cadena_hasta_head(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()  # S6-A3: ya no es head (la `0022` cuelga de ella)
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


# Forma de audit.signatures -----------------------------------------------------------------------


def test_columnas_tipos_y_nulabilidad(base: str) -> None:
    assert columnas(base, TABLA) == COLUMNAS
    largo = consultar(
        base,
        "SELECT character_maximum_length AS n FROM information_schema.columns "
        "WHERE table_schema = 'audit' AND table_name = 'signatures' AND column_name = 'hash'",
    )[0]["n"]
    assert largo == 64


def test_payload_version_vale_1_por_omision(base: str) -> None:
    filas = consultar(
        base,
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_schema = 'audit' AND table_name = 'signatures' "
        "AND column_name = 'payload_version'",
    )
    assert filas and str(filas[0]["column_default"]).strip("() ").startswith("1")


def test_indices_through_seq_unico_y_signed_at_descendente(base: str) -> None:
    filas = consultar(
        base,
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE schemaname = 'audit' AND tablename = 'signatures'",
    )
    definiciones = [f["indexdef"] for f in filas]
    assert any(
        d.startswith("CREATE UNIQUE INDEX") and d.endswith("(through_seq)") for d in definiciones
    )
    assert any("UNIQUE" not in d and d.endswith("(signed_at DESC)") for d in definiciones)
    assert len(filas) == 3  # la PK, `through_seq` único y `signed_at DESC`


def test_una_fila_valida_entra_y_los_dos_algoritmos_se_aceptan(base: str) -> None:
    _insertar_firma(base, through_seq=1)
    _insertar_firma(base, through_seq=2, algorithm="ML-DSA-65", payload_version=2)
    _insertar_firma(base, through_seq=3, hash="0" * 64)
    total = consultar(base, "SELECT count(*) AS n FROM audit.signatures")[0]["n"]
    assert total == 3


def test_through_seq_repetido_viola_el_indice_unico(base: str) -> None:
    _insertar_firma(base, through_seq=7)
    estado, _ = resultados(base, [[_paso_firma(_firma(through_seq=7))]])[0]
    assert estado == UNIQUE_VIOLATION


# CHECKs (23514) ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cambios",
    [
        {"hash": "A" * 64},
        {"hash": "g" * 64},
        {"hash": "a" * 63},
        {"hash": "a" * 63 + " "},
        {"algorithm": "RSA"},
        {"algorithm": "ed25519"},
        {"algorithm": "ML-DSA-44"},
        {"payload_version": 0},
        {"payload_version": -1},
    ],
    ids=[
        "hash_en_mayusculas",
        "hash_no_hexadecimal",
        "hash_de_63",
        "hash_con_espacio",
        "algoritmo_ajeno",
        "algoritmo_en_minusculas",
        "ml_dsa_otro",
        "version_cero",
        "version_negativa",
    ],
)
def test_cada_check_rechaza(base: str, cambios: dict[str, Any]) -> None:
    estado, _ = resultados(base, [[_paso_firma(_firma(**cambios))]])[0]
    assert estado == CHECK_VIOLATION


# Inmutabilidad ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sentencia",
    [
        "UPDATE audit.signatures SET algorithm = 'ML-DSA-65'",
        "UPDATE audit.signatures SET signature = 'x'",
        "DELETE FROM audit.signatures",
        "TRUNCATE audit.signatures",
    ],
    ids=["update_algoritmo", "update_firma", "delete", "truncate"],
)
def test_update_delete_y_truncate_se_rechazan(base: str, sentencia: str) -> None:
    _insertar_firma(base)
    assert _sqlstate(base, sentencia) == INMUTABLE
    assert len(consultar(base, "SELECT id FROM audit.signatures")) == 1


@pytest.mark.parametrize(
    "sentencia",
    ["UPDATE audit.signatures SET algorithm = 'ML-DSA-65'", "DELETE FROM audit.signatures"],
    ids=["update", "delete"],
)
def test_bajo_replica_los_triggers_siguen_disparando(base: str, sentencia: str) -> None:
    _insertar_firma(base)
    estado = _sqlstate(base, "SET session_replication_role = replica", sentencia)
    assert estado == INMUTABLE
    assert len(consultar(base, "SELECT id FROM audit.signatures")) == 1


def test_bajo_replica_el_truncate_sigue_rechazado(base: str) -> None:
    assert (
        _sqlstate(base, "SET session_replication_role = replica", "TRUNCATE audit.signatures")
        == INMUTABLE
    )


def test_triggers_en_always_con_la_definicion_esperada(base: str) -> None:
    filas = consultar(
        base,
        "SELECT t.tgname, t.tgenabled::text AS estado, pg_get_triggerdef(t.oid) AS def, "
        "p.proname AS funcion, n.nspname AS esquema "
        "FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid "
        "JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE t.tgrelid = 'audit.signatures'::regclass AND NOT t.tgisinternal",
    )
    por_nombre = {f["tgname"]: f for f in filas}
    assert set(por_nombre) == set(TRIGGERS)
    assert {f["estado"] for f in filas} == {"A"}
    mutacion, vaciado = (por_nombre[n] for n in TRIGGERS)
    # `pg_get_triggerdef` normaliza el orden de los eventos: `BEFORE DELETE OR UPDATE`.
    assert "BEFORE DELETE OR UPDATE" in mutacion["def"] and "FOR EACH ROW" in mutacion["def"]
    assert "BEFORE TRUNCATE" in vaciado["def"]
    assert (mutacion["esquema"], mutacion["funcion"]) == ("audit", FUNCION)


def test_key_id_es_llave_foranea_restrict_a_crypto_keys(base: str) -> None:
    filas = consultar(
        base,
        "SELECT pg_get_constraintdef(oid) AS def FROM pg_constraint "
        "WHERE conrelid = 'audit.signatures'::regclass AND contype = 'f'",
    )
    assert len(filas) == 1
    assert "FOREIGN KEY (key_id) REFERENCES crypto.crypto_keys(id)" in filas[0]["def"]
    assert "ON DELETE RESTRICT" in filas[0]["def"]
    estado, _ = resultados(base, [[_paso_firma(_firma(key_id=uuid4()))]])[0]
    assert estado == "23503"  # foreign_key_violation


def test_la_funcion_del_trigger_es_security_invoker_con_search_path_fijo(base: str) -> None:
    fila = consultar(
        base,
        "SELECT pg_get_functiondef('audit.forbid_signature_mutation'::regproc) AS def, "
        "prosecdef AS definer FROM pg_proc WHERE oid = 'audit.forbid_signature_mutation'::regproc",
    )[0]
    # `pg_get_functiondef` omite `SECURITY INVOKER` (es el valor por omisión): se lee `prosecdef`.
    assert fila["definer"] is False and "SECURITY DEFINER" not in fila["def"]
    assert "SET search_path TO 'pg_catalog'" in fila["def"]


# crypto.crypto_keys.public_key (S6-D81) ---------------------------------------------------------


def test_public_key_es_texto_nulo(base: str) -> None:
    assert columnas(base, "crypto.crypto_keys")["public_key"] == ("text", "YES")


def test_sign_sin_clave_publica_se_rechaza_y_el_resto_pasa(base: str) -> None:
    sign = _llave(
        purpose="sign", algorithm="Ed25519", data_class="audit.signature_prueba", public_key=None
    )
    sign_con = dict(sign, id=uuid4(), public_key="A" * 43 + "=")
    cifrado_sin = _llave(public_key=None)
    cifrado_con = _llave(data_class="test.cero_veintiuno_b", public_key="x")
    estados = resultados(
        base,
        [
            [_paso_llave(sign)],
            [_paso_llave(sign_con)],
            [_paso_llave(cifrado_sin)],
            [_paso_llave(cifrado_con)],
        ],
    )
    # `0025` volvió bidireccional el CHECK: una llave de cifrado con `public_key` tampoco pasa.
    assert [e for e, _ in estados] == [CHECK_VIOLATION, "", "", CHECK_VIOLATION]


def test_las_filas_existentes_de_crypto_keys_quedan_intactas_al_migrar(
    alembic_config: Config, base: str
) -> None:
    """Se siembran dos llaves con la base en `0020`, se sube a `0021` y siguen iguales, con
    `public_key` nula; el resto de la tabla (el conteo) tampoco cambia."""
    clase = "test.cero_veintiuno_datos"
    cifrado, indice = (
        _llave(data_class=clase),
        _llave(data_class=clase, purpose="index", algorithm="HMAC-SHA256"),
    )
    try:
        command.downgrade(alembic_config, PADRE)
        for fila in (cifrado, indice):
            sql, args = _paso_llave(fila)

            async def sembrar(sql: str = sql, args: list[Any] = args) -> None:
                conexion = await asyncpg.connect(_dsn(base))
                try:
                    await conexion.execute(sql, *args)
                finally:
                    await conexion.close()

            asyncio.run(sembrar())
        antes = consultar(
            base,
            "SELECT id, purpose, state, wrapped_material FROM crypto.crypto_keys ORDER BY id",
        )
        command.upgrade(alembic_config, "head")
        despues = consultar(
            base,
            "SELECT id, purpose, state, wrapped_material, public_key FROM crypto.crypto_keys "
            "ORDER BY id",
        )
        assert [tuple(f)[:4] for f in despues] == [tuple(f) for f in antes]
        assert all(f["public_key"] is None for f in despues)
        assert {f["id"] for f in despues} >= {cifrado["id"], indice["id"]}
    finally:
        command.upgrade(alembic_config, "head")
        _ejecutar(
            base,
            disable_user_sql("crypto.crypto_keys"),
            "DELETE FROM crypto.crypto_keys WHERE data_class LIKE 'test.cero_veintiuno%'",
            rearm_always_sql("crypto.crypto_keys"),
        )


# Ciclo ------------------------------------------------------------------------------------------


def _funcion_existe(url: str) -> bool:
    filas = consultar(
        url,
        "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'audit' AND p.proname = $1",
        FUNCION,
    )
    return bool(filas)


def test_downgrade_quita_tabla_triggers_funcion_check_y_columna(
    alembic_config: Config, base: str
) -> None:
    assert existe(base, TABLA) and _funcion_existe(base)
    try:
        command.downgrade(alembic_config, PADRE)
        assert not existe(base, TABLA)
        assert not _funcion_existe(base)
        assert (
            consultar(
                base, "SELECT tgname FROM pg_trigger WHERE tgname = ANY($1::text[])", list(TRIGGERS)
            )
            == []
        )
        assert "public_key" not in columnas(base, "crypto.crypto_keys")
        checks = consultar(
            base,
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'crypto.crypto_keys'::regclass AND pg_get_constraintdef(oid) "
            "LIKE '%public_key%'",
        )
        assert checks == []
        # La cadena y `audit.forbid_mutation()` no se tocan.
        assert consultar(
            base,
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'audit' AND p.proname = 'forbid_mutation'",
        )
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA) and "public_key" in columnas(base, "crypto.crypto_keys")


def test_ciclo_head_base_head(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, "base")
        assert not existe(base, TABLA)
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)
