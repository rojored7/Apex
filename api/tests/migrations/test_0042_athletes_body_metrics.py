"""`0042_athletes_body_metrics` (S9-A1, US-178; S9-D2, S9-D3, S9-D18, S9-D31). Rojo A1.

Padre `0041_results_session_index`. Crea el esquema `athletes` y la tabla `athletes.body_metrics`
con CHECK «al menos una medida» y `voided_pair`, el índice `(member_id, measured_on DESC,
created_at DESC)` y cuatro guardas `ENABLE ALWAYS` (`tgenabled = 'A'`), `SECURITY INVOKER` con
`search_path = pg_catalog`:
- `body_metrics_guard_insert`: `voided_at` y `voided_by` nulos al nacer y cada blob con la FORMA
  completa (`apx1.<uuid>.A256GCM.<nonce>.<ct>`, no solo el prefijo) y una llave `encrypt` de la
  clase `athlete.metric` (`active` o `decrypt_only`, S9-D31 precisión del plan);
- `body_metrics_guard_update` con tres ramas excluyentes: (a) RECIFRADO: blob por blob con la misma
  nulidad por columna, la llave del blob nuevo es la `encrypt` `active` de la clase y DISTINTA de la
  del blob viejo, la forma completa, `length(NEW) = length(OLD)` en las tres columnas de ancho fijo
  y sin tocar `voided_*` en el mismo `UPDATE`; una fila anulada SÍ se recifra; (b) ANULACIÓN:
  `voided_at` y `voided_by` pasan de NULL a valor en el mismo `UPDATE` (terminal); (c) `updated_at`
  sin retroceder; `id`, `member_id`, `measured_on`, `recorded_by` y `created_*` no cambian nunca;
- `body_metrics_forbid_delete` y `body_metrics_forbid_truncate`: nunca se borra.
Cada escenario corre en una transacción que se revierte (`resultados`); las llaves de la clase se
siembran dentro de ella. `P0001` es el error de las guardas; `23514`, el de un CHECK.
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

from tests.migrations._apoyo_notificaciones import (
    SYSTEM_USER_ID,
    Paso,
    columnas,
    consultar,
    existe,
    resultados,
)

REVISION = "0042_athletes_body_metrics"
PADRE = "0041_results_session_index"
TABLA = "athletes.body_metrics"
GUARDA = "P0001"
CHECK = "23514"
OK = ("", None)
TRIGGERS = (
    "body_metrics_guard_insert",
    "body_metrics_guard_update",
    "body_metrics_forbid_delete",
    "body_metrics_forbid_truncate",
)
AHORA = date(2026, 10, 20)
NONCE = "A" * 16  # 12 bytes en base64url
LARGO_PESO, LARGO_ESTATURA, LARGO_GRASA = 31, 27, 24  # largos de ejemplo de los tres anchos fijos
MEDIDAS = ("weight_g", "height_cm", "body_fat_pct", "notes")

K_VIEJA, K_NUEVA, K_OTRA, K_DECRYPT, K_RETIRED = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()


def _blob(llave: UUID, largo: int, relleno: str = "B") -> str:
    return f"apx1.{llave}.A256GCM.{NONCE}.{relleno * largo}"


def _llave(id_: UUID, clase: str, version: int, estado: str) -> Paso:
    return (
        "INSERT INTO crypto.crypto_keys (id, created_by, purpose, data_class, algorithm, provider,"
        " version, state, wrapped_material) VALUES ($1, $2, 'encrypt', $3, 'A256GCM', 'local',"
        " $4, $5, $6)",
        [id_, SYSTEM_USER_ID, clase, version, estado, b"envuelta"],
    )


def llaves() -> list[Paso]:
    """Lo que el bus deja tras una rotación: `K_VIEJA` en `decrypt_only`, `K_NUEVA` activa, otra
    clase con su propia llave activa y una segunda `decrypt_only` de la clase (para ese caso)."""
    return [
        ("ALTER TABLE crypto.crypto_keys DISABLE TRIGGER USER", []),
        (
            "DELETE FROM crypto.crypto_keys WHERE data_class IN ('athlete.metric', 'prueba.otra')",
            [],
        ),
        _llave(K_VIEJA, "athlete.metric", 1, "decrypt_only"),
        _llave(K_DECRYPT, "athlete.metric", 2, "decrypt_only"),
        _llave(K_NUEVA, "athlete.metric", 3, "active"),
        _llave(K_RETIRED, "athlete.metric", 4, "retired"),
        _llave(K_OTRA, "prueba.otra", 1, "active"),
    ]


def medida(llave: UUID = K_VIEJA, **cambios: Any) -> dict[str, Any]:
    fila: dict[str, Any] = {
        "id": uuid4(),
        "created_by": SYSTEM_USER_ID,
        "member_id": uuid4(),
        "measured_on": AHORA,
        "recorded_by": SYSTEM_USER_ID,
        "weight_g": _blob(llave, LARGO_PESO),
        "height_cm": _blob(llave, LARGO_ESTATURA),
        "body_fat_pct": _blob(llave, LARGO_GRASA),
        "notes": _blob(llave, 170),
    }
    fila.update(cambios)
    return fila


def insertar(fila: dict[str, Any]) -> Paso:
    nombres = list(fila)
    marcas = ", ".join(f"${i}" for i in range(1, len(nombres) + 1))
    sql = f"INSERT INTO {TABLA} ({', '.join(nombres)}) VALUES ({marcas})"  # noqa: S608
    return sql, [fila[c] for c in nombres]


def actualizar(id_: UUID, asignacion: str, *args: Any) -> Paso:
    return f"UPDATE {TABLA} SET {asignacion} WHERE id = $1", [id_, *args]  # noqa: S608


def anular(id_: UUID) -> Paso:
    return actualizar(id_, "voided_at = now(), voided_by = $2", SYSTEM_USER_ID)


def _escenario(*pasos: Paso) -> list[Paso]:
    return [*llaves(), *pasos]


def _correr(url: str, *escenarios: Sequence[Paso]) -> list[tuple[str, str | None]]:
    return resultados(url, [list(e) for e in escenarios])


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


# Cadena, esquema, columnas, CHECK e índice ----------------------------------------------------


def test_cuelga_de_0041_y_esta_en_la_cadena_de_head(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_crea_el_esquema_athletes_y_la_tabla(base: str) -> None:
    esquema = consultar(base, "SELECT 1 AS e FROM pg_namespace WHERE nspname = 'athletes'")
    assert len(esquema) == 1
    assert existe(base, TABLA)


def test_las_columnas_tipos_y_nulidad_de_s9_d3(base: str) -> None:
    assert columnas(base, TABLA) == {
        "id": ("uuid", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
        "updated_at": ("timestamp with time zone", "NO"),
        "created_by": ("uuid", "NO"),
        "member_id": ("uuid", "NO"),
        "measured_on": ("date", "NO"),
        "recorded_by": ("uuid", "NO"),
        "weight_g": ("text", "YES"),
        "height_cm": ("text", "YES"),
        "body_fat_pct": ("text", "YES"),
        "notes": ("text", "YES"),
        "voided_at": ("timestamp with time zone", "YES"),
        "voided_by": ("uuid", "YES"),
    }


def test_no_hay_claves_foraneas_entre_esquemas(base: str) -> None:
    assert existe(base, TABLA)
    filas = consultar(
        base,
        "SELECT conname FROM pg_constraint WHERE conrelid = to_regclass($1) AND contype = 'f'",
        TABLA,
    )
    assert filas == []


def test_el_indice_por_socio_fecha_y_creacion_descendentes(base: str) -> None:
    filas = consultar(
        base,
        "SELECT indexdef FROM pg_indexes WHERE schemaname = 'athletes' "
        "AND tablename = 'body_metrics' AND indexdef LIKE '%member_id%'",
    )
    assert any("(member_id, measured_on DESC, created_at DESC)" in f["indexdef"] for f in filas), [
        f["indexdef"] for f in filas
    ]


def test_check_al_menos_una_de_las_tres_medidas(base: str) -> None:
    solo_notas = medida(weight_g=None, height_cm=None, body_fat_pct=None)
    una_sola = medida(weight_g=None, body_fat_pct=None, notes=None)
    sin_nada = medida(weight_g=None, height_cm=None, body_fat_pct=None, notes=None)
    salidas = _correr(
        base,
        _escenario(insertar(solo_notas)),
        _escenario(insertar(una_sola)),
        _escenario(insertar(sin_nada)),
    )
    assert [s[0] for s in salidas] == [CHECK, "", CHECK], salidas


def test_check_voided_pair_las_dos_columnas_van_juntas_o_ninguna(base: str) -> None:
    id_ = uuid4()
    solo_at = _escenario(insertar(medida(id=id_)), actualizar(id_, "voided_at = now()"))
    solo_by = _escenario(
        insertar(medida(id=id_)), actualizar(id_, "voided_by = $2", SYSTEM_USER_ID)
    )
    salidas = _correr(base, solo_at, solo_by)
    assert all(s[0] in {GUARDA, CHECK} for s in salidas), salidas


# Guarda de INSERT ------------------------------------------------------------------------------


def test_insert_con_llave_activa_o_decrypt_only_de_la_clase_pasa(base: str) -> None:
    """Precisión del plan: una rotación entre el cifrado y el `INSERT` no da un 500."""
    activa = medida(K_NUEVA)
    decrypt_only = medida(K_VIEJA)
    mezcla = medida(K_VIEJA, height_cm=_blob(K_NUEVA, LARGO_ESTATURA))
    assert _correr(
        base,
        _escenario(insertar(activa)),
        _escenario(insertar(decrypt_only)),
        _escenario(insertar(mezcla)),
    ) == [OK, OK, OK]


def test_insert_nace_sin_voided_at_ni_voided_by(base: str) -> None:
    instante = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)
    ambas = medida(voided_at=instante, voided_by=SYSTEM_USER_ID)
    solo_at = medida(voided_at=instante)
    solo_by = medida(voided_by=SYSTEM_USER_ID)
    salidas = _correr(
        base,
        _escenario(insertar(ambas)),
        _escenario(insertar(solo_at)),
        _escenario(insertar(solo_by)),
    )
    assert salidas[0][0] == GUARDA, salidas  # nace anulada: la guarda, no un CHECK
    assert all(s[0] in {GUARDA, CHECK} for s in salidas), salidas


@pytest.mark.parametrize("columna", MEDIDAS)
@pytest.mark.parametrize(
    "malo",
    [
        "apx1.basura",
        "apx1.",
        f"apx1.{K_NUEVA}.A256GCM.{NONCE}.",  # sin texto cifrado
        f"apx1.{K_NUEVA}.A128GCM.{NONCE}.BBBB",  # algoritmo que el bus no usa
        f"apx1.{K_NUEVA}.A256GCM.AAAA.BBBB",  # nonce que no mide 12 bytes
        f"apx1.no-es-uuid.A256GCM.{NONCE}.BBBB",
        f"apx1.{K_NUEVA}.A256GCM.{NONCE}.BB BB",  # fuera del alfabeto base64url
        f"{K_NUEVA}.A256GCM.{NONCE}.BBBB",  # sin el prefijo
        "texto en claro",
        f"apx1.{K_NUEVA}.A256GCM.{NONCE}.{'B' * 21}",  # L-2: menos de 22 caracteres
    ],
)
def test_insert_exige_la_forma_completa_del_blob_en_cada_columna(
    base: str, columna: str, malo: str
) -> None:
    salida = _correr(base, _escenario(insertar(medida(K_NUEVA, **{columna: malo}))))
    assert salida[0][0] in {GUARDA, CHECK}, (salida, malo)
    if malo.startswith("apx1."):  # pasa el `LIKE 'apx1.%'`: lo detiene la guarda con su forma
        assert salida[0][0] == GUARDA, malo


def test_insert_exige_una_llave_de_la_clase_athlete_metric(base: str) -> None:
    otra_clase = medida(K_OTRA)
    inexistente = medida(uuid4())
    una_columna = medida(K_NUEVA, notes=_blob(K_OTRA, 170))
    assert (
        _correr(
            base,
            _escenario(insertar(otra_clase)),
            _escenario(insertar(inexistente)),
            _escenario(insertar(una_columna)),
        )
        == [(GUARDA, None)] * 3
    )


def test_insert_con_una_llave_retirada_de_la_clase_falla(base: str) -> None:
    """L-1 (revisión de A1): una llave `retired` no admite blobs nuevos."""
    retirada = medida(K_RETIRED)
    en_una_columna = medida(K_NUEVA, notes=_blob(K_RETIRED, 170))
    assert (
        _correr(base, _escenario(insertar(retirada)), _escenario(insertar(en_una_columna)))
        == [(GUARDA, None)] * 2
    )


def test_recifrar_con_una_llave_retirada_falla(base: str) -> None:
    id_ = uuid4()
    paso = actualizar(id_, "weight_g = $2", _blob(K_RETIRED, LARGO_PESO, "C"))
    assert _correr(base, _escenario(insertar(medida(id=id_)), paso)) == [(GUARDA, None)]


def test_insert_con_columnas_vacias_pasa_si_las_que_tiene_son_validas(base: str) -> None:
    parcial = medida(K_NUEVA, weight_g=None, body_fat_pct=None, notes=None)
    assert _correr(base, _escenario(insertar(parcial))) == [OK]


# Guarda de UPDATE: recifrado (rama a) -----------------------------------------------------------


def _recifrar(id_: UUID, *, llave: UUID = K_NUEVA, **cambios: str) -> Paso:
    valores = {
        "weight_g": _blob(llave, LARGO_PESO, "C"),
        "height_cm": _blob(llave, LARGO_ESTATURA, "C"),
        "body_fat_pct": _blob(llave, LARGO_GRASA, "C"),
        "notes": _blob(llave, 170, "C"),
    }
    valores.update(cambios)
    asignaciones = ", ".join(f"{c} = ${i}" for i, c in enumerate(valores, start=2))
    return actualizar(id_, asignaciones, *valores.values())


def test_recifrar_las_cuatro_columnas_con_la_llave_activa_y_distinta_pasa(base: str) -> None:
    id_ = uuid4()
    assert _correr(base, _escenario(insertar(medida(id=id_)), _recifrar(id_))) == [OK]


def test_recifrar_una_sola_columna_pasa(base: str) -> None:
    id_ = uuid4()
    una = actualizar(id_, "weight_g = $2", _blob(K_NUEVA, LARGO_PESO, "C"))
    assert _correr(base, _escenario(insertar(medida(id=id_)), una)) == [OK]


def test_recifrar_con_la_misma_llave_falla(base: str) -> None:
    """Fuera de una rotación no hay `UPDATE` de blob posible: la llave nueva debe ser DISTINTA."""
    id_ = uuid4()
    misma = actualizar(id_, "weight_g = $2", _blob(K_NUEVA, LARGO_PESO, "C"))
    assert _correr(base, _escenario(insertar(medida(K_NUEVA, id=id_)), misma)) == [(GUARDA, None)]


def test_recifrar_con_una_llave_que_no_es_la_activa_falla(base: str) -> None:
    id_ = uuid4()
    decrypt_only = actualizar(id_, "weight_g = $2", _blob(K_DECRYPT, LARGO_PESO, "C"))
    assert _correr(base, _escenario(insertar(medida(id=id_)), decrypt_only)) == [(GUARDA, None)]


def test_recifrar_con_llave_de_otra_clase_o_inexistente_falla(base: str) -> None:
    id_ = uuid4()
    otra = actualizar(id_, "weight_g = $2", _blob(K_OTRA, LARGO_PESO, "C"))
    inexistente = actualizar(id_, "weight_g = $2", _blob(uuid4(), LARGO_PESO, "C"))
    assert (
        _correr(
            base,
            _escenario(insertar(medida(id=id_)), otra),
            _escenario(insertar(medida(id=id_)), inexistente),
        )
        == [(GUARDA, None)] * 2
    )


@pytest.mark.parametrize("columna", MEDIDAS)
@pytest.mark.parametrize(
    "malo",
    ["apx1.basura", "texto en claro", f"apx1.{K_NUEVA}.A128GCM.{NONCE}.CCCC", f"apx1.{K_NUEVA}."],
)
def test_recifrar_con_un_blob_de_forma_invalida_falla(base: str, columna: str, malo: str) -> None:
    id_ = uuid4()
    paso = actualizar(id_, f"{columna} = $2", malo)
    salida = _correr(base, _escenario(insertar(medida(id=id_)), paso))
    assert salida[0][0] in {GUARDA, CHECK}, salida


@pytest.mark.parametrize(
    ("columna", "largo_original", "largo_nuevo"),
    [
        ("weight_g", LARGO_PESO, LARGO_PESO + 1),
        ("weight_g", LARGO_PESO, LARGO_PESO - 1),
        ("height_cm", LARGO_ESTATURA, LARGO_ESTATURA + 4),
        ("body_fat_pct", LARGO_GRASA, LARGO_GRASA - 4),
    ],
)
def test_recifrar_con_largo_distinto_en_las_tres_columnas_de_ancho_fijo_falla(
    base: str, columna: str, largo_original: int, largo_nuevo: int
) -> None:
    id_ = uuid4()
    paso = actualizar(id_, f"{columna} = $2", _blob(K_NUEVA, largo_nuevo, "C"))
    assert largo_original != largo_nuevo
    assert _correr(base, _escenario(insertar(medida(id=id_)), paso)) == [(GUARDA, None)]


def test_las_notas_no_son_de_ancho_fijo_en_el_recifrado(base: str) -> None:
    """`length(NEW) = length(OLD)` solo en `weight_g`, `height_cm` y `body_fat_pct` (S9-D31)."""
    id_ = uuid4()
    paso = actualizar(id_, "notes = $2", _blob(K_NUEVA, 340, "C"))
    assert _correr(base, _escenario(insertar(medida(id=id_)), paso)) == [OK]


def test_recifrar_y_anular_en_el_mismo_update_falla(base: str) -> None:
    id_ = uuid4()
    ambas = actualizar(
        id_,
        "weight_g = $2, voided_at = now(), voided_by = $3",
        _blob(K_NUEVA, LARGO_PESO, "C"),
        SYSTEM_USER_ID,
    )
    assert _correr(base, _escenario(insertar(medida(id=id_)), ambas)) == [(GUARDA, None)]


def test_una_fila_anulada_si_se_recifra(base: str) -> None:
    """Si no, `retire-key` quedaría bloqueado para siempre: «terminal» es solo de `voided_*`."""
    id_ = uuid4()
    assert _correr(base, _escenario(insertar(medida(id=id_)), anular(id_), _recifrar(id_))) == [OK]


def test_recifrar_no_cambia_la_nulidad_de_ninguna_columna(base: str) -> None:
    id_ = uuid4()
    parcial = medida(id=id_, body_fat_pct=None, notes=None)
    a_nulo = actualizar(id_, "weight_g = NULL")
    de_nulo_a_blob = actualizar(id_, "notes = $2", _blob(K_NUEVA, 170, "C"))
    de_nulo_a_blob_grasa = actualizar(id_, "body_fat_pct = $2", _blob(K_NUEVA, LARGO_GRASA, "C"))
    assert (
        _correr(
            base,
            _escenario(insertar(parcial), a_nulo),
            _escenario(insertar(parcial), de_nulo_a_blob),
            _escenario(insertar(parcial), de_nulo_a_blob_grasa),
        )
        == [(GUARDA, None)] * 3
    )


# Guarda de UPDATE: anulación, updated_at e inmutables -------------------------------------------


def test_anular_pasa_de_null_a_valor_en_el_mismo_update(base: str) -> None:
    id_ = uuid4()
    assert _correr(base, _escenario(insertar(medida(id=id_)), anular(id_))) == [OK]


def test_anular_solo_una_de_las_dos_columnas_falla(base: str) -> None:
    id_ = uuid4()
    solo_at = actualizar(id_, "voided_at = now()")
    solo_by = actualizar(id_, "voided_by = $2", SYSTEM_USER_ID)
    salidas = _correr(
        base,
        _escenario(insertar(medida(id=id_)), solo_at),
        _escenario(insertar(medida(id=id_)), solo_by),
    )
    assert all(s[0] in {GUARDA, CHECK} for s in salidas), salidas


def test_una_anulada_es_terminal_no_se_desanula_ni_se_reanula(base: str) -> None:
    id_ = uuid4()
    desanular = actualizar(id_, "voided_at = NULL, voided_by = NULL")
    cambiar_at = actualizar(id_, "voided_at = now() + interval '1 day'")
    cambiar_by = actualizar(id_, "voided_by = $2", uuid4())
    # Un segundo `anular(id_)` en la MISMA transacción asigna el mismo `now()` y el mismo usuario:
    # no cambia nada y pasa. La reanulación real cambia el instante y quien anula (S9-D31).
    reanular = actualizar(id_, "voided_at = now() + interval '2 days', voided_by = $2", uuid4())
    salidas = _correr(
        base,
        _escenario(insertar(medida(id=id_)), anular(id_), desanular),
        _escenario(insertar(medida(id=id_)), anular(id_), cambiar_at),
        _escenario(insertar(medida(id=id_)), anular(id_), cambiar_by),
        _escenario(insertar(medida(id=id_)), anular(id_), reanular),
    )
    assert salidas == [(GUARDA, None)] * 4, salidas


def test_updated_at_no_retrocede_pero_puede_avanzar_o_quedar_igual(base: str) -> None:
    id_ = uuid4()
    retroceder = actualizar(id_, "updated_at = updated_at - interval '1 day'")
    avanzar = actualizar(id_, "updated_at = updated_at + interval '1 second'")
    igual = actualizar(id_, "updated_at = updated_at")
    assert _correr(
        base,
        _escenario(insertar(medida(id=id_)), retroceder),
        _escenario(insertar(medida(id=id_)), avanzar),
        _escenario(insertar(medida(id=id_)), igual),
    ) == [(GUARDA, None), OK, OK]


@pytest.mark.parametrize(
    ("asignacion", "args"),
    [
        ("id = $2", [uuid4()]),
        ("member_id = $2", [uuid4()]),
        ("measured_on = '2020-01-01'", []),
        ("recorded_by = $2", [uuid4()]),
        ("created_by = $2", [uuid4()]),
        ("created_at = created_at - interval '1 day'", []),
    ],
    ids=["id", "member_id", "measured_on", "recorded_by", "created_by", "created_at"],
)
def test_las_columnas_fijas_no_cambian_nunca(base: str, asignacion: str, args: list[Any]) -> None:
    id_ = uuid4()
    paso = actualizar(id_, asignacion, *args)
    assert _correr(base, _escenario(insertar(medida(id=id_)), paso)) == [(GUARDA, None)]


# Sin borrado y guardas siempre activas ----------------------------------------------------------


def test_delete_y_truncate_estan_prohibidos(base: str) -> None:
    id_ = uuid4()
    borrar = (f"DELETE FROM {TABLA} WHERE id = $1", [id_])  # noqa: S608
    truncar = (f"TRUNCATE {TABLA}", [])
    assert (
        _correr(
            base,
            _escenario(insertar(medida(id=id_)), borrar),
            _escenario(insertar(medida(id=id_)), truncar),
        )
        == [(GUARDA, None)] * 2
    )


def test_bajo_replica_las_guardas_siguen_corriendo(base: str) -> None:
    """`ENABLE ALWAYS`: `session_replication_role = replica` no las salta."""
    id_ = uuid4()
    replica = ("SET LOCAL session_replication_role = replica", [])
    borrar = (f"DELETE FROM {TABLA} WHERE id = $1", [id_])  # noqa: S608
    cambiar = actualizar(id_, "measured_on = '2020-01-01'")
    assert (
        _correr(
            base,
            _escenario(insertar(medida(id=id_)), replica, borrar),
            _escenario(insertar(medida(id=id_)), replica, cambiar),
        )
        == [(GUARDA, None)] * 2
    )


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
    assert "forbid_mutation" in nombres and len(filas) >= 3, nombres
    for fila in filas:
        assert fila["prosecdef"] is False, fila["proname"]
        assert "search_path=pg_catalog" in (fila["proconfig"] or []), fila["proname"]


# Downgrade -------------------------------------------------------------------------------------


def test_downgrade_y_upgrade_son_reversibles(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert not existe(base, TABLA)
        esquema = consultar(base, "SELECT 1 AS e FROM pg_namespace WHERE nspname = 'athletes'")
        assert esquema == []
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


# Carrera con `retire-key` (M-1 de la revisión de A1) --------------------------------------------


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _retiro_espera(url: str, *, recifrado: bool) -> str:
    """Conexión A: INSERT o recifrado SIN confirmar con la guarda de `0042`. Conexión B: lo que hace
    `retire-key` (`SELECT ... FOR UPDATE` de la fila de la llave) con `lock_timeout` corto.
    Devuelve el SQLSTATE de B (`55P03` si la guarda tomó `FOR SHARE` de la llave)."""
    from tests.conftest import LIMPIAR_ATHLETES
    from tests.factories.triggers import disable_user_sql, rearm_always_sql

    dsn = _dsn(url)
    sembrar = await asyncpg.connect(dsn)
    a = await asyncpg.connect(dsn)
    b = await asyncpg.connect(dsn)
    try:
        await sembrar.execute(disable_user_sql("crypto.crypto_keys"))
        await sembrar.execute("DELETE FROM crypto.crypto_keys WHERE data_class = 'athlete.metric'")
        for paso in (
            _llave(K_VIEJA, "athlete.metric", 1, "decrypt_only"),
            _llave(K_NUEVA, "athlete.metric", 2, "active"),
        ):
            await sembrar.execute(paso[0], *paso[1])
        await sembrar.execute(rearm_always_sql("crypto.crypto_keys"))
        id_ = uuid4()
        llave_a_bloquear = K_VIEJA
        if recifrado:
            sql, args = insertar(medida(K_VIEJA, id=id_))
            await sembrar.execute(sql, *args)
        tr = a.transaction()
        await tr.start()
        if recifrado:
            sql, args = actualizar(id_, "weight_g = $2", _blob(K_NUEVA, LARGO_PESO, "C"))
            llave_a_bloquear = K_NUEVA
        else:
            sql, args = insertar(medida(K_VIEJA))
        await a.execute(sql, *args)
        await b.execute("SET lock_timeout = '300ms'")
        try:
            await b.fetch(
                "SELECT id FROM crypto.crypto_keys WHERE id = $1 FOR UPDATE", llave_a_bloquear
            )
            estado = ""
        except asyncpg.PostgresError as error:
            estado = error.sqlstate or ""
        await tr.rollback()
        return estado
    finally:
        await sembrar.execute(LIMPIAR_ATHLETES)
        await sembrar.execute(disable_user_sql("crypto.crypto_keys"))
        await sembrar.execute("DELETE FROM crypto.crypto_keys WHERE data_class = 'athlete.metric'")
        await sembrar.execute(rearm_always_sql("crypto.crypto_keys"))
        for conexion in (sembrar, a, b):
            await conexion.close()


@pytest.mark.parametrize("recifrado", [False, True], ids=["insert", "recifrado"])
def test_la_guarda_toma_for_share_de_la_llave_y_un_retiro_concurrente_espera(
    base: str, recifrado: bool
) -> None:
    """`retire-key` toma `FOR UPDATE` de la llave: mientras un INSERT o un recifrado sin confirmar
    la usó, debe esperar (si no, quedaría una medida con una llave retirada y el conteo en 0)."""
    assert asyncio.run(_retiro_espera(base, recifrado=recifrado)) == "55P03"
