"""`0009_membership_freezes` (S3-B2, US-089; blueprint B2; D14, S3-D48, S3-D49, M-5, L-10).

Padre `0008_memberships`. Tabla `memberships.membership_freezes`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`), `membership_id uuid NOT NULL` con FK a
  `memberships.memberships(id)` (mismo esquema), `frozen_from date`, `frozen_to date` y
  `days integer`, todas obligatorias;
- CHECKs (23514, la convención les antepone `ck_membership_freezes_`): `dates_ordered`
  (`frozen_from <= frozen_to`) y `days_match` (`days = (frozen_to - frozen_from) + 1`, RN-07);
- `ex_membership_freezes_dates` (23P01): `EXCLUDE USING gist (membership_id WITH =,
  daterange(frozen_from, frozen_to, '[]') WITH &&)`; adyacentes caben, el mismo día choca, otra
  membresía no cuenta;
- índice `ix_membership_freezes_membership (membership_id)`;
- append-only (S3-D48, M-5): `memberships.forbid_freeze_mutation()` con los triggers
  `membership_freezes_append_only` (`BEFORE UPDATE OR DELETE FOR EACH ROW`) y
  `membership_freezes_forbid_truncate` (`BEFORE TRUNCATE FOR EACH STATEMENT`); los tres caminos
  dan 23000 con `CONSTRAINT = membership_freezes_append_only`, también bajo
  `session_replication_role = replica` (los dos triggers con `ENABLE ALWAYS`, S3-D49);
- la función es `plpgsql`, `SECURITY INVOKER` y `SET search_path = pg_catalog` (L-10; por catálogo:
  `prosecdef = false`, `lanname` y `proconfig`, criterio de S3-B1).
El `downgrade` borra triggers, función, índice y tabla, y deja intactas `memberships.memberships`,
sus dos funciones, el esquema y `btree_gist`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REVISION = "0009_membership_freezes"
PADRE = "0008_memberships"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"
EXCLUSION_VIOLATION = "23P01"
INTEGRITY_VIOLATION = "23000"
FOREIGN_KEY_VIOLATION = "23503"
EXCLUDE = "ex_membership_freezes_dates"
SOLO_AGREGAR = "membership_freezes_append_only"
CHECK_ORDEN = "ck_membership_freezes_dates_ordered"
CHECK_DIAS = "ck_membership_freezes_days_match"
INDICE = "ix_membership_freezes_membership"
TRIGGERS = ("membership_freezes_append_only", "membership_freezes_forbid_truncate")
FUNCION = "forbid_freeze_mutation"
FUNCIONES_DE_0008 = ("forbid_delete", "guard_identity")

TIMESTAMPTZ = "timestamp with time zone"
COLUMNAS: dict[str, tuple[str, str]] = {
    "id": ("uuid", "NO"),
    "created_at": (TIMESTAMPTZ, "NO"),
    "updated_at": (TIMESTAMPTZ, "NO"),
    "created_by": ("uuid", "NO"),
    "membership_id": ("uuid", "NO"),
    "frozen_from": ("date", "NO"),
    "frozen_to": ("date", "NO"),
    "days": ("integer", "NO"),
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


def _estado(url: str) -> dict[str, Any]:
    existe = _consultar(
        url, "SELECT to_regclass('memberships.membership_freezes') IS NOT NULL AS e"
    )
    membresias = _consultar(url, "SELECT to_regclass('memberships.memberships') IS NOT NULL AS e")
    funciones = _consultar(
        url,
        "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'memberships' ORDER BY p.proname",
    )
    gist = _consultar(url, "SELECT count(*) AS n FROM pg_extension WHERE extname = 'btree_gist'")
    salida: dict[str, Any] = {
        "existe": existe[0]["e"],
        "membresias": membresias[0]["e"],
        "funciones": [f["proname"] for f in funciones],
        "btree_gist": gist[0]["n"] == 1,
    }
    if not salida["existe"]:
        return salida
    salida["columnas"] = {
        r["column_name"]: (r["data_type"], r["is_nullable"])
        for r in _consultar(
            url,
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'memberships' AND table_name = 'membership_freezes'",
        )
    }
    salida["indices"] = {
        r["indexname"]: r["indexdef"]
        for r in _consultar(
            url,
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'memberships' AND tablename = 'membership_freezes'",
        )
    }
    salida["triggers"] = {
        r["tgname"]: r["estado"]
        for r in _consultar(
            url,
            "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
            "WHERE tgrelid = 'memberships.membership_freezes'::regclass AND NOT tgisinternal",
        )
    }
    return salida


def _membresia() -> dict[str, object]:
    """Membresía `active` del 1 al 31 de octubre de un socio nuevo en cada llamada."""
    return {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "member_id": uuid4(),
        "plan_id": uuid4(),
        "agreed_price_cop": 120_000,
        "start_date": date(2026, 10, 1),
        "end_date": date(2026, 10, 31),
        "status": "active",
    }


def _congelacion(membership_id: object, **cambios: object) -> dict[str, object]:
    """Congelación válida del 21 al 30 de octubre (10 días) de la membresía dada."""
    fila: dict[str, object] = {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "membership_id": membership_id,
        "frozen_from": date(2026, 10, 21),
        "frozen_to": date(2026, 10, 30),
        "days": 10,
    }
    fila.update(cambios)
    return fila


def _insert(tabla: str, fila: dict[str, object]) -> Paso:
    columnas = list(fila)
    marcas = ", ".join(f"${i}" for i in range(1, len(columnas) + 1))
    sql = f"INSERT INTO memberships.{tabla} ({', '.join(columnas)}) VALUES ({marcas})"  # noqa: S608
    return sql, [fila[c] for c in columnas]


def _con_membresia(*congelaciones: dict[str, object]) -> list[Paso]:
    """Inserta la membresía de la primera congelación y después las congelaciones."""
    membresia = _membresia()
    pasos = [_insert("memberships", membresia)]
    for congelacion in congelaciones:
        pasos.append(
            _insert("membership_freezes", {**congelacion, "membership_id": membresia["id"]})
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


def _resultado(url: str, pasos: Sequence[Paso]) -> tuple[str, str | None]:
    return _resultados(url, [pasos])[0]


# Revisión y forma ----------------------------------------------------------------------------


def test_la_revision_existe_cuelga_de_0008_memberships_y_esta_en_la_cadena_de_head(
    alembic_config: Config,
) -> None:
    """Desde S3-B3 `0010_payments` cuelga de esta revisión (D40): ya no es head, pero sigue en la
    cadena que llega a head (la cabeza única la exige `test_migrations.py::test_single_head`)."""
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
    assert estado["columnas"] == COLUMNAS


def test_indice_por_membresia_y_exclusion_por_rango_de_fechas(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    indices = _estado(migrated_database)["indices"]
    assert {INDICE, EXCLUDE} <= set(indices), sorted(indices)
    assert "(membership_id)" in indices[INDICE] and "UNIQUE" not in indices[INDICE]
    exclusion = indices[EXCLUDE]
    assert "USING gist" in exclusion
    assert "daterange(frozen_from, frozen_to, '[]'::text)" in exclusion
    assert "WHERE" not in exclusion


def test_la_fk_apunta_a_memberships_del_mismo_esquema(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    filas = _consultar(
        migrated_database,
        "SELECT confrelid::regclass::text AS destino, pg_get_constraintdef(oid) AS def "
        "FROM pg_constraint WHERE conrelid = 'memberships.membership_freezes'::regclass "
        "AND contype = 'f'",
    )
    assert [f["destino"] for f in filas] == ["memberships.memberships"]
    assert "(membership_id)" in filas[0]["def"] and "(id)" in filas[0]["def"]


# Filas válidas, CHECKs, NOT NULL y FK ---------------------------------------------------------


def test_una_congelacion_de_un_dia_y_una_de_diez_entran(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    un_dia = _congelacion(None, frozen_to=date(2026, 10, 21), days=1)
    diez = _congelacion(None)
    escenarios = [_con_membresia(un_dia), _con_membresia(diez)]
    assert _resultados(migrated_database, escenarios) == [("", None)] * 2


@pytest.mark.parametrize(
    ("cambios", "restriccion"),
    [
        (
            {"frozen_from": date(2026, 10, 31), "frozen_to": date(2026, 10, 30), "days": 0},
            CHECK_ORDEN,
        ),
        ({"days": 9}, CHECK_DIAS),
        ({"days": 11}, CHECK_DIAS),
        ({"frozen_to": date(2026, 10, 21), "days": 0}, CHECK_DIAS),
    ],
    ids=["fechas-invertidas", "dias-de-menos", "dias-de-mas", "un-dia-con-cero"],
)
def test_los_checks_rechazan_por_sql_crudo(
    alembic_config: Config,
    migrated_database: str,
    cambios: dict[str, object],
    restriccion: str,
) -> None:
    _revision_existe(alembic_config)
    pasos = _con_membresia(_congelacion(None, **cambios))
    assert _resultado(migrated_database, pasos) == (CHECK_VIOLATION, restriccion)


@pytest.mark.parametrize("columna", ["membership_id", "frozen_from", "frozen_to", "days"])
def test_las_obligatorias_no_admiten_nulo(
    alembic_config: Config, migrated_database: str, columna: str
) -> None:
    _revision_existe(alembic_config)
    membresia = _membresia()
    congelacion = {**_congelacion(membresia["id"]), columna: None}
    pasos = [_insert("memberships", membresia), _insert("membership_freezes", congelacion)]
    assert _resultado(migrated_database, pasos)[0] == NOT_NULL_VIOLATION


def test_una_membresia_inexistente_viola_la_fk(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    pasos = [_insert("membership_freezes", _congelacion(uuid4()))]
    assert _resultado(migrated_database, pasos)[0] == FOREIGN_KEY_VIOLATION


# EXCLUDE ---------------------------------------------------------------------------------------


def test_dos_ventanas_que_se_cruzan_dan_23p01_con_el_nombre(
    alembic_config: Config, migrated_database: str
) -> None:
    """21 a 30 y 30 a 31 de octubre comparten el 30."""
    _revision_existe(alembic_config)
    segunda = _congelacion(
        None, frozen_from=date(2026, 10, 30), frozen_to=date(2026, 10, 31), days=2
    )
    pasos = _con_membresia(_congelacion(None), segunda)
    assert _resultado(migrated_database, pasos) == (EXCLUSION_VIOLATION, EXCLUDE)


def test_adyacentes_y_otra_membresia_no_chocan(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    adyacente = _congelacion(
        None, frozen_from=date(2026, 10, 31), frozen_to=date(2026, 10, 31), days=1
    )
    otra = _membresia()
    misma_ventana_en_otra = [
        *_con_membresia(_congelacion(None)),
        _insert("memberships", otra),
        _insert("membership_freezes", _congelacion(otra["id"])),
    ]
    escenarios = [_con_membresia(_congelacion(None), adyacente), misma_ventana_en_otra]
    assert _resultados(migrated_database, escenarios) == [("", None)] * 2


# Append-only (S3-D48, M-5) y ENABLE ALWAYS (S3-D49) -----------------------------------------------


def _con_una_congelacion() -> tuple[list[Paso], object]:
    pasos = _con_membresia(_congelacion(None))
    congelacion_id = pasos[1][1][0]  # `id` es la primera columna de la congelación
    return pasos, congelacion_id


@pytest.mark.parametrize(
    "mutacion",
    [
        "UPDATE memberships.membership_freezes SET days = 1 WHERE id = $1",
        "UPDATE memberships.membership_freezes SET frozen_to = frozen_to WHERE id = $1",
        "DELETE FROM memberships.membership_freezes WHERE id = $1",
    ],
    ids=["cambiar-dias", "update-sin-cambios", "borrar"],
)
@pytest.mark.parametrize("replica", [False, True], ids=["origen", "replica"])
def test_update_y_delete_se_rechazan_tambien_bajo_replica(
    alembic_config: Config, migrated_database: str, mutacion: str, replica: bool
) -> None:
    _revision_existe(alembic_config)
    pasos, congelacion_id = _con_una_congelacion()
    if replica:
        pasos.append(("SET LOCAL session_replication_role = replica", []))
    pasos.append((mutacion, [congelacion_id]))
    assert _resultado(migrated_database, pasos) == (INTEGRITY_VIOLATION, SOLO_AGREGAR)


@pytest.mark.parametrize("replica", [False, True], ids=["origen", "replica"])
def test_vaciar_la_tabla_se_rechaza_tambien_bajo_replica(
    alembic_config: Config, migrated_database: str, replica: bool
) -> None:
    _revision_existe(alembic_config)
    pasos, _ = _con_una_congelacion()
    if replica:
        pasos.append(("SET LOCAL session_replication_role = replica", []))
    pasos.append(("TRUNCATE memberships.membership_freezes", []))
    assert _resultado(migrated_database, pasos) == (INTEGRITY_VIOLATION, SOLO_AGREGAR)


def test_los_dos_triggers_estan_enable_always(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    assert _estado(migrated_database)["triggers"] == dict.fromkeys(TRIGGERS, "A")


def test_los_triggers_cubren_update_delete_por_fila_y_el_vaciado_por_sentencia(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    filas = _consultar(
        migrated_database,
        "SELECT tgname, pg_get_triggerdef(oid) AS def FROM pg_trigger "
        "WHERE tgrelid = 'memberships.membership_freezes'::regclass AND NOT tgisinternal",
    )
    definiciones = {f["tgname"]: f["def"] for f in filas}
    solo_agregar = definiciones["membership_freezes_append_only"]
    # PostgreSQL reescribe el orden de los eventos (`BEFORE DELETE OR UPDATE`).
    eventos = solo_agregar.split(" ON ")[0]
    assert "BEFORE" in eventos and "UPDATE" in eventos and "DELETE" in eventos
    assert "TRUNCATE" not in eventos and "FOR EACH ROW" in solo_agregar
    vaciado = definiciones["membership_freezes_forbid_truncate"]
    assert "BEFORE TRUNCATE" in vaciado and "FOR EACH STATEMENT" in vaciado
    for definicion in definiciones.values():
        assert f"memberships.{FUNCION}()" in definicion


def test_la_funcion_es_plpgsql_security_invoker_con_search_path_fijo(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    filas = _consultar(
        migrated_database,
        "SELECT p.prosecdef, p.proconfig, l.lanname, pg_get_functiondef(p.oid) AS def "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "JOIN pg_language l ON l.oid = p.prolang "
        "WHERE n.nspname = 'memberships' AND p.proname = $1",
        FUNCION,
    )
    assert len(filas) == 1
    funcion = filas[0]
    assert funcion["prosecdef"] is False
    assert funcion["lanname"] == "plpgsql"
    assert list(funcion["proconfig"] or []) == ["search_path=pg_catalog"]
    assert "search_path" in funcion["def"] and "SECURITY DEFINER" not in funcion["def"]
    assert SOLO_AGREGAR in funcion["def"]


# Ciclo ------------------------------------------------------------------------------------------


def test_ciclo_de_0009(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    command.downgrade(alembic_config, PADRE)
    assert _estado(migrated_database) == {
        "existe": False,
        "membresias": True,
        "funciones": sorted(FUNCIONES_DE_0008),
        "btree_gist": True,
    }
    command.upgrade(alembic_config, "head")
    estado = _estado(migrated_database)
    assert estado["existe"] is True
    assert estado["columnas"] == COLUMNAS
    assert sorted(estado["funciones"]) == sorted((*FUNCIONES_DE_0008, FUNCION))
    assert estado["triggers"] == dict.fromkeys(TRIGGERS, "A")
