"""`0028_attendance` (S7-C1, US-159, US-161; S7-D13, S7-D37, M-3). Rojo C1.

Padre `0027_class_sessions`. Crea `classes.attendance` (FK RESTRICT a las sesiones; CHECK de
estado, de las siete banderas, del motivo y del par `removed_*`; único parcial por sesión y socio
vivos; índices de ficha y de semana), la guarda `classes.guard_attendance()` (un `UPDATE` solo
cambia `removed_*` y `updated_at`, una vez; nunca se «desborra») y los triggers de `DELETE` y
`TRUNCATE`, todos `ENABLE ALWAYS`. Además suma el CHECK `ck_class_sessions_session_date_bogota`
(S7-D37). Cada escenario corre en una transacción que se revierte (SQL crudo con asyncpg).
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

from tests.conftest import LIMPIAR_ATTENDANCE, LIMPIAR_CLASS_SESSIONS, LIMPIAR_CLASS_SLOTS
from tests.migrations._apoyo_notificaciones import (
    CHECK_VIOLATION,
    UNIQUE_VIOLATION,
    columnas,
    consultar,
    existe,
    resultados,
)
from tests.migrations.test_0023_attachments import _ejecutar

REVISION = "0028_attendance"
PADRE = "0027_class_sessions"
TABLA = "classes.attendance"
INMUTABLE = "P0001"
FK_VIOLATION = "23503"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
TRIGGERS = ("attendance_guard_update", "attendance_forbid_delete", "attendance_forbid_truncate")
INICIO = datetime(2026, 10, 26, 11, 0, tzinfo=UTC)  # 06:00 del 26 en Bogotá
SIETE = [
    "expired",
    "no_membership",
    "frozen",
    "pending_payment",
    "over_capacity",
    "out_of_window",
    "other_day",
]

COLUMNAS = {
    "id": ("uuid", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
    "created_by": ("uuid", "NO"),
    "session_id": ("uuid", "NO"),
    "member_id": ("uuid", "NO"),
    "membership_id": ("uuid", "YES"),
    "membership_status_at_checkin": ("text", "NO"),
    "flags": ("ARRAY", "NO"),
    "checked_in_at": ("timestamp with time zone", "NO"),
    "checked_in_by": ("uuid", "NO"),
    "removed_at": ("timestamp with time zone", "YES"),
    "removed_by": ("uuid", "YES"),
    "removed_reason": ("text", "YES"),
}

Paso = tuple[str, list[Any]]

ALTA_SESION = (
    "INSERT INTO classes.class_sessions (id, created_by, session_date, starts_at, duration_min, "
    "capacity) VALUES ($1, $2, '2026-10-26', $3, 60, 15)"
)
ALTA_ASISTENCIA = (
    "INSERT INTO classes.attendance (id, created_by, session_id, member_id, membership_id, "
    "membership_status_at_checkin, flags, checked_in_at, checked_in_by, removed_at, removed_by, "
    "removed_reason) VALUES ($1, $2, $3, $4, NULL, $5, $6::text[], $7, $2, $8, $9, $10)"
)


def _sesion(sid: UUID) -> Paso:
    return ALTA_SESION, [sid, SYSTEM_USER_ID, INICIO]


def _asistencia(sid: UUID, **cambios: Any) -> Paso:
    v: dict[str, Any] = {
        "id": uuid4(),
        "member": uuid4(),
        "status": "expired",
        "flags": ["expired"],
        "removed_at": None,
        "removed_by": None,
        "reason": None,
    }
    v.update(cambios)
    return ALTA_ASISTENCIA, [
        v["id"],
        SYSTEM_USER_ID,
        sid,
        v["member"],
        v["status"],
        v["flags"],
        INICIO,
        v["removed_at"],
        v["removed_by"],
        v["reason"],
    ]


def _quitada(sid: UUID, **cambios: Any) -> Paso:
    base = {"removed_at": INICIO, "removed_by": SYSTEM_USER_ID, "reason": "Error de dedo"}
    return _asistencia(sid, **{**base, **cambios})


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
            _ejecutar(migrated_database, LIMPIAR_ATTENDANCE)
            _ejecutar(migrated_database, LIMPIAR_CLASS_SESSIONS)
            _ejecutar(migrated_database, LIMPIAR_CLASS_SLOTS)


def test_la_revision_cuelga_de_0027_tiene_id_corto_y_esta_en_la_cadena(
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
        "SELECT indexdef FROM pg_indexes WHERE schemaname = 'classes' AND tablename = 'attendance'",
    )
    definiciones = " | ".join(f["indexdef"] for f in filas)
    assert "UNIQUE INDEX uq_attendance_session_member_alive" in definiciones
    assert "(session_id, member_id) WHERE (removed_at IS NULL)" in definiciones
    assert "ix_attendance_member_checked_in" in definiciones
    assert "(member_id, checked_in_at DESC) WHERE (removed_at IS NULL)" in definiciones
    assert "ix_attendance_checked_in" in definiciones
    assert "(checked_in_at) WHERE (removed_at IS NULL)" in definiciones


def test_la_fk_a_la_sesion_es_restrict(base: str) -> None:
    filas = consultar(
        base,
        "SELECT confdeltype::text AS tipo FROM pg_constraint "
        "WHERE conrelid = 'classes.attendance'::regclass AND contype = 'f'",
    )
    assert [f["tipo"] for f in filas] == ["r"]
    sid = uuid4()
    salidas = resultados(base, [[_sesion(sid), _asistencia(sid)], [_asistencia(uuid4())]])
    assert salidas == [("", None), (FK_VIOLATION, "fk_attendance_session_id_class_sessions")]


def test_no_se_borra_una_sesion_con_asistencias(base: str) -> None:
    sid = uuid4()
    borrar = ("DELETE FROM classes.class_sessions WHERE id = $1", [sid])
    (salida,) = resultados(base, [[_sesion(sid), _asistencia(sid), borrar]])
    assert salida[0] == INMUTABLE  # el trigger de la sesión lo ataja antes que la FK


def test_check_de_estado_y_de_flags_con_siete_valores(base: str) -> None:
    sid = uuid4()
    casos = [
        _asistencia(sid, status="done"),
        _asistencia(sid, status="vencida"),
        _asistencia(sid, flags=["flagged"]),
        _asistencia(sid, flags=["expired", "otra"]),
    ]
    salidas = resultados(base, [[_sesion(sid), caso] for caso in casos])
    assert [s for s, _ in salidas] == [CHECK_VIOLATION] * 4
    assert [n for _, n in salidas] == [
        "ck_attendance_status_at_checkin",
        "ck_attendance_status_at_checkin",
        "ck_attendance_flags",
        "ck_attendance_flags",
    ]
    todos = [[_sesion(sid), _asistencia(sid, flags=SIETE)]]
    sin_banderas = [[_sesion(sid), _asistencia(sid, status="active", flags=[])]]
    assert resultados(base, todos + sin_banderas) == [("", None), ("", None)]
    estados = [
        [_sesion(sid), _asistencia(sid, status=e)]
        for e in ("active", "expiring", "expired", "frozen", "pending_payment", "none")
    ]
    assert resultados(base, estados) == [("", None)] * 6


def test_motivo_y_par_de_quitada(base: str) -> None:
    sid = uuid4()
    casos = [
        (_quitada(sid, reason=""), "ck_attendance_removed_reason_length"),
        (_quitada(sid, reason="x" * 201), "ck_attendance_removed_reason_length"),
        (_quitada(sid, removed_by=None), "ck_attendance_removed_pair"),
        (_quitada(sid, removed_at=None), "ck_attendance_removed_pair"),
        (_asistencia(sid, reason="sin quitar"), "ck_attendance_removed_pair"),
    ]
    salidas = resultados(base, [[_sesion(sid), paso] for paso, _ in casos])
    assert salidas == [(CHECK_VIOLATION, nombre) for _, nombre in casos]
    # sin motivo es válido: el motivo es opcional (US-161)
    assert resultados(base, [[_sesion(sid), _quitada(sid, reason=None)]]) == [("", None)]


def test_unico_parcial_solo_entre_vivas(base: str) -> None:
    sid, socio = uuid4(), uuid4()
    repetida = [_sesion(sid), _asistencia(sid, member=socio), _asistencia(sid, member=socio)]
    con_quitada = [
        _sesion(sid),
        _quitada(sid, member=socio),
        _asistencia(sid, member=socio),  # volver a registrar tras quitar (CA5 de US-161)
        _quitada(sid, member=socio),  # dos quitadas del mismo socio conviven
    ]
    otra_sesion = [
        _sesion(sid),
        _asistencia(sid, member=socio),
        _sesion(uuid4()),
    ]
    salidas = resultados(base, [repetida, con_quitada, otra_sesion])
    assert salidas == [
        (UNIQUE_VIOLATION, "uq_attendance_session_member_alive"),
        ("", None),
        ("", None),
    ]


def test_update_solo_removed(base: str) -> None:
    sid, aid = uuid4(), uuid4()
    quitar = (
        "UPDATE classes.attendance SET removed_at = now(), removed_by = $2, "
        "removed_reason = 'Error', updated_at = now() WHERE id = $1",
        [aid, SYSTEM_USER_ID],
    )
    assert resultados(base, [[_sesion(sid), _asistencia(sid, id=aid), quitar]]) == [("", None)]


@pytest.mark.parametrize(
    "asignacion",
    [
        "flags = ARRAY[]::text[]",
        "membership_status_at_checkin = 'active'",
        "membership_id = gen_random_uuid()",
        "member_id = gen_random_uuid()",
        "session_id = gen_random_uuid()",
        "checked_in_at = now()",
        "checked_in_by = gen_random_uuid()",
        "created_by = gen_random_uuid()",
        "id = gen_random_uuid()",
    ],
)
def test_la_identidad_es_inmutable(base: str, asignacion: str) -> None:
    sid, aid = uuid4(), uuid4()
    editar = (f"UPDATE classes.attendance SET {asignacion} WHERE id = $1", [aid])  # noqa: S608
    assert resultados(base, [[_sesion(sid), _asistencia(sid, id=aid), editar]]) == [
        (INMUTABLE, None)
    ]


def test_no_se_desborra_ni_se_reescribe_lo_quitado(base: str) -> None:
    sid, aid = uuid4(), uuid4()
    desborrar = (
        "UPDATE classes.attendance SET removed_at = NULL, removed_by = NULL, "
        "removed_reason = NULL WHERE id = $1",
        [aid],
    )
    cambiar_motivo = (
        "UPDATE classes.attendance SET removed_reason = 'Otro' WHERE id = $1",
        [aid],
    )
    cambiar_quien = (
        "UPDATE classes.attendance SET removed_by = $2 WHERE id = $1",
        [aid, uuid4()],
    )
    salidas = resultados(
        base,
        [
            [_sesion(sid), _quitada(sid, id=aid), desborrar],
            [_sesion(sid), _quitada(sid, id=aid), cambiar_motivo],
            [_sesion(sid), _quitada(sid, id=aid), cambiar_quien],
        ],
    )
    assert salidas == [(INMUTABLE, None)] * 3


def test_delete_y_truncate_estan_prohibidos(base: str) -> None:
    sid = uuid4()
    salidas = resultados(
        base,
        [
            [_sesion(sid), _asistencia(sid), ("DELETE FROM classes.attendance", [])],
            [_sesion(sid), _asistencia(sid), ("TRUNCATE classes.attendance", [])],
        ],
    )
    assert [s for s, _ in salidas] == [INMUTABLE, INMUTABLE]


def test_los_tres_triggers_estan_en_always_y_la_guarda_es_invoker(base: str) -> None:
    filas = consultar(
        base,
        "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
        "WHERE tgrelid = 'classes.attendance'::regclass AND NOT tgisinternal",
    )
    assert {f["tgname"]: f["estado"] for f in filas} == dict.fromkeys(TRIGGERS, "A")
    definicion = consultar(
        base,
        "SELECT prosecdef, proconfig FROM pg_proc "
        "WHERE oid = 'classes.guard_attendance()'::regprocedure",
    )[0]
    assert definicion["prosecdef"] is False
    assert list(definicion["proconfig"]) == ["search_path=pg_catalog"]


def test_la_limpieza_deja_los_triggers_en_always(base: str) -> None:
    _ejecutar(base, LIMPIAR_ATTENDANCE)
    _ejecutar(base, LIMPIAR_CLASS_SESSIONS)
    filas = consultar(
        base,
        "SELECT tgenabled::text AS estado FROM pg_trigger WHERE tgname = ANY($1::text[])",
        list(TRIGGERS),
    )
    assert [f["estado"] for f in filas] == ["A"] * 3


def test_la_sesion_guarda_su_fecha_de_bogota_s7_d37(base: str) -> None:
    """S7-D37 (2): `session_date = (starts_at AT TIME ZONE 'America/Bogota')::date`."""
    # 2026-10-26 03:00Z es el 25 a las 22:00 en Bogotá: la fecha 26 no cuadra.
    desfasada = (ALTA_SESION, [uuid4(), SYSTEM_USER_ID, datetime(2026, 10, 26, 3, 0, tzinfo=UTC)])
    cuadra = (ALTA_SESION, [uuid4(), SYSTEM_USER_ID, datetime(2026, 10, 26, 5, 0, tzinfo=UTC)])
    salidas = resultados(base, [[desfasada], [cuadra]])
    assert salidas == [(CHECK_VIOLATION, "ck_class_sessions_session_date_bogota"), ("", None)]


def test_ciclo_head_base_head(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, "base")
        assert not existe(base, TABLA)
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)


def test_downgrade_a_0027_quita_asistencia_y_el_check_y_deja_las_sesiones(
    alembic_config: Config, base: str
) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert not existe(base, TABLA)
        assert existe(base, "classes.class_sessions")
        assert (
            consultar(
                base,
                "SELECT 1 FROM pg_proc "
                "WHERE oid::regprocedure::text = 'classes.guard_attendance()'",
            )
            == []
        )
        assert (
            consultar(
                base,
                "SELECT 1 FROM pg_constraint "
                "WHERE conname = 'ck_class_sessions_session_date_bogota'",
            )
            == []
        )
    finally:
        command.upgrade(alembic_config, "head")
    assert existe(base, TABLA)
