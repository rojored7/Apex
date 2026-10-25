"""`0008_memberships` (S3-B1, US-084; blueprint B1; D8, D9, S3-D48, S3-D49, S3-D68, L-10).

Padre `0007_plans`. Tabla `memberships.memberships`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`), `member_id`, `plan_id` (sin FK: otros
  esquemas), `agreed_price_cop integer`, `start_date date`, `end_date date`, `classes_total` y
  `classes_remaining` (nulas), `status text`, `cancel_reason`, `cancelled_by` y `cancelled_at`
  (nulas);
- CHECKs (23514): precio > 0, `start_date <= end_date`, los seis estados, clases > 0 y >= 0, el
  par de clases, restantes <= total, la cancelada con motivo, quién y cuándo, y el motivo de 5 a
  500 caracteres;
- `ex_memberships_member_dates` (23P01): `EXCLUDE USING gist (member_id WITH =,
  daterange(start_date, end_date, '[]') WITH &&) WHERE (status <> 'cancelled')`; adyacentes
  (fin el 28, inicio el 29) caben, el mismo día choca, las canceladas y otro socio no cuentan;
- índices `ix_memberships_status_end_date`, `ix_memberships_member_status_start` e
  `ix_memberships_plan_id`;
- `memberships.guard_identity()` (`BEFORE UPDATE FOR EACH ROW`, 23000 con
  `CONSTRAINT = memberships_identity`): no cambian `member_id`, `plan_id`, `agreed_price_cop`,
  `start_date` ni `classes_total`, y una `cancelled` no cambia nada (S3-D48: estado, motivo,
  quién, cuándo y tampoco el fin);
- `memberships.forbid_delete()` (`BEFORE DELETE FOR EACH ROW` y `BEFORE TRUNCATE FOR EACH
  STATEMENT`, 23000 con `CONSTRAINT = memberships_no_delete`);
- los tres triggers con `ENABLE ALWAYS` (S3-D49): `session_replication_role = replica` no los
  salta;
- las dos funciones `plpgsql`, `SECURITY INVOKER` y `SET search_path = pg_catalog` (L-10,
  S3-D68).
El `downgrade` borra triggers, funciones, índices y tabla, y deja el esquema y `btree_gist`.

Nota de diseño de la prueba: `pg_get_functiondef` nunca imprime `SECURITY INVOKER` (es el valor
por defecto; solo imprime `SECURITY DEFINER`). La prueba lo comprueba con `pg_proc.prosecdef =
false` y `search_path` con `proconfig` y el texto de la definición.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REVISION = "0008_memberships"
PADRE = "0007_plans"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
T_ANULADA = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"
EXCLUSION_VIOLATION = "23P01"
INTEGRITY_VIOLATION = "23000"
EXCLUDE = "ex_memberships_member_dates"
IDENTIDAD = "memberships_identity"
SIN_BORRADO = "memberships_no_delete"
TRIGGERS = (
    "memberships_guard_identity",
    "memberships_forbid_delete",
    "memberships_forbid_truncate",
)
FUNCIONES = ("guard_identity", "forbid_delete")

TIMESTAMPTZ = "timestamp with time zone"
COLUMNAS: dict[str, tuple[str, str]] = {
    "id": ("uuid", "NO"),
    "created_at": (TIMESTAMPTZ, "NO"),
    "updated_at": (TIMESTAMPTZ, "NO"),
    "created_by": ("uuid", "NO"),
    "member_id": ("uuid", "NO"),
    "plan_id": ("uuid", "NO"),
    "agreed_price_cop": ("integer", "NO"),
    "start_date": ("date", "NO"),
    "end_date": ("date", "NO"),
    "classes_total": ("integer", "YES"),
    "classes_remaining": ("integer", "YES"),
    "status": ("text", "NO"),
    "cancel_reason": ("text", "YES"),
    "cancelled_by": ("uuid", "YES"),
    "cancelled_at": (TIMESTAMPTZ, "YES"),
}
INDICES = (
    "ix_memberships_status_end_date",
    "ix_memberships_member_status_start",
    "ix_memberships_plan_id",
    EXCLUDE,
)

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
    existe = _consultar(url, "SELECT to_regclass('memberships.memberships') IS NOT NULL AS e")
    esquema = _consultar(
        url, "SELECT count(*) AS n FROM pg_namespace WHERE nspname = 'memberships'"
    )
    funciones = _consultar(
        url,
        "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'memberships' ORDER BY p.proname",
    )
    gist = _consultar(url, "SELECT count(*) AS n FROM pg_extension WHERE extname = 'btree_gist'")
    salida: dict[str, Any] = {
        "existe": existe[0]["e"],
        "esquema": esquema[0]["n"] == 1,
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
            "WHERE table_schema = 'memberships' AND table_name = 'memberships'",
        )
    }
    salida["indices"] = {
        r["indexname"]: r["indexdef"]
        for r in _consultar(
            url,
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'memberships' AND tablename = 'memberships'",
        )
    }
    salida["triggers"] = {
        r["tgname"]: r["estado"]
        for r in _consultar(
            url,
            "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
            "WHERE tgrelid = 'memberships.memberships'::regclass AND NOT tgisinternal",
        )
    }
    return salida


def _fila(**cambios: object) -> dict[str, object]:
    """Fila mínima válida (`active`, 1 a 28 de octubre) de un socio nuevo en cada llamada."""
    fila: dict[str, object] = {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "member_id": uuid4(),
        "plan_id": uuid4(),
        "agreed_price_cop": 120_000,
        "start_date": date(2026, 10, 1),
        "end_date": date(2026, 10, 28),
        "status": "active",
    }
    fila.update(cambios)
    return fila


def _cancelada(**cambios: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "status": "cancelled",
        "cancel_reason": "Se mudó de ciudad",
        "cancelled_by": SYSTEM_USER_ID,
        "cancelled_at": T_ANULADA,
    }
    valores.update(cambios)
    return _fila(**valores)


def _insert(fila: dict[str, object]) -> Paso:
    columnas = list(fila)
    marcas = ", ".join(f"${i}" for i in range(1, len(columnas) + 1))
    sql = f"INSERT INTO memberships.memberships ({', '.join(columnas)}) VALUES ({marcas})"  # noqa: S608
    return sql, [fila[c] for c in columnas]


def _update(id_: object, asignacion: str, *args: Any) -> Paso:
    sql = f"UPDATE memberships.memberships SET {asignacion} WHERE id = $1"  # noqa: S608
    return sql, [id_, *args]


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


def _resultado(url: str, *pasos: Paso) -> tuple[str, str | None]:
    return _resultados(url, [pasos])[0]


def _codigo(url: str, *filas: dict[str, object]) -> str:
    return _resultado(url, *(_insert(f) for f in filas))[0]


# Revisión y forma ----------------------------------------------------------------------------


def test_la_revision_existe_cuelga_de_0007_plans_y_esta_en_la_cadena_de_head(
    alembic_config: Config,
) -> None:
    """Desde S3-B2 `0009_membership_freezes` cuelga de esta revisión (D40): ya no es head, pero
    sigue en la cadena que llega a head (la cabeza única la exige
    `test_migrations.py::test_single_head`)."""
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


def test_indices_y_la_exclusion_por_rango_de_fechas(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    indices = _estado(migrated_database)["indices"]
    assert set(INDICES) <= set(indices), sorted(indices)
    assert "(status, end_date)" in indices["ix_memberships_status_end_date"]
    assert "(member_id, status, start_date)" in indices["ix_memberships_member_status_start"]
    assert "(plan_id)" in indices["ix_memberships_plan_id"]
    exclusion = indices[EXCLUDE]
    assert "USING gist" in exclusion
    assert "daterange(start_date, end_date, '[]'::text)" in exclusion
    assert "WHERE (status <> 'cancelled'::text)" in exclusion
    for nombre in INDICES[:3]:
        assert "UNIQUE" not in indices[nombre], nombre


def test_una_fila_minima_una_tiquetera_y_una_cancelada_entran(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    tiquetera = _fila(classes_total=12, classes_remaining=12, status="pending_payment")
    usada = _fila(classes_total=12, classes_remaining=0, status="expired")
    un_dia = _fila(start_date=date(2026, 10, 21), end_date=date(2026, 10, 21))
    motivo_minimo = _cancelada(cancel_reason="abcde")
    motivo_maximo = _cancelada(cancel_reason="x" * 500)
    filas = [_fila(), tiquetera, usada, un_dia, _cancelada(), motivo_minimo, motivo_maximo]
    assert _resultados(migrated_database, [[_insert(f)] for f in filas]) == [("", None)] * 7


@pytest.mark.parametrize(
    "fila",
    [
        _fila(agreed_price_cop=0),
        _fila(agreed_price_cop=-1),
        _fila(start_date=date(2026, 10, 29), end_date=date(2026, 10, 28)),
        _fila(status="paid"),
        _fila(status="ACTIVE"),
        _fila(classes_total=0, classes_remaining=0),
        _fila(classes_total=5, classes_remaining=-1),
        _fila(classes_total=5, classes_remaining=None),
        _fila(classes_total=None, classes_remaining=3),
        _fila(classes_total=5, classes_remaining=6),
        _fila(status="cancelled"),
        _fila(status="cancelled", cancel_reason="Se mudó", cancelled_by=SYSTEM_USER_ID),
        _fila(status="cancelled", cancel_reason="Se mudó", cancelled_at=T_ANULADA),
        _fila(status="cancelled", cancelled_by=SYSTEM_USER_ID, cancelled_at=T_ANULADA),
        _cancelada(cancel_reason="abcd"),
        _cancelada(cancel_reason="x" * 501),
    ],
    ids=[
        "precio-cero",
        "precio-negativo",
        "fechas-invertidas",
        "estado-ajeno",
        "estado-mayuscula",
        "clases-cero",
        "restantes-negativas",
        "total-sin-restantes",
        "restantes-sin-total",
        "restantes-mayor-que-total",
        "cancelada-sin-nada",
        "cancelada-sin-cuando",
        "cancelada-sin-quien",
        "cancelada-sin-motivo",
        "motivo-de-4",
        "motivo-de-501",
    ],
)
def test_los_checks_rechazan_por_sql_crudo(
    alembic_config: Config, migrated_database: str, fila: dict[str, object]
) -> None:
    _revision_existe(alembic_config)
    assert _codigo(migrated_database, fila) == CHECK_VIOLATION


@pytest.mark.parametrize(
    "columna",
    ["member_id", "plan_id", "agreed_price_cop", "start_date", "end_date", "status", "created_by"],
)
def test_las_obligatorias_no_admiten_nulo(
    alembic_config: Config, migrated_database: str, columna: str
) -> None:
    _revision_existe(alembic_config)
    assert _codigo(migrated_database, _fila(**{columna: None})) == NOT_NULL_VIOLATION


# EXCLUDE (D8) -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("inicio", "fin"),
    [
        (date(2026, 10, 28), date(2026, 11, 27)),
        (date(2026, 10, 1), date(2026, 10, 28)),
        (date(2026, 9, 1), date(2026, 10, 1)),
        (date(2026, 10, 10), date(2026, 10, 12)),
        (date(2026, 9, 1), date(2026, 12, 31)),
    ],
    ids=["mismo-dia-final", "iguales", "mismo-dia-inicial", "contenida", "la-contiene"],
)
def test_dos_rangos_solapados_del_mismo_socio_dan_23p01_con_el_nombre(
    alembic_config: Config, migrated_database: str, inicio: date, fin: date
) -> None:
    _revision_existe(alembic_config)
    socio = uuid4()
    primera = _fila(member_id=socio)
    segunda = _fila(member_id=socio, start_date=inicio, end_date=fin, status="pending_payment")
    assert _resultado(migrated_database, _insert(primera), _insert(segunda)) == (
        EXCLUSION_VIOLATION,
        EXCLUDE,
    )


def test_adyacentes_canceladas_y_otro_socio_no_chocan(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    socio = uuid4()
    vigente = _fila(member_id=socio)
    siguiente = _fila(member_id=socio, start_date=date(2026, 10, 29), end_date=date(2026, 11, 28))
    anterior = _fila(member_id=socio, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30))
    cancelada = _cancelada(
        member_id=socio, start_date=date(2026, 10, 15), end_date=date(2026, 11, 14)
    )
    otro_socio = _fila()
    escenarios = [
        [_insert(vigente), _insert(siguiente), _insert(anterior)],
        [_insert(_fila(member_id=socio)), _insert(cancelada)],
        [_insert(_fila(member_id=socio)), _insert(otro_socio)],
    ]
    assert _resultados(migrated_database, escenarios) == [("", None)] * 3


# guard_identity (D9, S3-D48) -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("asignacion", "valor"),
    [
        ("member_id = $2", uuid4()),
        ("plan_id = $2", uuid4()),
        ("agreed_price_cop = $2", 1),
        ("start_date = $2", date(2026, 10, 2)),
        ("classes_total = $2", 20),
    ],
    ids=["socio", "plan", "precio", "inicio", "clases-totales"],
)
def test_guard_identity_rechaza_cambiar_la_identidad(
    alembic_config: Config, migrated_database: str, asignacion: str, valor: object
) -> None:
    _revision_existe(alembic_config)
    fila = _fila(classes_total=12, classes_remaining=12)
    assert _resultado(migrated_database, _insert(fila), _update(fila["id"], asignacion, valor)) == (
        INTEGRITY_VIOLATION,
        IDENTIDAD,
    )


def test_guard_identity_deja_los_cambios_legitimos(
    alembic_config: Config, migrated_database: str
) -> None:
    """Lo que el plan sí cambia: el fin (congelar, B2), el estado (activar, congelar, revertir),
    las clases restantes (v0.4), anular (B6) y un `UPDATE` sin cambios."""
    _revision_existe(alembic_config)
    fila = _fila(classes_total=12, classes_remaining=12)
    id_ = fila["id"]
    escenarios = [
        [_insert(fila), _update(id_, "end_date = $2", date(2026, 11, 7))],
        [_insert(fila), _update(id_, "status = $2", "frozen")],
        [_insert(fila), _update(id_, "status = $2", "pending_payment")],
        [_insert(fila), _update(id_, "classes_remaining = $2", 11)],
        [
            _insert(fila),
            _update(
                id_,
                "status = 'cancelled', cancel_reason = $2, cancelled_by = $3, cancelled_at = $4",
                "Se lesionó la rodilla",
                SYSTEM_USER_ID,
                T_ANULADA,
            ),
        ],
        [_insert(fila), _update(id_, "status = status")],
    ]
    assert _resultados(migrated_database, escenarios) == [("", None)] * 6


@pytest.mark.parametrize(
    ("asignacion", "valor"),
    [
        ("status = $2", "active"),
        ("status = $2", "pending_payment"),
        ("cancel_reason = $2", "Otro motivo distinto"),
        ("cancelled_by = $2", uuid4()),
        ("cancelled_at = $2", datetime(2026, 10, 22, 15, 0, tzinfo=UTC)),
        ("end_date = $2", date(2026, 11, 30)),
    ],
    ids=["revivir", "a-pendiente", "motivo", "quien", "cuando", "fin"],
)
def test_una_cancelada_no_cambia_nunca(
    alembic_config: Config, migrated_database: str, asignacion: str, valor: object
) -> None:
    _revision_existe(alembic_config)
    fila = _cancelada()
    assert _resultado(migrated_database, _insert(fila), _update(fila["id"], asignacion, valor)) == (
        INTEGRITY_VIOLATION,
        IDENTIDAD,
    )


# forbid_delete (S3-D48) y ENABLE ALWAYS (S3-D49) --------------------------------------------------


def test_delete_y_truncate_se_rechazan_con_memberships_no_delete(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    fila = _fila()
    borrar: Paso = ("DELETE FROM memberships.memberships WHERE id = $1", [fila["id"]])
    # `CASCADE` desde S3-B2: con la FK de `membership_freezes` un `TRUNCATE` simple ya lo rechaza
    # PostgreSQL (0A000) antes de correr el trigger; con `CASCADE` el trigger de esta tabla corre
    # primero y es lo que se prueba.
    vaciar: Paso = ("TRUNCATE memberships.memberships CASCADE", [])
    escenarios = [[_insert(fila), borrar], [_insert(_fila()), vaciar]]
    assert _resultados(migrated_database, escenarios) == [(INTEGRITY_VIOLATION, SIN_BORRADO)] * 2


def test_bajo_replica_los_triggers_siguen_rechazando(
    alembic_config: Config, migrated_database: str
) -> None:
    """M-6: con `session_replication_role = replica` un trigger `ENABLE` (origen) no corre; uno
    `ENABLE ALWAYS` sí."""
    _revision_existe(alembic_config)
    fila = _fila()
    replica: Paso = ("SET LOCAL session_replication_role = replica", [])
    borrar: Paso = ("DELETE FROM memberships.memberships WHERE id = $1", [fila["id"]])
    escenarios = [
        [_insert(fila), replica, _update(fila["id"], "agreed_price_cop = $2", 1)],
        [_insert(fila), replica, borrar],
    ]
    assert _resultados(migrated_database, escenarios) == [
        (INTEGRITY_VIOLATION, IDENTIDAD),
        (INTEGRITY_VIOLATION, SIN_BORRADO),
    ]


def test_los_tres_triggers_estan_enable_always(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    assert _estado(migrated_database)["triggers"] == dict.fromkeys(TRIGGERS, "A")


def test_las_funciones_son_plpgsql_security_invoker_con_search_path_fijo(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    filas = _consultar(
        migrated_database,
        "SELECT p.proname, p.prosecdef, p.proconfig, l.lanname, pg_get_functiondef(p.oid) AS def "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "JOIN pg_language l ON l.oid = p.prolang "
        "WHERE n.nspname = 'memberships' AND p.proname = ANY($1::text[]) ORDER BY p.proname",
        list(FUNCIONES),
    )
    assert [f["proname"] for f in filas] == sorted(FUNCIONES)
    for funcion in filas:
        assert funcion["prosecdef"] is False, funcion["proname"]
        assert funcion["lanname"] == "plpgsql", funcion["proname"]
        assert list(funcion["proconfig"] or []) == ["search_path=pg_catalog"], funcion["proname"]
        assert "search_path" in funcion["def"] and "SECURITY DEFINER" not in funcion["def"]


# Ciclo ------------------------------------------------------------------------------------------


def test_ciclo_de_0008(alembic_config: Config, migrated_database: str) -> None:
    _revision_existe(alembic_config)
    command.downgrade(alembic_config, PADRE)
    assert _estado(migrated_database) == {
        "existe": False,
        "esquema": True,
        "funciones": [],
        "btree_gist": True,
    }
    command.upgrade(alembic_config, "head")
    estado = _estado(migrated_database)
    assert estado["existe"] is True
    # Desde S3-B2 head trae también la función de `0009` en el mismo esquema.
    assert set(FUNCIONES) <= set(estado["funciones"])
    assert estado["triggers"] == dict.fromkeys(TRIGGERS, "A")
