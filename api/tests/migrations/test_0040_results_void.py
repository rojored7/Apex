"""`0040_results_void` (S8-B3b, S8-D46 b): la anulación de un resultado por un admin.

Padre `0039_results_updated_guard`. Columnas `voided_by`, `voided_at` y `void_reason`; `status`
admite `voided`. La guarda de `0037` deja pasar SOLO `validated -> voided` de una fila vigente, con
`is_current` de `true` a `false` y los tres campos de NULL a valor en el MISMO `UPDATE`; un anulado
no se toca más. El trigger diferido de sucesor no exige sucesor a un anulado. CHECK de forma:
`voided_shape`, `void_reason_length`, `voided_not_current` y `validated_pair` (validado o anulado
llevan validación).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.context import SYSTEM_USER_ID
from tests.conftest import LIMPIAR_WOD_RESULTS
from tests.migrations._apoyo_notificaciones import consultar, existe, resultados
from tests.migrations.test_0023_attachments import _ejecutar
from tests.migrations.test_0036_results_wod_results import TABLA, fila
from tests.migrations.test_0037_results_immutability import GUARDA, _confirmar, _upd

REVISION = "0040_results_void"
PADRE = "0039_results_updated_guard"
CHECK_VIOLATION = "23514"
ANULAR = (
    "status = 'voided', is_current = false, voided_by = $2, voided_at = now(), "
    "void_reason = 'Registrado en el socio equivocado'"
)
ANULAR_SIN_APAGAR = "status = 'voided', voided_by = $2, voided_at = now(), void_reason = 'x'"


def _anular(rid: Any) -> tuple[str, list[Any]]:
    return _upd(rid, ANULAR, SYSTEM_USER_ID)


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> Iterator[str]:
    scripts = ScriptDirectory.from_config(alembic_config)
    if scripts.get_revision(REVISION) is None:
        pytest.fail(f"no existe la revisión {REVISION}")
    try:
        yield migrated_database
    finally:
        if existe(migrated_database, TABLA):
            _ejecutar(migrated_database, LIMPIAR_WOD_RESULTS)


def test_cuelga_de_0039_y_tiene_id_corto(alembic_config: Config) -> None:
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_columnas_nuevas_son_nulables(base: str) -> None:
    filas = consultar(
        base,
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'results' AND table_name = 'wod_results' "
        "AND column_name IN ('voided_by', 'voided_at', 'void_reason') ORDER BY column_name",
    )
    assert [(f["column_name"], f["data_type"], f["is_nullable"]) for f in filas] == [
        ("void_reason", "text", "YES"),
        ("voided_at", "timestamp with time zone", "YES"),
        ("voided_by", "uuid", "YES"),
    ]


def test_validated_pasa_a_voided_con_los_tres_campos_y_apagado(base: str) -> None:
    rid = uuid4()
    assert resultados(base, [[fila(id=rid), _anular(rid)]]) == [("", None)]


def test_anular_sin_el_motivo_o_sin_quien_viola_voided_shape(base: str) -> None:
    rid = uuid4()
    sin_todo = _upd(rid, "status = 'voided', is_current = false")
    sin_motivo = _upd(
        rid,
        "status = 'voided', is_current = false, voided_by = $2, voided_at = now()",
        SYSTEM_USER_ID,
    )
    salidas = resultados(base, [[fila(id=rid), sin_todo], [fila(id=rid), sin_motivo]])
    assert salidas == [
        (CHECK_VIOLATION, "ck_wod_results_voided_shape"),
        (CHECK_VIOLATION, "ck_wod_results_voided_shape"),
    ]


def test_anular_sin_apagar_viola_voided_not_current(base: str) -> None:
    rid = uuid4()
    salidas = resultados(base, [[fila(id=rid), _upd(rid, ANULAR_SIN_APAGAR, SYSTEM_USER_ID)]])
    assert salidas == [(CHECK_VIOLATION, "ck_wod_results_voided_not_current")]


@pytest.mark.parametrize("motivo", ["''", "repeat('x', 201)"])
def test_motivo_de_1_a_200(base: str, motivo: str) -> None:
    rid = uuid4()
    sql = (
        "status = 'voided', is_current = false, voided_by = $2, voided_at = now(), "
        f"void_reason = {motivo}"
    )
    assert resultados(base, [[fila(id=rid), _upd(rid, sql, SYSTEM_USER_ID)]]) == [
        (CHECK_VIOLATION, "ck_wod_results_void_reason_length")
    ]


def test_los_campos_de_anulacion_no_se_escriben_sin_anular(base: str) -> None:
    rid = uuid4()
    assert resultados(base, [[fila(id=rid), _upd(rid, "void_reason = 'x'")]]) == [(GUARDA, None)]


def test_un_resultado_pending_no_se_anula(base: str) -> None:
    rid = uuid4()
    pendiente = fila(id=rid, status="pending", vby=None, vat=None)
    assert resultados(base, [[pendiente, _anular(rid)]]) == [(GUARDA, None)]


def test_un_resultado_ya_apagado_no_se_anula(base: str) -> None:
    rid, nuevo = uuid4(), uuid4()
    pasos = [fila(id=rid), _upd(rid, "is_current = false"), fila(id=nuevo, sup=rid)]
    # `rid` ya está corregido (apagado): anularlo no tiene sentido y la guarda lo impide.
    anular = _upd(rid, ANULAR_SIN_APAGAR, SYSTEM_USER_ID)
    assert resultados(base, [[*pasos, anular]]) == [(GUARDA, None)]


def test_un_anulado_es_terminal(base: str) -> None:
    rid = uuid4()
    previos = [fila(id=rid), _anular(rid)]
    cambios = [
        "status = 'validated'",
        "status = 'pending'",
        "void_reason = 'otro'",
        "voided_by = NULL",
        "is_current = true",
        "seconds = 1",
    ]
    escenarios = [[*previos, _upd(rid, c)] for c in cambios]
    escenarios.append([*previos, _upd(rid, "updated_at = now()")])
    salidas = resultados(base, escenarios)
    assert salidas[:6] == [(GUARDA, None)] * 6
    assert salidas[6] == ("", None)


def test_no_se_inserta_una_fila_anulada(base: str) -> None:
    rid = uuid4()
    assert resultados(base, [[fila(id=rid, status="voided")]]) == [(GUARDA, None)]


def test_el_anulado_no_exige_sucesor_al_confirmar(base: str) -> None:
    a, b = uuid4(), uuid4()
    assert _confirmar(base, [fila(id=a), _anular(a)]) == ""
    # Sin la anulación, apagar sigue exigiendo sucesor (0037 no cambia).
    assert _confirmar(base, [fila(id=b), _upd(b, "is_current = false")]) == GUARDA


def test_anulado_libera_el_unico_vigente_del_socio_en_el_wod(base: str) -> None:
    a, b = uuid4(), uuid4()
    assert _confirmar(base, [fila(id=a), _anular(a), fila(id=b)]) == ""


def test_la_guarda_sigue_siempre_activa_y_la_de_updated_at_se_conserva(base: str) -> None:
    (g,) = consultar(
        base, "SELECT tgenabled FROM pg_trigger WHERE tgname = 'wod_results_guard_update'"
    )
    assert g["tgenabled"] in {"A", b"A"}
    rid = uuid4()
    atras = _upd(rid, "updated_at = now() - interval '1 day'")
    assert resultados(base, [[fila(id=rid), atras]]) == [(GUARDA, None)]  # `0039` sigue en pie


def test_ciclo_downgrade_upgrade_sin_anulados(alembic_config: Config, base: str) -> None:
    rid = uuid4()
    try:
        command.downgrade(alembic_config, PADRE)
        columnas = consultar(
            base,
            "SELECT count(*) AS n FROM information_schema.columns WHERE table_schema = 'results' "
            "AND table_name = 'wod_results' AND column_name = 'void_reason'",
        )
        assert columnas[0]["n"] == 0
        # Sin 0040 un estado `voided` vuelve a estar prohibido por el CHECK de `status`.
        salida = resultados(base, [[fila(id=rid, status="voided", vby=None, vat=None)]])
        assert salida[0][0] != ""
    finally:
        command.upgrade(alembic_config, "head")
    assert resultados(base, [[fila(id=rid), _anular(rid)]]) == [("", None)]
