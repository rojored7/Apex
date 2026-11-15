"""`0029_memberships_orig_end_date` (S7-C2, US-160; S7-D14, S7-D29, S7-D2). Rojo C2.

Padre `0028_attendance`. Suma `memberships.memberships.original_end_date date NULL` con el CHECK
`ck_memberships_original_end_date_needs_classes` y el CHECK `ck_attendance_membership_pair` de
`classes.attendance` (`(estado = 'none') = (membership_id IS NULL)`), con una consulta previa que
aborta con el conteo si hay filas que lo violen. Los CHECK de `classes_remaining` de `0008` siguen.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_ATTENDANCE, LIMPIAR_CLASS_SESSIONS, LIMPIAR_CLASS_SLOTS
from tests.migrations._apoyo_notificaciones import (
    CHECK_VIOLATION,
    columnas,
    consultar,
    resultados,
)
from tests.migrations.test_0023_attachments import _ejecutar

REVISION = "0029_memberships_orig_end_date"
PADRE = "0028_attendance"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
INICIO = datetime(2026, 10, 26, 11, 0, tzinfo=UTC)

Paso = tuple[str, list[Any]]

ALTA_SESION = (
    "INSERT INTO classes.class_sessions (id, created_by, session_date, starts_at, duration_min, "
    "capacity) VALUES ($1, $2, '2026-10-26', $3, 60, 15)"
)
ALTA_ASISTENCIA = (
    "INSERT INTO classes.attendance (id, created_by, session_id, member_id, membership_id, "
    "membership_status_at_checkin, flags, checked_in_at, checked_in_by) "
    "VALUES ($1, $2, $3, $4, $5, $6, '{}'::text[], $7, $2)"
)
ALTA_PLAN = (
    "INSERT INTO plans.plans (id, created_by, name, price_cop, kind, duration_days, class_count, "
    "is_active) VALUES ($1, $2, $3, 100000, $4, 60, $5, true)"
)
ALTA_MEMBRESIA = (
    "INSERT INTO memberships.memberships (id, created_by, member_id, plan_id, agreed_price_cop, "
    "start_date, end_date, classes_total, classes_remaining, status, original_end_date) "
    "VALUES ($1, $2, $3, $4, 100000, '2026-10-01', '2026-11-30', $5, $6, 'active', $7)"
)


def _asistencia(sid: UUID, estado: str, membership_id: UUID | None) -> Paso:
    return ALTA_ASISTENCIA, [uuid4(), SYSTEM_USER_ID, sid, uuid4(), membership_id, estado, INICIO]


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
        _ejecutar(migrated_database, LIMPIAR_ATTENDANCE)
        _ejecutar(migrated_database, LIMPIAR_CLASS_SESSIONS)
        _ejecutar(migrated_database, LIMPIAR_CLASS_SLOTS)


def test_la_revision_cuelga_de_0028_tiene_id_corto_y_esta_en_la_cadena(
    alembic_config: Config,
) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_la_columna_es_date_nula(base: str) -> None:
    assert columnas(base, "memberships.memberships")["original_end_date"] == ("date", "YES")


def test_checks_de_0008_siguen(base: str) -> None:
    filas = consultar(
        base,
        "SELECT conname FROM pg_constraint WHERE conrelid = 'memberships.memberships'::regclass "
        "AND contype = 'c'",
    )
    nombres = {f["conname"] for f in filas}
    assert {
        "ck_memberships_classes_pair",
        "ck_memberships_classes_remaining_non_negative",
        "ck_memberships_classes_remaining_le_total",
    } <= nombres


def test_check_nuevo_de_la_tiquetera(base: str) -> None:
    """Solo una tiquetera (`classes_total` no nulo) puede tener `original_end_date`."""
    socio, por_dias, por_clases = uuid4(), uuid4(), uuid4()
    altas = [
        (ALTA_PLAN, [por_dias, SYSTEM_USER_ID, "Prueba 0029 dias", "days", None]),
        (ALTA_PLAN, [por_clases, SYSTEM_USER_ID, "Prueba 0029 clases", "classes", 12]),
    ]
    fin = date(2026, 12, 15)
    malo = (
        ALTA_MEMBRESIA,
        [uuid4(), SYSTEM_USER_ID, socio, por_dias, None, None, fin],
    )
    bueno = (
        ALTA_MEMBRESIA,
        [uuid4(), SYSTEM_USER_ID, socio, por_clases, 12, 3, fin],
    )
    salidas = resultados(base, [[*altas, malo], [*altas, bueno]])
    assert salidas[0] == (CHECK_VIOLATION, "ck_memberships_original_end_date_needs_classes")
    assert salidas[1] == ("", None)


def test_check_del_par_de_la_asistencia(base: str) -> None:
    """`ck_attendance_membership_pair`: estado `none` sin id; cualquier otro estado, con id."""
    sid = uuid4()
    sesion = (ALTA_SESION, [sid, SYSTEM_USER_ID, INICIO])
    casos = [
        _asistencia(sid, "none", uuid4()),
        _asistencia(sid, "expired", None),
        _asistencia(sid, "none", None),
        _asistencia(sid, "active", uuid4()),
    ]
    salidas = resultados(base, [[sesion, caso] for caso in casos])
    assert salidas == [
        (CHECK_VIOLATION, "ck_attendance_membership_pair"),
        (CHECK_VIOLATION, "ck_attendance_membership_pair"),
        ("", None),
        ("", None),
    ]


def test_ciclo_head_base_head(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, "base")
    finally:
        command.upgrade(alembic_config, "head")
    assert columnas(base, "memberships.memberships")["original_end_date"] == ("date", "YES")


def test_downgrade_a_0028_quita_columna_y_checks(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert "original_end_date" not in columnas(base, "memberships.memberships")
        nombres = {
            f["conname"]
            for f in consultar(
                base,
                "SELECT conname FROM pg_constraint WHERE conname IN "
                "('ck_attendance_membership_pair', "
                "'ck_memberships_original_end_date_needs_classes')",
            )
        }
        assert nombres == set()
    finally:
        command.upgrade(alembic_config, "head")


def test_upgrade_aborta_con_el_conteo_si_hay_pares_malos(alembic_config: Config, base: str) -> None:
    """Con una asistencia que viola el par, `0029` aborta nombrando el conteo y no cambia nada."""
    sid = uuid4()
    try:
        command.downgrade(alembic_config, PADRE)
        _ejecutar_pasos(
            base,
            [(ALTA_SESION, [sid, SYSTEM_USER_ID, INICIO]), _asistencia(sid, "expired", None)],
        )
        with pytest.raises(RuntimeError, match=r"1 asistencia"):
            command.upgrade(alembic_config, REVISION)
        assert "original_end_date" not in columnas(base, "memberships.memberships")
    finally:
        _ejecutar(base, LIMPIAR_ATTENDANCE)
        command.upgrade(alembic_config, "head")


def _ejecutar_pasos(url: str, pasos: list[Paso]) -> None:
    """Corre los pasos con commit (a diferencia de `resultados`, que revierte)."""

    async def correr() -> None:
        conexion = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://", 1))
        try:
            for sql, args in pasos:
                await conexion.execute(sql, *args)
        finally:
            await conexion.close()

    asyncio.run(correr())
