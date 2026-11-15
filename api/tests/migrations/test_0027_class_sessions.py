"""`0027_class_sessions` (S7-B1, US-156; S7-D10, M-3). Rojo B1.

Padre `0026_class_slots`. Crea `classes.class_sessions` (CHECK de estado, duración, cupo, nombre y
motivo; trío de cancelación junto), FK RESTRICT a `class_slots`, índice único parcial
`(slot_id, starts_at)` (solo con franja), índices por `starts_at` y `session_date`, la guarda
`classes.guard_sessions_update()` (solo `scheduled -> cancelled`, `cancel_*` una vez, identidad
inmutable) y los triggers de `DELETE` y `TRUNCATE`, todos `ENABLE ALWAYS`. Cada escenario corre en
una transacción que se revierte (SQL crudo con asyncpg).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_CLASS_SESSIONS, LIMPIAR_CLASS_SLOTS
from tests.migrations._apoyo_notificaciones import (
    CHECK_VIOLATION,
    UNIQUE_VIOLATION,
    columnas,
    consultar,
    existe,
    resultados,
)
from tests.migrations.test_0023_attachments import _ejecutar

REVISION = "0027_class_sessions"
PADRE = "0026_class_slots"
TABLA = "classes.class_sessions"
INMUTABLE = "P0001"
FK_VIOLATION = "23503"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
TRIGGERS = (
    "class_sessions_guard_update",
    "class_sessions_forbid_delete",
    "class_sessions_forbid_truncate",
)
INICIO = datetime(2026, 10, 26, 11, 0, tzinfo=UTC)

COLUMNAS = {
    "id": ("uuid", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
    "created_by": ("uuid", "NO"),
    "slot_id": ("uuid", "YES"),
    "session_date": ("date", "NO"),
    "starts_at": ("timestamp with time zone", "NO"),
    "duration_min": ("integer", "NO"),
    "capacity": ("integer", "NO"),
    "coach_id": ("uuid", "YES"),
    "name": ("text", "YES"),
    "wod_id": ("uuid", "YES"),
    "status": ("text", "NO"),
    "cancel_reason": ("text", "YES"),
    "cancelled_by": ("uuid", "YES"),
    "cancelled_at": ("timestamp with time zone", "YES"),
}

Paso = tuple[str, list[Any]]

ALTA_FRANJA = (
    "INSERT INTO classes.class_slots (id, created_by, weekdays, start_time, duration_min, "
    "capacity, valid_from) VALUES ($1, $2, '{0}'::smallint[], '06:00', 60, 15, '2026-10-01')"
)
ALTA_SESION = (
    "INSERT INTO classes.class_sessions (id, created_by, slot_id, session_date, starts_at, "
    "duration_min, capacity, name, status, cancel_reason, cancelled_by, cancelled_at) "
    "VALUES ($1, $2, $3, '2026-10-26', $4, $5, $6, $7, $8, $9, $10, $11)"
)


def _franja(slot: UUID) -> Paso:
    return ALTA_FRANJA, [slot, SYSTEM_USER_ID]


def _sesion(slot: UUID | None, **cambios: Any) -> Paso:
    v: dict[str, Any] = {
        "id": uuid4(),
        "starts": INICIO,
        "d": 60,
        "c": 15,
        "n": None,
        "status": "scheduled",
        "reason": None,
        "by": None,
        "at": None,
    }
    v.update(cambios)
    args = [
        v["id"],
        SYSTEM_USER_ID,
        slot,
        v["starts"],
        v["d"],
        v["c"],
        v["n"],
        v["status"],
        v["reason"],
        v["by"],
        v["at"],
    ]
    return ALTA_SESION, args


def _cancelada(slot: UUID | None, **cambios: Any) -> Paso:
    base = {"status": "cancelled", "reason": "Feriado", "by": SYSTEM_USER_ID, "at": INICIO}
    return _sesion(slot, **{**base, **cambios})


def _actualizar(sql: str, *args: Any) -> Paso:
    return sql, [*args]


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
    _revision_existe(alembic_config)
    try:
        yield migrated_database
    finally:
        if existe(migrated_database, TABLA):
            _ejecutar(migrated_database, LIMPIAR_CLASS_SESSIONS)
            _ejecutar(migrated_database, LIMPIAR_CLASS_SLOTS)


def test_la_revision_cuelga_de_0026_tiene_id_corto_y_esta_en_la_cadena(
    alembic_config: Config,
) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 31
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_las_columnas(base: str) -> None:
    assert columnas(base, TABLA) == COLUMNAS


def test_indices(base: str) -> None:
    filas = consultar(
        base,
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = 'classes' AND tablename = 'class_sessions'",
    )
    definiciones = " | ".join(f["indexdef"] for f in filas)
    assert "UNIQUE INDEX uq_class_sessions_slot_starts_at" in definiciones
    assert "(slot_id, starts_at) WHERE (slot_id IS NOT NULL)" in definiciones
    assert "ix_class_sessions_starts_at" in definiciones and "(starts_at)" in definiciones
    assert "ix_class_sessions_session_date" in definiciones and "(session_date)" in definiciones


def test_la_fk_a_la_franja_es_restrict(base: str) -> None:
    filas = consultar(
        base,
        "SELECT confdeltype::text AS tipo FROM pg_constraint "
        "WHERE conrelid = 'classes.class_sessions'::regclass AND contype = 'f'",
    )
    assert [f["tipo"] for f in filas] == ["r"]
    slot = uuid4()
    salidas = resultados(base, [[_franja(slot), _sesion(slot)], [_sesion(uuid4())]])
    assert salidas == [("", None), (FK_VIOLATION, "fk_class_sessions_slot_id_class_slots")]


def test_una_sesion_de_franja_y_una_extra_entran(base: str) -> None:
    slot = uuid4()
    salidas = resultados(
        base,
        [
            [_franja(slot), _sesion(slot, n="Fuerza", c=100, d=240)],
            [_sesion(None), _sesion(None)],  # extras a la misma hora: el índice solo cubre franjas
        ],
    )
    assert salidas == [("", None), ("", None)]


def test_unica_franja_y_hora(base: str) -> None:
    slot = uuid4()
    salidas = resultados(base, [[_franja(slot), _sesion(slot), _sesion(slot)]])
    assert salidas == [(UNIQUE_VIOLATION, "uq_class_sessions_slot_starts_at")]


def test_checks_de_estado_duracion_cupo_nombre_y_motivo(base: str) -> None:
    casos = [
        (_sesion(None, d=14), "ck_class_sessions_duration_min"),
        (_sesion(None, d=241), "ck_class_sessions_duration_min"),
        (_sesion(None, c=0), "ck_class_sessions_capacity"),
        (_sesion(None, c=101), "ck_class_sessions_capacity"),
        (_sesion(None, n=""), "ck_class_sessions_name_length"),
        (_sesion(None, n="x" * 41), "ck_class_sessions_name_length"),
        (_cancelada(None, reason=""), "ck_class_sessions_cancel_reason_length"),
        (_cancelada(None, reason="x" * 201), "ck_class_sessions_cancel_reason_length"),
    ]
    salidas = resultados(base, [[paso] for paso, _ in casos])
    assert salidas == [(CHECK_VIOLATION, nombre) for _, nombre in casos]


def test_el_estado_solo_admite_programada_o_cancelada(base: str) -> None:
    """`done` se calcula al leer: nunca se guarda (el trío de cancelación también lo rechaza)."""
    (salida,) = resultados(base, [[_sesion(None, status="done")]])
    assert salida[0] == CHECK_VIOLATION
    definicion = consultar(
        base,
        "SELECT pg_get_constraintdef(oid) AS d FROM pg_constraint "
        "WHERE conname = 'ck_class_sessions_status'",
    )
    assert "'scheduled'" in definicion[0]["d"] and "'cancelled'" in definicion[0]["d"]


def test_el_trio_de_cancelacion_va_junto(base: str) -> None:
    incompletas = [
        _cancelada(None, reason=None),
        _cancelada(None, by=None),
        _cancelada(None, at=None),
        _sesion(None, reason="Feriado"),  # scheduled con motivo
        _sesion(None, by=SYSTEM_USER_ID),
    ]
    salidas = resultados(base, [[p] for p in incompletas])
    assert salidas == [(CHECK_VIOLATION, "ck_class_sessions_cancel_trio")] * len(incompletas)
    assert resultados(base, [[_cancelada(None)]]) == [("", None)]


def test_cancelar_una_programada_se_puede(base: str) -> None:
    sid = uuid4()
    cancelar = _actualizar(
        "UPDATE classes.class_sessions SET status = 'cancelled', cancel_reason = 'Feriado', "
        "cancelled_by = $2, cancelled_at = now() WHERE id = $1",
        sid,
        SYSTEM_USER_ID,
    )
    assert resultados(base, [[_sesion(None, id=sid), cancelar]]) == [("", None)]


def test_no_se_descancela(base: str) -> None:
    sid = uuid4()
    reabrir = _actualizar(
        "UPDATE classes.class_sessions SET status = 'scheduled', cancel_reason = NULL, "
        "cancelled_by = NULL, cancelled_at = NULL WHERE id = $1",
        sid,
    )
    assert resultados(base, [[_cancelada(None, id=sid), reabrir]]) == [(INMUTABLE, None)]


def test_motivo_una_sola_vez(base: str) -> None:
    sid = uuid4()
    cambiar_motivo = _actualizar(
        "UPDATE classes.class_sessions SET cancel_reason = 'Otro' WHERE id = $1", sid
    )
    cambiar_quien = _actualizar(
        "UPDATE classes.class_sessions SET cancelled_by = $2 WHERE id = $1", sid, uuid4()
    )
    salidas = resultados(
        base,
        [[_cancelada(None, id=sid), cambiar_motivo], [_cancelada(None, id=sid), cambiar_quien]],
    )
    assert salidas == [(INMUTABLE, None)] * 2


@pytest.mark.parametrize(
    "asignacion",
    [
        "starts_at = starts_at + interval '1 hour'",
        "session_date = '2026-10-27'",
        "duration_min = 90",
        "capacity = 1",
        "coach_id = gen_random_uuid()",
        "name = 'Otra'",
        "created_by = gen_random_uuid()",
        "slot_id = NULL",
        "id = gen_random_uuid()",
    ],
)
def test_la_identidad_es_inmutable(base: str, asignacion: str) -> None:
    sid = uuid4()
    slot = uuid4()
    editar = _actualizar(f"UPDATE classes.class_sessions SET {asignacion} WHERE id = $1", sid)  # noqa: S608
    assert resultados(base, [[_franja(slot), _sesion(slot, id=sid), editar]]) == [(INMUTABLE, None)]


def test_wod_id_si_se_puede_asignar(base: str) -> None:
    """`wod_id` no es identidad: EP-22 lo llena (su GRANT llega con esa migración)."""
    sid = uuid4()
    asignar = _actualizar(
        "UPDATE classes.class_sessions SET wod_id = gen_random_uuid() WHERE id = $1", sid
    )
    assert resultados(base, [[_sesion(None, id=sid), asignar]]) == [("", None)]


def test_delete_y_truncate_estan_prohibidos(base: str) -> None:
    paso = _sesion(None)
    salidas = resultados(
        base,
        [
            [paso, ("DELETE FROM classes.class_sessions", [])],
            [paso, ("TRUNCATE classes.class_sessions CASCADE", [])],
            [paso, ("TRUNCATE classes.class_sessions", [])],
        ],
    )
    # Desde `0028` `classes.attendance` referencia a las sesiones: el `TRUNCATE` a secas choca con
    # esa FK (0A000) antes del trigger; con `CASCADE` la guarda corre y da P0001.
    assert [s for s, _ in salidas] == [INMUTABLE, INMUTABLE, "0A000"]


def test_los_tres_triggers_estan_en_always_y_la_guarda_es_invoker(base: str) -> None:
    filas = consultar(
        base,
        "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
        "WHERE tgrelid = 'classes.class_sessions'::regclass AND NOT tgisinternal",
    )
    assert {f["tgname"]: f["estado"] for f in filas} == dict.fromkeys(TRIGGERS, "A")
    definicion = consultar(
        base,
        "SELECT prosecdef, proconfig FROM pg_proc "
        "WHERE oid = 'classes.guard_sessions_update()'::regprocedure",
    )[0]
    assert definicion["prosecdef"] is False
    assert list(definicion["proconfig"]) == ["search_path=pg_catalog"]


def test_la_limpieza_deja_los_triggers_en_always(base: str) -> None:
    _ejecutar(base, LIMPIAR_CLASS_SESSIONS)
    filas = consultar(
        base,
        "SELECT tgenabled::text AS estado FROM pg_trigger WHERE tgname = ANY($1::text[])",
        list(TRIGGERS),
    )
    assert [f["estado"] for f in filas] == ["A"] * 3


def test_ciclo_head_base_head(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, "base")
        assert not existe(base, TABLA)
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)


def test_downgrade_a_0026_quita_sesiones_y_deja_las_franjas(
    alembic_config: Config, base: str
) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert not existe(base, TABLA)
        assert existe(base, "classes.class_slots")
        assert (
            consultar(
                base,
                "SELECT 1 FROM pg_proc "
                "WHERE oid::regprocedure::text = 'classes.guard_sessions_update()'",
            )
            == []
        )
        assert consultar(
            base,
            "SELECT 1 FROM pg_proc WHERE oid::regprocedure::text = 'classes.forbid_mutation()'",
        )
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)
