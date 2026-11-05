"""`0016_member_channel_preferences` (S5-B5, US-123; S5-D31, S5-D34). # Rojo B5

Padre `0015_crypto_provider_migration`; desde S5-B6 está en la cadena de head. Tabla
`members.member_channel_preferences`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`), `member_id uuid NOT NULL` con FK a
  `members.members(id)` `ON DELETE RESTRICT` (el borrado de socios es lógico), `channel text` y
  `active boolean`, todas obligatorias;
- CHECK `ck_member_channel_preferences_channel` (23514): `channel IN ('email', 'whatsapp_link')`;
- único `(member_id, channel)` (23505);
- sin triggers (tabla de datos vivos, se actualiza con upsert).
El `downgrade` borra la tabla y deja intacta `members.members`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REVISION = "0016_member_channel_preferences"
PADRE = "0015_crypto_provider_migration"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
CHECK_VIOLATION = "23514"
UNIQUE_VIOLATION = "23505"
NOT_NULL_VIOLATION = "23502"
FOREIGN_KEY_VIOLATION = "23503"
TABLA = "members.member_channel_preferences"
CHECK_CANAL = "ck_member_channel_preferences_channel"
UNICO = "uq_member_channel_preferences_member_id_channel"
TIMESTAMPTZ = "timestamp with time zone"
COLUMNAS: dict[str, tuple[str, str]] = {
    "id": ("uuid", "NO"),
    "created_at": (TIMESTAMPTZ, "NO"),
    "updated_at": (TIMESTAMPTZ, "NO"),
    "created_by": ("uuid", "NO"),
    "member_id": ("uuid", "NO"),
    "channel": ("text", "NO"),
    "active": ("boolean", "NO"),
}

Paso = tuple[str, Sequence[Any]]


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


def _existe(url: str) -> bool:
    return bool(_consultar(url, "SELECT to_regclass($1) IS NOT NULL AS e", TABLA)[0]["e"])


def _columnas(url: str) -> dict[str, tuple[str, str]]:
    return {
        r["column_name"]: (r["data_type"], r["is_nullable"])
        for r in _consultar(
            url,
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'members' AND table_name = 'member_channel_preferences'",
        )
    }


def _socio() -> dict[str, object]:
    """Socio mínimo válido (columnas obligatorias de `members.members`, sin campos cifrados)."""
    return {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "first_name": "Ana",
        "last_name": "Prueba",
        "document": "apx1.k.A256GCM.n.c",
        "document_idx": uuid4().hex,
    }


def _preferencia(member_id: object, **cambios: object) -> dict[str, object]:
    fila: dict[str, object] = {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "member_id": member_id,
        "channel": "email",
        "active": True,
    }
    fila.update(cambios)
    return fila


def _insert(tabla: str, fila: dict[str, object]) -> Paso:
    columnas = list(fila)
    marcas = ", ".join(f"${i}" for i in range(1, len(columnas) + 1))
    sql = f"INSERT INTO members.{tabla} ({', '.join(columnas)}) VALUES ({marcas})"  # noqa: S608
    return sql, [fila[c] for c in columnas]


def _con_socio(*preferencias: dict[str, object]) -> list[Paso]:
    socio = _socio()
    pasos = [_insert("members", socio)]
    for preferencia in preferencias:
        pasos.append(
            _insert("member_channel_preferences", {**preferencia, "member_id": socio["id"]})
        )
    return pasos


def _resultados(url: str, escenarios: Sequence[Sequence[Paso]]) -> list[tuple[str, str | None]]:
    """Cada escenario corre en una transacción que siempre se revierte; da `(sqlstate,
    constraint_name)` del primer error, o `("", None)` si todos sus pasos entraron."""

    async def correr() -> list[tuple[str, str | None]]:
        conexion = await asyncpg.connect(_dsn(url))
        salida: list[tuple[str, str | None]] = []
        try:
            for pasos in escenarios:
                transaccion = conexion.transaction()
                await transaccion.start()
                try:
                    for sql, args in pasos:
                        await conexion.execute(sql, *args)
                except asyncpg.PostgresError as error:
                    salida.append((str(error.sqlstate), getattr(error, "constraint_name", None)))
                else:
                    salida.append(("", None))
                finally:
                    await transaccion.rollback()
            return salida
        finally:
            await conexion.close()

    return asyncio.run(correr())


# Revisión y forma ------------------------------------------------------------------------------


def test_la_revision_existe_cuelga_de_0015_y_esta_en_la_cadena_de_head(
    alembic_config: Config,
) -> None:
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    cadena = {r.revision for r in scripts.walk_revisions("base", "heads")}
    assert (
        REVISION in cadena
    )  # desde S5-B6 (P-MIG 9) ya no es head: la cabeza única la exige test_migrations


def test_columnas_exactas_con_tipo_y_nulabilidad(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    assert _columnas(migrated_database) == COLUMNAS


def test_la_fk_apunta_a_members_con_on_delete_restrict(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    filas = _consultar(
        migrated_database,
        "SELECT confrelid::regclass::text AS destino, confdeltype::text AS borrado, "
        "pg_get_constraintdef(oid) AS def FROM pg_constraint "
        "WHERE conrelid = to_regclass($1) AND contype = 'f'",
        TABLA,
    )
    assert [f["destino"] for f in filas] == ["members.members"]
    assert filas[0]["borrado"] == "r", "ON DELETE RESTRICT (el borrado de socios es lógico)"
    assert "(member_id)" in filas[0]["def"] and "(id)" in filas[0]["def"]


def test_la_tabla_no_tiene_triggers_de_usuario(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    filas = _consultar(
        migrated_database,
        "SELECT tgname FROM pg_trigger WHERE tgrelid = to_regclass($1) AND NOT tgisinternal",
        TABLA,
    )
    assert [f["tgname"] for f in filas] == []


# Filas válidas, CHECK, único, NOT NULL y FK -------------------------------------------------------


def test_los_dos_canales_con_active_verdadero_y_falso_entran(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    escenarios = [
        _con_socio(_preferencia(None, channel="email", active=True)),
        _con_socio(_preferencia(None, channel="whatsapp_link", active=False)),
        _con_socio(
            _preferencia(None, channel="email", active=False),
            _preferencia(None, channel="whatsapp_link", active=True),
        ),
    ]
    assert _resultados(migrated_database, escenarios) == [("", None)] * 3


@pytest.mark.parametrize("canal", ["sms", "telegram", "EMAIL", "", "whatsapp"])
def test_un_canal_fuera_de_la_lista_viola_el_check(
    alembic_config: Config, migrated_database: str, canal: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_socio(_preferencia(None, channel=canal))
    assert _resultados(migrated_database, [pasos]) == [(CHECK_VIOLATION, CHECK_CANAL)]


def test_el_mismo_socio_y_canal_dos_veces_viola_el_unico(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_socio(_preferencia(None), _preferencia(None, active=False))
    assert _resultados(migrated_database, [pasos]) == [(UNIQUE_VIOLATION, UNICO)]


def test_el_mismo_canal_en_otro_socio_no_choca(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    otro = _socio()
    pasos = [
        *_con_socio(_preferencia(None)),
        _insert("members", otro),
        _insert("member_channel_preferences", _preferencia(otro["id"])),
    ]
    assert _resultados(migrated_database, [pasos]) == [("", None)]


@pytest.mark.parametrize("columna", ["member_id", "channel", "active"])
def test_las_obligatorias_no_admiten_nulo(
    alembic_config: Config, migrated_database: str, columna: str
) -> None:
    _revision_existe(alembic_config)
    socio = _socio()
    fila = {**_preferencia(socio["id"]), columna: None}
    pasos = [_insert("members", socio), _insert("member_channel_preferences", fila)]
    assert _resultados(migrated_database, [pasos])[0][0] == NOT_NULL_VIOLATION


def test_un_socio_inexistente_viola_la_fk(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    pasos = [_insert("member_channel_preferences", _preferencia(uuid4()))]
    assert _resultados(migrated_database, [pasos])[0][0] == FOREIGN_KEY_VIOLATION


def test_borrar_un_socio_con_preferencias_se_rechaza_por_restrict(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_socio(_preferencia(None))
    socio_id = pasos[0][1][0]
    pasos.append(("DELETE FROM members.members WHERE id = $1", [socio_id]))
    assert _resultados(migrated_database, [pasos])[0][0] == FOREIGN_KEY_VIOLATION


# Ciclo ------------------------------------------------------------------------------------------


def test_ciclo_head_base_head_de_0016(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    assert _existe(migrated_database) is True
    command.downgrade(alembic_config, PADRE)
    try:
        assert _existe(migrated_database) is False
        socios = _consultar(migrated_database, "SELECT to_regclass('members.members') AS t")
        assert socios[0]["t"] == "members.members", "el downgrade no toca `members.members`"
    finally:
        command.upgrade(alembic_config, "head")
    assert _existe(migrated_database) is True
    assert _columnas(migrated_database) == COLUMNAS
