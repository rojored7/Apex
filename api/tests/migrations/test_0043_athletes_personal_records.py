"""`0043_athletes_personal_records` (S9-B1, US-180; S9-D8, S9-D18, S9-D31). Rojo B1.

Padre `0042_athletes_body_metrics`. Crea `athletes.personal_records` (sin claves foráneas entre
esquemas, sin columnas cifradas) con:
- CHECK de forma: `rm` exige `movement_id` y `value_g` y prohíbe `benchmark_id` y la marca;
  `benchmark`
  exige `benchmark_id` y `level` y prohíbe `movement_id` y `value_g`; `derived` exige `result_id` y
  `wod_id`, `manual` los prohíbe; `(invalidated_at IS NULL) = (invalidated_reason IS NULL)`;
  `manual_error` solo con `manual`, `superseded` y `voided` solo con `derived`;
  `NOT capped OR (seconds IS NOT NULL AND reps IS NOT NULL)`; rangos de `value_g` y de la marca.
- Seis índices (S9-D8): el único parcial `(result_id, kind)`, los dos de vigentes con la columna
  desnuda `invalidated_at IS NULL` (S8-D50), el de historial y los dos del puerto de S9-D9.
- Cuatro guardas `ENABLE ALWAYS` (`tgenabled = 'A'`), `SECURITY INVOKER` con
  `search_path = pg_catalog`: `BEFORE INSERT` con `invalidated_*` nulos; `BEFORE UPDATE` que solo
  deja las cuatro columnas de invalidación pasar de NULL a valor UNA vez (un invalidado es
  terminal) y `updated_at` sin retroceder; `DELETE` y `TRUNCATE` prohibidos.
Cada escenario corre en una transacción que se revierte. `P0001` es el error de las guardas;
`23514`, el de un CHECK; `23505`, el del índice único.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.migrations._apoyo_notificaciones import (
    SYSTEM_USER_ID,
    Paso,
    columnas,
    consultar,
    existe,
    resultados,
)

REVISION = "0043_athletes_personal_records"
PADRE = "0042_athletes_body_metrics"
TABLA = "athletes.personal_records"
GUARDA = "P0001"
CHECK = "23514"
UNICO = "23505"
OK = ("", None)
TRIGGERS = (
    "personal_records_guard_insert",
    "personal_records_guard_update",
    "personal_records_forbid_delete",
    "personal_records_forbid_truncate",
)
HOY = date(2026, 10, 20)
TSTZ = "timestamp with time zone"


def rm(**cambios: Any) -> dict[str, Any]:
    fila: dict[str, Any] = {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "member_id": uuid4(),
        "kind": "rm",
        "movement_id": uuid4(),
        "value_g": 100_000,
        "achieved_on": HOY,
        "source": "manual",
    }
    fila.update(cambios)
    return fila


def marca(**cambios: Any) -> dict[str, Any]:
    fila: dict[str, Any] = {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "member_id": uuid4(),
        "kind": "benchmark",
        "benchmark_id": uuid4(),
        "level": "rx",
        "seconds": 300,
        "achieved_on": HOY,
        "source": "manual",
    }
    fila.update(cambios)
    return fila


def derivado(**cambios: Any) -> dict[str, Any]:
    """Un RM derivado de un resultado: pide `result_id` y `wod_id`."""
    base = {"source": "derived", "result_id": uuid4(), "wod_id": uuid4()}
    return rm(**{**base, **cambios})


def insertar(fila: dict[str, Any]) -> Paso:
    nombres = list(fila)
    marcas = ", ".join(f"${i}" for i in range(1, len(nombres) + 1))
    sql = f"INSERT INTO {TABLA} ({', '.join(nombres)}) VALUES ({marcas})"  # noqa: S608
    return sql, [fila[c] for c in nombres]


def actualizar(id_: UUID, asignacion: str, *args: Any) -> Paso:
    return f"UPDATE {TABLA} SET {asignacion} WHERE id = $1", [id_, *args]  # noqa: S608


def invalidar(id_: UUID, razon: str = "manual_error", *, por_resultado: bool = False) -> Paso:
    """La invalidación completa que la guarda permite: las columnas pasan de NULL a valor."""
    extra = ", invalidated_by_result_id = $4" if por_resultado else ""
    args: list[Any] = [SYSTEM_USER_ID, razon]
    if por_resultado:
        args.append(uuid4())
    return (
        f"UPDATE {TABLA} SET invalidated_at = clock_timestamp(), invalidated_by = $2, "  # noqa: S608
        f"invalidated_reason = $3{extra}, updated_at = clock_timestamp() WHERE id = $1",
        [id_, *args],
    )


def _correr(url: str, *escenarios: Sequence[Paso]) -> list[tuple[str, str | None]]:
    return resultados(url, [list(e) for e in escenarios])


def _uno(url: str, *pasos: Paso) -> tuple[str, str | None]:
    return _correr(url, pasos)[0]


def _revision_existe(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> str:
    _revision_existe(alembic_config)
    return migrated_database


# Cadena, esquema, columnas ----------------------------------------------------------------------


def test_cuelga_de_0042_y_esta_en_la_cadena_de_head(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_crea_la_tabla_en_el_esquema_athletes(base: str) -> None:
    assert existe(base, TABLA)


def test_las_columnas_tipos_y_nulidad_de_s9_d8(base: str) -> None:
    assert columnas(base, TABLA) == {
        "id": ("uuid", "NO"),
        "created_at": (TSTZ, "NO"),
        "updated_at": (TSTZ, "NO"),
        "created_by": ("uuid", "NO"),
        "member_id": ("uuid", "NO"),
        "kind": ("text", "NO"),
        "movement_id": ("uuid", "YES"),
        "benchmark_id": ("uuid", "YES"),
        "wod_id": ("uuid", "YES"),
        "value_g": ("integer", "YES"),
        "level": ("text", "YES"),
        "seconds": ("integer", "YES"),
        "rounds": ("integer", "YES"),
        "reps": ("integer", "YES"),
        "load_g": ("integer", "YES"),
        "capped": ("boolean", "NO"),
        "achieved_on": ("date", "NO"),
        "source": ("text", "NO"),
        "result_id": ("uuid", "YES"),
        "invalidated_at": (TSTZ, "YES"),
        "invalidated_reason": ("text", "YES"),
        "invalidated_by": ("uuid", "YES"),
        "invalidated_by_result_id": ("uuid", "YES"),
    }


def test_no_hay_claves_foraneas_entre_esquemas(base: str) -> None:
    assert existe(base, TABLA)
    filas = consultar(
        base,
        "SELECT conname FROM pg_constraint WHERE conrelid = to_regclass($1) AND contype = 'f'",
        TABLA,
    )
    assert filas == []


def test_capped_nace_en_false_por_defecto(base: str) -> None:
    fila = marca()
    paso_lectura = (f"SELECT 1 FROM {TABLA} WHERE id = $1 AND capped IS NOT TRUE", [fila["id"]])  # noqa: S608
    assert _uno(base, insertar(fila), paso_lectura) == OK
    defecto = consultar(
        base,
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_schema = 'athletes' AND table_name = 'personal_records' "
        "AND column_name = 'capped'",
    )
    assert defecto and "false" in str(defecto[0]["column_default"])


# CHECK de forma ---------------------------------------------------------------------------------


def test_filas_validas_de_cada_forma_pasan(base: str) -> None:
    salidas = _correr(
        base,
        [insertar(rm())],
        [insertar(marca())],
        [insertar(derivado())],
        [insertar(marca(source="derived", result_id=uuid4(), wod_id=uuid4()))],
        [insertar(marca(level="rx_plus"))],
        [insertar(marca(level="scaled"))],
        [
            insertar(
                marca(
                    source="derived",
                    result_id=uuid4(),
                    wod_id=uuid4(),
                    capped=True,
                    seconds=600,
                    reps=40,
                )
            )
        ],
        [insertar(marca(seconds=None, rounds=5, reps=12))],
        [insertar(marca(seconds=None, load_g=100_000))],
    )
    assert salidas == [OK] * 9, salidas


@pytest.mark.parametrize("faltante", ["movement_id", "value_g"])
def test_rm_exige_movimiento_y_valor(base: str, faltante: str) -> None:
    assert _uno(base, insertar(rm(**{faltante: None})))[0] == CHECK


@pytest.mark.parametrize(
    ("columna", "valor"),
    [
        ("benchmark_id", uuid4()),
        ("level", "rx"),
        ("seconds", 300),
        ("rounds", 3),
        ("reps", 10),
        ("load_g", 5_000),
    ],
)
def test_rm_prohibe_los_campos_de_benchmark_y_la_marca(base: str, columna: str, valor: Any) -> None:
    assert _uno(base, insertar(rm(**{columna: valor})))[0] == CHECK


@pytest.mark.parametrize("faltante", ["benchmark_id", "level"])
def test_benchmark_exige_id_y_nivel(base: str, faltante: str) -> None:
    assert _uno(base, insertar(marca(**{faltante: None})))[0] == CHECK


@pytest.mark.parametrize(("columna", "valor"), [("movement_id", uuid4()), ("value_g", 5_000)])
def test_benchmark_prohibe_movimiento_y_valor(base: str, columna: str, valor: Any) -> None:
    assert _uno(base, insertar(marca(**{columna: valor})))[0] == CHECK


@pytest.mark.parametrize("kind", ["pr", "RM", "", "benchmarks"])
def test_kind_solo_acepta_rm_o_benchmark(base: str, kind: str) -> None:
    assert _uno(base, insertar(rm(kind=kind)))[0] == CHECK


@pytest.mark.parametrize("fuente", ["auto", "Manual", "", "import"])
def test_source_solo_acepta_manual_o_derived(base: str, fuente: str) -> None:
    assert _uno(base, insertar(rm(source=fuente)))[0] == CHECK


@pytest.mark.parametrize("faltante", ["result_id", "wod_id"])
def test_derived_exige_result_id_y_wod_id(base: str, faltante: str) -> None:
    assert _uno(base, insertar(derivado(**{faltante: None})))[0] == CHECK


@pytest.mark.parametrize("sobrante", ["result_id", "wod_id"])
def test_manual_prohibe_result_id_y_wod_id(base: str, sobrante: str) -> None:
    assert _uno(base, insertar(rm(**{sobrante: uuid4()})))[0] == CHECK


@pytest.mark.parametrize("nivel", ["RX", "elite", "", "rx-plus"])
def test_level_solo_acepta_rx_rx_plus_o_scaled(base: str, nivel: str) -> None:
    assert _uno(base, insertar(marca(level=nivel)))[0] == CHECK


def test_capped_exige_seconds_y_reps(base: str) -> None:
    sin_reps = marca(capped=True, seconds=600)
    sin_seconds = marca(capped=True, seconds=None, reps=40)
    con_ambos = marca(
        source="derived", result_id=uuid4(), wod_id=uuid4(), capped=True, seconds=600, reps=40
    )
    salidas = _correr(base, [insertar(sin_reps)], [insertar(sin_seconds)], [insertar(con_ambos)])
    assert [s[0] for s in salidas] == [CHECK, CHECK, ""], salidas


@pytest.mark.parametrize(
    ("fila", "ok"),
    [
        (rm(value_g=0), False),
        (rm(value_g=1), True),
        (rm(value_g=1_000_000), True),
        (rm(value_g=1_000_001), False),
        (marca(seconds=0), False),
        (marca(seconds=1), True),
        (marca(seconds=86_400), True),
        (marca(seconds=86_401), False),
        (marca(seconds=None, rounds=-1, reps=1), False),
        (marca(seconds=None, rounds=0, reps=0), True),
        (marca(seconds=None, rounds=1_000, reps=100_000), True),
        (marca(seconds=None, rounds=1_001, reps=1), False),
        (marca(seconds=None, rounds=1, reps=100_001), False),
        (marca(seconds=None, load_g=-1), False),
        (marca(seconds=None, load_g=0), True),
        (marca(seconds=None, load_g=1_000_000), True),
        (marca(seconds=None, load_g=1_000_001), False),
    ],
)
def test_rangos_de_value_g_y_de_la_marca(base: str, fila: dict[str, Any], ok: bool) -> None:
    assert _uno(base, insertar(fila))[0] == ("" if ok else CHECK)


# Índices ----------------------------------------------------------------------------------------


def _indexdef(base: str, nombre: str) -> str:
    filas = consultar(
        base,
        "SELECT indexdef FROM pg_indexes WHERE schemaname = 'athletes' "
        "AND tablename = 'personal_records' AND indexname = $1",
        nombre,
    )
    assert len(filas) == 1, f"falta el índice {nombre}"
    return str(filas[0]["indexdef"])


def test_el_indice_unico_parcial_por_resultado_y_tipo(base: str) -> None:
    definicion = _indexdef(base, "uq_personal_records_result_kind")
    assert "UNIQUE" in definicion and "(result_id, kind)" in definicion
    assert "result_id IS NOT NULL" in definicion


def test_un_resultado_da_a_lo_sumo_un_rm_y_un_record_de_benchmark(base: str) -> None:
    resultado, wod, socio = uuid4(), uuid4(), uuid4()
    primero = derivado(member_id=socio, result_id=resultado, wod_id=wod)
    repetido = derivado(member_id=socio, result_id=resultado, wod_id=wod)
    de_benchmark = marca(member_id=socio, source="derived", result_id=resultado, wod_id=wod)
    salidas = _correr(
        base,
        [insertar(primero), insertar(repetido)],
        [insertar(primero), insertar(de_benchmark)],
    )
    assert salidas[0][0] == UNICO, salidas
    assert salidas[1] == OK, salidas


def test_los_manuales_sin_result_id_no_chocan_entre_si(base: str) -> None:
    socio, mov = uuid4(), uuid4()
    uno = rm(member_id=socio, movement_id=mov)
    otro = rm(member_id=socio, movement_id=mov)
    assert _uno(base, insertar(uno), insertar(otro)) == OK


def test_los_indices_de_vigentes_usan_la_columna_desnuda(base: str) -> None:
    for nombre, columnas_, tipo in (
        ("ix_personal_records_rm", "(member_id, movement_id)", "rm"),
        ("ix_personal_records_bench", "(member_id, benchmark_id)", "benchmark"),
    ):
        definicion = _indexdef(base, nombre)
        assert columnas_ in definicion, definicion
        assert f"kind = '{tipo}'" in definicion, definicion
        assert "invalidated_at IS NULL" in definicion, definicion
        assert "= true" not in definicion.lower() and "is true" not in definicion.lower()


def test_el_indice_de_historial_por_socio_y_fecha_descendentes(base: str) -> None:
    definicion = _indexdef(base, "ix_personal_records_member_date")
    assert "(member_id, achieved_on DESC, created_at DESC)" in definicion


@pytest.mark.parametrize(
    ("nombre", "columna"),
    [
        ("ix_personal_records_movement", "movement_id"),
        ("ix_personal_records_benchmark", "benchmark_id"),
    ],
)
def test_los_indices_del_puerto_de_s9_d9(base: str, nombre: str, columna: str) -> None:
    definicion = _indexdef(base, nombre)
    assert f"({columna})" in definicion and f"{columna} IS NOT NULL" in definicion


# Guarda de INSERT -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "columna",
    ["invalidated_at", "invalidated_reason", "invalidated_by", "invalidated_by_result_id"],
)
def test_insert_nace_sin_ninguna_columna_de_invalidacion(base: str, columna: str) -> None:
    valores: dict[str, Any] = {
        "invalidated_at": datetime(2026, 10, 20, 10, 0, tzinfo=UTC),
        "invalidated_reason": "manual_error",
        "invalidated_by": SYSTEM_USER_ID,
        "invalidated_by_result_id": uuid4(),
    }
    salida = _uno(base, insertar(rm(**{columna: valores[columna]})))
    assert salida[0] == GUARDA, (columna, salida)


def test_insert_nace_sin_las_cuatro_a_la_vez_y_la_guarda_manda_sobre_el_check(base: str) -> None:
    fila = rm(
        invalidated_at=datetime(2026, 10, 20, 10, 0, tzinfo=UTC), invalidated_reason="manual_error",
        invalidated_by=SYSTEM_USER_ID,
    )  # fmt: skip
    assert _uno(base, insertar(fila))[0] == GUARDA


# Guarda de UPDATE: invalidar --------------------------------------------------------------------


def test_invalidar_un_manual_pasa_de_null_a_valor_en_el_mismo_update(base: str) -> None:
    fila = rm()
    assert _uno(base, insertar(fila), invalidar(fila["id"], "manual_error")) == OK


def test_invalidar_un_derivado_superseded_con_su_resultado_nuevo_pasa(base: str) -> None:
    fila = derivado()
    paso = invalidar(fila["id"], "superseded", por_resultado=True)
    assert _uno(base, insertar(fila), paso) == OK


def test_solo_superseded_lleva_resultado_nuevo_un_voided_con_el_falla_check(base: str) -> None:
    """S9-D10: anular un resultado no tiene resultado nuevo; solo la corrección lo tiene."""
    fila = derivado()
    paso = invalidar(fila["id"], "voided", por_resultado=True)
    assert _uno(base, insertar(fila), paso)[0] == CHECK


def test_invalidar_un_derivado_sin_resultado_nuevo_pasa(base: str) -> None:
    fila = derivado()
    assert _uno(base, insertar(fila), invalidar(fila["id"], "voided")) == OK


@pytest.mark.parametrize(
    ("origen", "razon"),
    [
        ("derived", "manual_error"),
        ("manual", "superseded"),
        ("manual", "voided"),
    ],
)
def test_la_razon_de_invalidacion_debe_ser_la_del_origen(
    base: str, origen: str, razon: str
) -> None:
    fila = derivado() if origen == "derived" else rm()
    salida = _uno(base, insertar(fila), invalidar(fila["id"], razon))
    assert salida[0] == CHECK, salida


@pytest.mark.parametrize("razon", ["error", "", "SUPERSEDED", "deleted"])
def test_una_razon_fuera_del_catalogo_falla(base: str, razon: str) -> None:
    fila = rm()
    assert _uno(base, insertar(fila), invalidar(fila["id"], razon))[0] in {CHECK, GUARDA}


def test_invalidated_at_e_invalidated_reason_van_juntas(base: str) -> None:
    solo_at = rm()
    solo_razon = rm()
    salidas = _correr(
        base,
        [insertar(solo_at), actualizar(solo_at["id"], "invalidated_at = now()")],
        [
            insertar(solo_razon),
            actualizar(solo_razon["id"], "invalidated_reason = 'manual_error'"),
        ],
    )
    assert all(s[0] in {GUARDA, CHECK} for s in salidas), salidas


def test_un_invalidado_es_terminal_no_se_reinvalida_ni_se_revive_ni_cambia_la_razon(
    base: str,
) -> None:
    fila = rm()
    primero = [insertar(fila), invalidar(fila["id"], "manual_error")]
    volver_a_invalidar = [*primero, invalidar(fila["id"], "manual_error")]
    revivir = [*primero, actualizar(fila["id"], "invalidated_at = NULL, invalidated_reason = NULL")]
    cambiar_razon = [*primero, actualizar(fila["id"], "invalidated_reason = 'manual_error'")]
    cambiar_quien = [*primero, actualizar(fila["id"], "invalidated_by = $2", uuid4())]
    cambiar_fecha = [*primero, actualizar(fila["id"], "invalidated_at = now() + interval '1 day'")]
    salidas = _correr(
        base, volver_a_invalidar, revivir, cambiar_razon, cambiar_quien, cambiar_fecha
    )
    assert [s[0] for s in salidas] == [GUARDA] * 5, salidas


def test_un_derivado_invalidado_no_cambia_su_resultado_nuevo(base: str) -> None:
    fila = derivado()
    paso = invalidar(fila["id"], "superseded", por_resultado=True)
    cambiar = actualizar(fila["id"], "invalidated_by_result_id = $2", uuid4())
    assert _uno(base, insertar(fila), paso, cambiar)[0] == GUARDA


# Guarda de UPDATE: el resto de las columnas -----------------------------------------------------


def test_updated_at_no_retrocede_pero_puede_avanzar_o_quedar_igual(base: str) -> None:
    fila = rm()
    retroceder = actualizar(fila["id"], "updated_at = updated_at - interval '1 day'")
    avanzar = actualizar(fila["id"], "updated_at = updated_at + interval '1 second'")  # L8
    igual = actualizar(fila["id"], "updated_at = updated_at")
    salidas = _correr(
        base,
        [insertar(fila), retroceder],
        [insertar(fila), avanzar],
        [insertar(fila), igual],
    )
    # L8 (revisión de base de datos): `updated_at` solo cambia al invalidar; avanzarlo suelto falla.
    assert salidas == [(GUARDA, None), (GUARDA, None), OK]


@pytest.mark.parametrize(
    ("asignacion", "args", "base_fila"),
    [
        ("id = $2", [uuid4()], "rm"),
        ("member_id = $2", [uuid4()], "rm"),
        ("kind = 'benchmark'", [], "rm"),
        ("movement_id = $2", [uuid4()], "rm"),
        ("benchmark_id = $2", [uuid4()], "benchmark"),
        ("wod_id = $2", [uuid4()], "derived"),
        ("value_g = 200000", [], "rm"),
        ("level = 'scaled'", [], "benchmark"),
        ("seconds = 10", [], "benchmark"),
        ("rounds = 3", [], "benchmark"),
        ("reps = 7", [], "benchmark"),
        ("load_g = 9000", [], "benchmark"),
        ("capped = true", [], "benchmark"),
        ("achieved_on = '2020-01-01'", [], "rm"),
        ("source = 'derived'", [], "rm"),
        ("result_id = $2", [uuid4()], "derived"),
        ("created_by = $2", [uuid4()], "rm"),
        ("created_at = created_at - interval '1 day'", [], "rm"),
    ],
    ids=[
        "id", "member_id", "kind", "movement_id", "benchmark_id", "wod_id", "value_g", "level",
        "seconds", "rounds", "reps", "load_g", "capped", "achieved_on", "source", "result_id",
        "created_by", "created_at",
    ],
)  # fmt: skip
def test_las_columnas_fijas_no_cambian_nunca(
    base: str, asignacion: str, args: list[Any], base_fila: str
) -> None:
    fila = {"rm": rm, "benchmark": marca, "derived": derivado}[base_fila]()
    paso = actualizar(fila["id"], asignacion, *args)
    assert _uno(base, insertar(fila), paso) == (GUARDA, None)


def test_invalidar_y_cambiar_otra_columna_en_el_mismo_update_falla(base: str) -> None:
    fila = rm()
    paso = (
        f"UPDATE {TABLA} SET invalidated_at = now(), invalidated_by = $2, "  # noqa: S608
        "invalidated_reason = 'manual_error', value_g = 1 WHERE id = $1",
        [fila["id"], SYSTEM_USER_ID],
    )
    assert _uno(base, insertar(fila), paso) == (GUARDA, None)


# Sin borrado y guardas siempre activas ----------------------------------------------------------


def test_delete_y_truncate_estan_prohibidos(base: str) -> None:
    fila = rm()
    borrar = (f"DELETE FROM {TABLA} WHERE id = $1", [fila["id"]])  # noqa: S608
    truncar = (f"TRUNCATE {TABLA}", [])
    salidas = _correr(base, [insertar(fila), borrar], [insertar(fila), truncar])
    assert salidas == [(GUARDA, None)] * 2


def test_un_invalidado_tampoco_se_borra(base: str) -> None:
    fila = rm()
    borrar = (f"DELETE FROM {TABLA} WHERE id = $1", [fila["id"]])  # noqa: S608
    assert _uno(base, insertar(fila), invalidar(fila["id"]), borrar) == (GUARDA, None)


def test_bajo_replica_las_guardas_siguen_corriendo(base: str) -> None:
    """`ENABLE ALWAYS`: `session_replication_role = replica` no las salta."""
    fila = rm()
    replica = ("SET LOCAL session_replication_role = replica", [])
    borrar = (f"DELETE FROM {TABLA} WHERE id = $1", [fila["id"]])  # noqa: S608
    cambiar = actualizar(fila["id"], "achieved_on = '2020-01-01'")
    salidas = _correr(
        base,
        [insertar(fila), replica, borrar],
        [insertar(fila), replica, cambiar],
    )
    assert salidas == [(GUARDA, None)] * 2


def test_los_cuatro_triggers_existen_y_estan_en_always(base: str) -> None:
    filas = consultar(
        base,
        "SELECT t.tgname, t.tgenabled::text AS estado FROM pg_trigger t "
        "WHERE NOT t.tgisinternal AND t.tgrelid = to_regclass($1) ORDER BY t.tgname",
        TABLA,
    )
    assert {f["tgname"]: f["estado"] for f in filas} == dict.fromkeys(TRIGGERS, "A")


def test_las_funciones_son_security_invoker_con_search_path_fijo(base: str) -> None:
    filas = consultar(
        base,
        "SELECT p.proname, p.prosecdef, p.proconfig FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'athletes'",
    )
    nombres = {f["proname"] for f in filas}
    assert {
        "forbid_mutation",
        "guard_personal_records_insert",
        "guard_personal_records_update",
    } <= nombres, nombres
    for fila in filas:
        assert fila["prosecdef"] is False, fila["proname"]
        assert "search_path=pg_catalog" in (fila["proconfig"] or []), fila["proname"]


# Downgrade --------------------------------------------------------------------------------------


def test_downgrade_borra_la_tabla_y_deja_intacto_lo_de_0042(
    alembic_config: Config, base: str
) -> None:
    """`athletes.forbid_mutation()` es de `0042` (la usa `body_metrics`): el downgrade de `0043` no
    la borra ni toca el esquema; el `upgrade` posterior deja los cuatro triggers en `A`."""
    try:
        command.downgrade(alembic_config, PADRE)
        assert not existe(base, TABLA)
        assert existe(base, "athletes.body_metrics")
        funcion = consultar(
            base,
            "SELECT 1 AS e FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'athletes' AND p.proname = 'forbid_mutation'",
        )
        assert len(funcion) == 1
        sobrantes = consultar(
            base,
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'athletes' AND p.proname LIKE '%personal_records%'",
        )
        assert sobrantes == []
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)
    estados = consultar(
        base,
        "SELECT count(*) AS n FROM pg_trigger WHERE NOT tgisinternal "
        "AND tgrelid = to_regclass($1) AND tgenabled = 'A'",
        TABLA,
    )
    assert estados[0]["n"] == len(TRIGGERS)


# Revisiones de B1 (M2, M3, L4, L6, L7 de la base y L4 de seguridad) -------------------------


def test_created_at_y_updated_at_nacen_con_clock_timestamp_y_en_orden(base: str) -> None:
    defectos = consultar(
        base,
        "SELECT column_name, column_default FROM information_schema.columns "
        "WHERE table_schema = 'athletes' AND table_name = 'personal_records' "
        "AND column_name IN ('created_at', 'updated_at')",
    )
    assert {f["column_name"]: str(f["column_default"]) for f in defectos} == {
        "created_at": "clock_timestamp()",
        "updated_at": "clock_timestamp()",
    }
    fila = rm()
    lectura = (f"SELECT 1 FROM {TABLA} WHERE id = $1 AND updated_at >= created_at", [fila["id"]])  # noqa: S608
    assert _uno(base, insertar(fila), lectura) == OK


def test_dos_altas_en_la_misma_transaccion_quedan_en_orden_de_insercion(base: str) -> None:
    uno, otro = rm(), rm()
    lectura = (
        f"SELECT 1 FROM {TABLA} a, {TABLA} b WHERE a.id = $1 AND b.id = $2 "  # noqa: S608
        "AND b.created_at > a.created_at",
        [uno["id"], otro["id"]],
    )
    assert _uno(base, insertar(uno), insertar(otro), lectura) == OK


def test_updated_at_no_puede_ser_anterior_a_created_at(base: str) -> None:
    fila = rm(created_at=datetime(2026, 10, 20, 10, 0, tzinfo=UTC),
              updated_at=datetime(2026, 10, 20, 9, 0, tzinfo=UTC))  # fmt: skip
    ok = rm(created_at=datetime(2026, 10, 20, 10, 0, tzinfo=UTC),
            updated_at=datetime(2026, 10, 20, 10, 0, tzinfo=UTC))  # fmt: skip
    salidas = _correr(base, [insertar(fila)], [insertar(ok)])
    assert salidas == [(CHECK, "ck_personal_records_updated_after_created"), OK]


def test_un_manual_no_puede_ser_capped_un_derivado_si(base: str) -> None:
    manual = marca(capped=True, seconds=600, reps=40)
    derivada = marca(
        source="derived", result_id=uuid4(), wod_id=uuid4(), capped=True, seconds=600, reps=40
    )
    assert _correr(base, [insertar(manual)], [insertar(derivada)]) == [
        (CHECK, "ck_personal_records_capped_manual"),
        OK,
    ]


def test_un_benchmark_exige_al_menos_una_marca(base: str) -> None:
    sin_marca = marca(seconds=None)
    con_marca = marca(seconds=None, reps=0)
    assert _correr(base, [insertar(sin_marca)], [insertar(con_marca)]) == [
        (CHECK, "ck_personal_records_benchmark_shape"),
        OK,
    ]


def _insertar_invalidado(fila: dict[str, Any]) -> list[Paso]:
    """Salta SOLO la guarda de INSERT dentro de la transacción de la prueba (se revierte) para
    probar el CHECK que, con la guarda armada, quedaría detrás de ella."""
    apagar = (f"ALTER TABLE {TABLA} DISABLE TRIGGER personal_records_guard_insert", [])
    return [apagar, insertar(fila)]


def test_invalidated_at_e_invalidated_by_van_juntas(base: str) -> None:
    sin_quien = rm(
        invalidated_at=datetime(2026, 10, 21, tzinfo=UTC), invalidated_reason="manual_error"
    )
    sin_cuando = rm(invalidated_by=SYSTEM_USER_ID)
    con_ambos = rm(
        invalidated_at=datetime(2026, 10, 21, tzinfo=UTC),
        invalidated_reason="manual_error",
        invalidated_by=SYSTEM_USER_ID,
        created_at=datetime(2026, 10, 20, tzinfo=UTC),
        updated_at=datetime(2026, 10, 21, tzinfo=UTC),
    )
    salidas = _correr(
        base,
        _insertar_invalidado(sin_quien),
        _insertar_invalidado(sin_cuando),
        _insertar_invalidado(con_ambos),
    )
    assert [s[0] for s in salidas] == [CHECK, CHECK, ""], salidas


def test_invalidated_at_no_puede_ser_anterior_a_created_at(base: str) -> None:
    antes = rm(
        created_at=datetime(2026, 10, 20, tzinfo=UTC),
        updated_at=datetime(2026, 10, 20, tzinfo=UTC),
        invalidated_at=datetime(2026, 10, 19, tzinfo=UTC),
        invalidated_reason="manual_error",
        invalidated_by=SYSTEM_USER_ID,
    )
    assert _uno(base, *_insertar_invalidado(antes))[0] == CHECK


def test_invalidated_by_result_id_solo_con_superseded_check_directo(base: str) -> None:
    fila = derivado(
        created_at=datetime(2026, 10, 20, tzinfo=UTC),
        updated_at=datetime(2026, 10, 21, tzinfo=UTC),
        invalidated_at=datetime(2026, 10, 21, tzinfo=UTC),
        invalidated_reason="voided",
        invalidated_by=SYSTEM_USER_ID,
        invalidated_by_result_id=uuid4(),
    )
    assert _uno(base, *_insertar_invalidado(fila))[0] == CHECK
