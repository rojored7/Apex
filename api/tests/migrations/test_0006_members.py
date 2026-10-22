"""`0006_members` (S2-B7, US-069; S2-D16, M-4, M-5, N-02; blueprint B7).

Padre `0005b_auth_security`. Tabla `members.members`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`) y `deleted_at`;
- en claro: `first_name`, `last_name` (no nulos), `sex` (nulo), `status` (default `'active'`),
  `document_type` (default `'CC'`), `data_consent_at` y `data_consent_version` (nulos);
- cifradas (`text`): `document` (no nula), `phone`, `email`, `birth_date`, `emergency_contact`;
- índices ciegos: `document_idx` (no nulo), `phone_idx`, `email_idx`;
- sin `notes` (M-5) y sin columnas `*_hint` (N-02);
- CHECKs: sexo, estado, tipo de documento, nombres no vacíos, cada blob `apx1.%` (un valor en
  claro se rechaza) y los pares `(phone IS NULL) = (phone_idx IS NULL)` y el de `email`;
- único parcial `uq_members_document_idx_alive` (un socio dado de baja libera el documento) e
  índices `ix_members_phone_idx`, `ix_members_email_idx` y `ix_members_alive_last_name`.
El `downgrade` borra la tabla y deja el esquema `members` (lo crea `0001`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REVISION = "0006_members"
PADRE = "0005b_auth_security"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
T_BAJA = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
BLOB = "apx1.11111111-2222-3333-4444-555555555555.A256GCM.bm9uY2U.Y2lmcmFkbw"
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"
UNIQUE_VIOLATION = "23505"

TIMESTAMPTZ = "timestamp with time zone"
COLUMNAS: dict[str, tuple[str, str]] = {
    "id": ("uuid", "NO"),
    "created_at": (TIMESTAMPTZ, "NO"),
    "updated_at": (TIMESTAMPTZ, "NO"),
    "created_by": ("uuid", "NO"),
    "deleted_at": (TIMESTAMPTZ, "YES"),
    "first_name": ("text", "NO"),
    "last_name": ("text", "NO"),
    "sex": ("text", "YES"),
    "status": ("text", "NO"),
    "document_type": ("text", "NO"),
    "data_consent_at": (TIMESTAMPTZ, "YES"),
    "data_consent_version": ("text", "YES"),
    "document": ("text", "NO"),
    "phone": ("text", "YES"),
    "email": ("text", "YES"),
    "birth_date": ("text", "YES"),
    "emergency_contact": ("text", "YES"),
    "document_idx": ("text", "NO"),
    "phone_idx": ("text", "YES"),
    "email_idx": ("text", "YES"),
}
INDICES = (
    "uq_members_document_idx_alive",
    "ix_members_phone_idx",
    "ix_members_email_idx",
    "ix_members_alive_last_name",
)
CONTACTO_EN_CLARO = '{"name": "Rosa", "phone": "3115550199"}'


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


def _estado(url: str) -> dict[str, Any]:
    async def consultar() -> dict[str, Any]:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            existe = await conexion.fetchval("SELECT to_regclass('members.members') IS NOT NULL")
            esquema = await conexion.fetchval(
                "SELECT count(*) FROM pg_namespace WHERE nspname = 'members'"
            )
            if not existe:
                return {"existe": False, "esquema": bool(esquema)}
            columnas = {
                r["column_name"]: (r["data_type"], r["is_nullable"], r["column_default"])
                for r in await conexion.fetch(
                    "SELECT column_name, data_type, is_nullable, column_default "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'members' AND table_name = 'members'"
                )
            }
            indices = {
                r["indexname"]: r["indexdef"]
                for r in await conexion.fetch(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = 'members' AND tablename = 'members'"
                )
            }
            return {
                "existe": True,
                "esquema": bool(esquema),
                "columnas": columnas,
                "indices": indices,
            }
        finally:
            await conexion.close()

    return asyncio.run(consultar())


def _fila(**cambios: object) -> dict[str, object]:
    """Fila mínima válida: blob con forma `apx1.` y un índice distinto en cada llamada."""
    fila: dict[str, object] = {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "first_name": "Ana",
        "last_name": "Ruiz",
        "document": BLOB,
        "document_idx": f"idx-{uuid4().hex}",
    }
    fila.update(cambios)
    return fila


async def _insertar(conexion: asyncpg.Connection, fila: dict[str, object]) -> None:
    columnas = list(fila)
    marcas = ", ".join(f"${i}" for i in range(1, len(columnas) + 1))
    sql = f"INSERT INTO members.members ({', '.join(columnas)}) VALUES ({marcas})"  # noqa: S608
    await conexion.execute(sql, *[fila[c] for c in columnas])


def _codigos(url: str, lotes: Sequence[Sequence[dict[str, object]]]) -> list[str]:
    """Cada lote va en una transacción que siempre se revierte; devuelve el SQLSTATE del primer
    error de cada lote, o "" si todas sus filas entraron."""

    async def correr() -> list[str]:
        conexion = await asyncpg.connect(_dsn(url))
        salida: list[str] = []
        try:
            for lote in lotes:
                transaccion = conexion.transaction()
                await transaccion.start()
                try:
                    for fila in lote:
                        await _insertar(conexion, fila)
                except asyncpg.PostgresError as error:
                    salida.append(str(error.sqlstate))
                else:
                    salida.append("")
                finally:
                    await transaccion.rollback()
            return salida
        finally:
            await conexion.close()

    return asyncio.run(correr())


def _codigo(url: str, *filas: dict[str, object]) -> str:
    return _codigos(url, [filas])[0]


def test_la_revision_existe_cuelga_de_0005b_y_esta_en_la_cadena_de_head(
    alembic_config: Config,
) -> None:
    """Desde S2-B9 `0007_plans` cuelga de esta revisión: ya no es head, pero sigue en la cadena
    que llega a head (la cabeza única la exige `test_migrations.py::test_single_head`)."""
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    cadena = {r.revision for r in scripts.walk_revisions("base", "heads")}
    assert REVISION in cadena


def test_columnas_exactas_con_tipo_y_nulabilidad(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    estado = _estado(migrated_database)
    assert estado["existe"] is True
    assert {c: v[:2] for c, v in estado["columnas"].items()} == COLUMNAS


def test_sin_notes_ni_columnas_hint(alembic_config: Config, migrated_database: str) -> None:
    """M-5: `notes` no existe; N-02: ningún fragmento de un dato cifrado se guarda en claro."""
    _revision_existe(alembic_config)
    columnas = _estado(migrated_database)["columnas"]
    assert "notes" not in columnas
    assert [c for c in columnas if c.endswith("_hint")] == []


def test_defaults_de_estado_tipo_y_fechas(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    columnas = _estado(migrated_database)["columnas"]
    assert "'active'" in (columnas["status"][2] or "")
    assert "'CC'" in (columnas["document_type"][2] or "")
    assert columnas["created_at"][2] == "now()"
    assert columnas["updated_at"][2] == "now()"
    for nula in ("data_consent_at", "data_consent_version", "deleted_at", "sex"):
        assert columnas[nula][2] is None, nula


def test_una_fila_minima_y_una_completa_entran(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    completa = _fila(
        sex="x",
        status="inactive",
        document_type="PA",
        phone=BLOB,
        phone_idx="p",
        email=BLOB,
        email_idx="e",
        birth_date=BLOB,
        emergency_contact=BLOB,
    )
    assert _codigos(migrated_database, [[_fila()], [completa]]) == ["", ""]


@pytest.mark.parametrize(
    "cambios",
    [
        {"sex": "z"},
        {"sex": "F"},
        {"status": "deleted"},
        {"document_type": "NIT"},
        {"first_name": "   "},
        {"last_name": ""},
    ],
    ids=["sexo", "sexo-mayuscula", "estado", "tipo-documento", "nombre-vacio", "apellido-vacio"],
)
def test_los_checks_de_los_valores_en_claro(
    alembic_config: Config, migrated_database: str, cambios: dict[str, object]
) -> None:
    _revision_existe(alembic_config)
    assert _codigo(migrated_database, _fila(**cambios)) == CHECK_VIOLATION


@pytest.mark.parametrize(
    "cambios",
    [
        {"document": "7319582046"},
        {"phone": "+57 300 765 4321", "phone_idx": "p"},
        {"email": "lucia.gomez@correo.co", "email_idx": "e"},
        {"birth_date": "1991-07-23"},
        {"emergency_contact": CONTACTO_EN_CLARO},
    ],
    ids=["document", "phone", "email", "birth_date", "emergency_contact"],
)
def test_un_valor_en_claro_en_una_columna_cifrada_se_rechaza(
    alembic_config: Config, migrated_database: str, cambios: dict[str, object]
) -> None:
    _revision_existe(alembic_config)
    assert _codigo(migrated_database, _fila(**cambios)) == CHECK_VIOLATION


@pytest.mark.parametrize(
    "cambios",
    [{"phone": BLOB}, {"phone_idx": "p"}, {"email": BLOB}, {"email_idx": "e"}],
    ids=["phone-sin-idx", "phone_idx-sin-phone", "email-sin-idx", "email_idx-sin-email"],
)
def test_los_pares_valor_e_indice(
    alembic_config: Config, migrated_database: str, cambios: dict[str, object]
) -> None:
    _revision_existe(alembic_config)
    assert _codigo(migrated_database, _fila(**cambios)) == CHECK_VIOLATION


@pytest.mark.parametrize("columna", ["document", "document_idx", "first_name", "last_name"])
def test_las_obligatorias_no_admiten_nulo(
    alembic_config: Config, migrated_database: str, columna: str
) -> None:
    _revision_existe(alembic_config)
    assert _codigo(migrated_database, _fila(**{columna: None})) == NOT_NULL_VIOLATION


def test_el_documento_es_unico_entre_vivos_y_un_dado_de_baja_lo_libera(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    indice = f"idx-{uuid4().hex}"
    baja = {"document_idx": indice, "deleted_at": T_BAJA}
    codigos = _codigos(
        migrated_database,
        [
            [_fila(document_idx=indice), _fila(document_idx=indice)],
            [_fila(**baja), _fila(document_idx=indice)],
            [_fila(**baja), _fila(**baja)],
        ],
    )
    assert codigos == [UNIQUE_VIOLATION, "", ""]


def test_indices_unico_parcial_y_de_busqueda(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    indices = _estado(migrated_database)["indices"]
    assert set(INDICES) <= set(indices), sorted(indices)
    unico = indices["uq_members_document_idx_alive"]
    assert "UNIQUE" in unico and "(document_idx)" in unico and "deleted_at IS NULL" in unico
    assert "(phone_idx)" in indices["ix_members_phone_idx"]
    assert "(email_idx)" in indices["ix_members_email_idx"]
    alfabetico = indices["ix_members_alive_last_name"]
    assert "(last_name, first_name)" in alfabetico and "deleted_at IS NULL" in alfabetico


def test_ciclo_de_0006(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    command.downgrade(alembic_config, PADRE)
    assert _estado(migrated_database) == {"existe": False, "esquema": True}
    command.upgrade(alembic_config, "head")
    estado = _estado(migrated_database)
    assert estado["existe"] is True
    assert {c: v[:2] for c, v in estado["columnas"].items()} == COLUMNAS
    assert set(INDICES) <= set(estado["indices"])
