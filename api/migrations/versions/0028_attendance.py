"""Asistencia y fecha de Bogotá de las sesiones (S7-C1, US-159, US-161; S7-D13, S7-D37, M-3).

Revision ID: 0028_attendance
Revises: 0027_class_sessions
Create Date: 2026-11-14

Tabla `classes.attendance` (la asistencia de un socio a una sesión):
- comunes (`id`, `created_at`, `updated_at`, `created_by`);
- `session_id uuid` (FK `RESTRICT` a `classes.class_sessions`), `member_id uuid` (sin FK entre
  esquemas), `membership_id uuid` nulo (la membresía que decidió; para devolver la clase),
  `membership_status_at_checkin text`, `flags text[]`, `checked_in_at timestamptz`,
  `checked_in_by uuid` y `removed_at`, `removed_by`, `removed_reason` (borrado lógico, US-161);
- CHECK `ck_attendance_status_at_checkin` (los seis estados), `_flags` (`flags <@` las siete
  banderas: `expired`, `no_membership`, `frozen`, `pending_payment`, `over_capacity`,
  `out_of_window`, `other_day`), `_removed_reason_length` (nulo o de 1 a 200) y `_removed_pair`
  (`removed_at` y `removed_by` juntos; sin ellos tampoco hay motivo);
- índices: único parcial `uq_attendance_session_member_alive (session_id, member_id) WHERE
  removed_at IS NULL` (RN-10; dos tablets a la vez), `ix_attendance_member_checked_in (member_id,
  checked_in_at DESC) WHERE removed_at IS NULL` (última asistencia y ficha) e
  `ix_attendance_checked_in (checked_in_at) WHERE removed_at IS NULL` (semana, filtro y resumen);
- guarda `classes.guard_attendance()` (`BEFORE UPDATE`, `SECURITY INVOKER`, `search_path`
  `pg_catalog`): un `UPDATE` solo cambia `removed_*` y `updated_at`, y solo de `removed_at` nulo
  a no nulo (no se «desborra» ni se reescribe lo quitado);
- triggers `attendance_forbid_delete` y `attendance_forbid_truncate` sobre
  `classes.forbid_mutation()` (de `0026`). Los tres `ENABLE ALWAYS` (`tgenabled = 'A'`). La
  auditoría la hace el hook del ORM (`__audited__`, `__audit_subject__ = "member_id"`).

Además (S7-D37, 2): CHECK `ck_class_sessions_session_date_bogota` sobre `classes.class_sessions`
(`session_date = (starts_at AT TIME ZONE 'America/Bogota')::date`). `0027` ya estaba aplicada y no
se editó. Si alguna fila existente no lo cumpliera, el `ADD CONSTRAINT` falla y Alembic (DDL
transaccional) revierte todo; el service siempre calculó `session_date` desde `starts_at`.

`downgrade`: el CHECK de sesiones, los triggers, la guarda y la tabla. Las asistencias guardadas SE
PIERDEN al bajar (el volcado previo de P-MIG las conserva).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_attendance"
down_revision: str | None = "0027_class_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "classes"
TABLE: Final = "attendance"
IX_UNIQUE: Final = "uq_attendance_session_member_alive"
IX_MEMBER: Final = "ix_attendance_member_checked_in"
IX_CHECKED_IN: Final = "ix_attendance_checked_in"
SESSION_DATE_CHECK: Final = "session_date_bogota"

ESTADOS: Final = ("active", "expiring", "expired", "frozen", "pending_payment", "none")
BANDERAS: Final = (
    "expired",
    "no_membership",
    "frozen",
    "pending_payment",
    "over_capacity",
    "out_of_window",
    "other_day",
)


def _lista(valores: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in valores)


CHECKS: Final[tuple[tuple[str, str], ...]] = (
    ("status_at_checkin", f"membership_status_at_checkin IN ({_lista(ESTADOS)})"),
    ("flags", f"flags <@ ARRAY[{_lista(BANDERAS)}]::text[]"),
    (
        "removed_reason_length",
        "removed_reason IS NULL OR char_length(removed_reason) BETWEEN 1 AND 200",
    ),
    (
        "removed_pair",
        "(removed_at IS NULL AND removed_by IS NULL AND removed_reason IS NULL) "
        "OR (removed_at IS NOT NULL AND removed_by IS NOT NULL)",
    ),
)

CREATE_GUARD: Final = (
    "CREATE FUNCTION classes.guard_attendance() RETURNS trigger LANGUAGE plpgsql "
    "SECURITY INVOKER SET search_path = pg_catalog AS $$ "
    "BEGIN "
    "IF NEW.id IS DISTINCT FROM OLD.id "
    "OR NEW.session_id IS DISTINCT FROM OLD.session_id "
    "OR NEW.member_id IS DISTINCT FROM OLD.member_id "
    "OR NEW.membership_id IS DISTINCT FROM OLD.membership_id "
    "OR NEW.membership_status_at_checkin IS DISTINCT FROM OLD.membership_status_at_checkin "
    "OR NEW.flags IS DISTINCT FROM OLD.flags "
    "OR NEW.checked_in_at IS DISTINCT FROM OLD.checked_in_at "
    "OR NEW.checked_in_by IS DISTINCT FROM OLD.checked_in_by "
    "OR NEW.created_at IS DISTINCT FROM OLD.created_at "
    "OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN "
    "RAISE EXCEPTION 'classes.attendance: la asistencia registrada no cambia' "
    "USING ERRCODE = 'P0001'; END IF; "
    "IF OLD.removed_at IS NOT NULL AND (NEW.removed_at IS DISTINCT FROM OLD.removed_at "
    "OR NEW.removed_by IS DISTINCT FROM OLD.removed_by "
    "OR NEW.removed_reason IS DISTINCT FROM OLD.removed_reason) THEN "
    "RAISE EXCEPTION 'classes.attendance: una asistencia quitada no se modifica' "
    "USING ERRCODE = 'P0001'; END IF; "
    "RETURN NEW; END; $$"
)
CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER attendance_guard_update BEFORE UPDATE ON classes.attendance "
    "FOR EACH ROW EXECUTE FUNCTION classes.guard_attendance()",
    "CREATE TRIGGER attendance_forbid_delete BEFORE DELETE ON classes.attendance "
    "FOR EACH ROW EXECUTE FUNCTION classes.forbid_mutation()",
    "CREATE TRIGGER attendance_forbid_truncate BEFORE TRUNCATE ON classes.attendance "
    "FOR EACH STATEMENT EXECUTE FUNCTION classes.forbid_mutation()",
)
ENABLE_ALWAYS: Final[tuple[str, ...]] = tuple(
    f"ALTER TABLE classes.attendance ENABLE ALWAYS TRIGGER {nombre}"
    for nombre in (
        "attendance_guard_update",
        "attendance_forbid_delete",
        "attendance_forbid_truncate",
    )
)
DROP_TRIGGERS: Final[tuple[str, ...]] = (
    "DROP TRIGGER IF EXISTS attendance_forbid_truncate ON classes.attendance",
    "DROP TRIGGER IF EXISTS attendance_forbid_delete ON classes.attendance",
    "DROP TRIGGER IF EXISTS attendance_guard_update ON classes.attendance",
)


def common_columns() -> list[sa.Column[object]]:
    """Se declara dentro del archivo porque Alembic carga cada revisión por ruta."""
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        TABLE,
        *common_columns(),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("classes.class_sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("membership_status_at_checkin", sa.Text(), nullable=False),
        sa.Column("flags", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("checked_in_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("checked_in_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("removed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("removed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("removed_reason", sa.Text(), nullable=True),
        *[sa.CheckConstraint(texto, name=nombre) for nombre, texto in CHECKS],
        schema=SCHEMA,
    )
    op.create_index(
        IX_UNIQUE,
        TABLE,
        ["session_id", "member_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.create_index(
        IX_MEMBER,
        TABLE,
        ["member_id", sa.text("checked_in_at DESC")],
        schema=SCHEMA,
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.create_index(
        IX_CHECKED_IN,
        TABLE,
        ["checked_in_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.execute(CREATE_GUARD)
    for sentencia in (*CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)
    op.create_check_constraint(
        SESSION_DATE_CHECK,
        "class_sessions",
        "session_date = (starts_at AT TIME ZONE 'America/Bogota')::date",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(SESSION_DATE_CHECK, "class_sessions", schema=SCHEMA, type_="check")
    for sentencia in DROP_TRIGGERS:
        op.execute(sentencia)
    op.execute("DROP FUNCTION IF EXISTS classes.guard_attendance()")
    op.drop_index(IX_CHECKED_IN, table_name=TABLE, schema=SCHEMA)
    op.drop_index(IX_MEMBER, table_name=TABLE, schema=SCHEMA)
    op.drop_index(IX_UNIQUE, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
