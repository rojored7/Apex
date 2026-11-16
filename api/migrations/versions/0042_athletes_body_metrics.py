"""Esquema `athletes` y `athletes.body_metrics` (S9-A1, US-178; S9-D2, S9-D3, S9-D31).

Revision ID: 0042_athletes_body_metrics
Revises: 0041_results_session_index
Create Date: 2026-11-16

Tabla `athletes.body_metrics`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`);
- `member_id` (sin FK entre esquemas), `measured_on` (fecha civil de Bogotá), `recorded_by`;
- cuatro columnas cifradas `TEXT NULL` (`weight_g`, `height_cm`, `body_fat_pct`, `notes`), todas
  con blob `apx1.*` de la clase `athlete.metric` (la clase y el modelo `Encrypted` van en el
  mismo checkpoint, S9-D5);
- `voided_at` y `voided_by` (anulación, S9-D13);
- CHECK `at_least_one_measure` (al menos una de las tres medidas; la nulidad de un blob sí se ve)
  y `voided_pair` (las dos columnas de anulación van juntas o ninguna);
- índice `(member_id, measured_on DESC, created_at DESC)`.

Guardas (`SECURITY INVOKER`, `search_path = pg_catalog`, `ENABLE ALWAYS`, S9-D31):
- `body_metrics_guard_insert`: nace sin `voided_*` y cada blob no nulo con la forma completa
  (`apx1.<uuid>.A256GCM.<nonce de 12 bytes>.<texto>`) y una llave `encrypt` de la clase (`active`
  o `decrypt_only`: una rotación entre el cifrado y el INSERT no da un 500);
- `body_metrics_guard_update`: `id`, `member_id`, `measured_on`, `recorded_by` y `created_*` no
  cambian; `updated_at` no retrocede; `voided_*` solo pasan de NULL a valor (las dos a la vez); un
  blob solo cambia en un RECIFRADO: misma nulidad, forma completa, llave `active` de la clase y
  DISTINTA de la del blob viejo, `length(NEW) = length(OLD)` en las tres columnas de ancho fijo
  (no en `notes`) y sin anular en el mismo UPDATE. Una fila anulada SÍ se recifra (`retire-key`);
- `body_metrics_forbid_delete` y `body_metrics_forbid_truncate`: nunca se borra.
La auditoría la hace el hook del ORM (`__audited__`), no un trigger por tabla.

`downgrade`: triggers, funciones, tabla y esquema; las mediciones guardadas SE PIERDEN (volcado
previo `sprint-09-antes-0042.dump`, P-MIG 1). NO borra la fila de la clase `athlete.metric` de
`crypto.crypto_keys` (ni sus `crypto_ops`) ni los blobs de `athletes.body_metrics` que quedaron
en `audit.audit_log`: ambos son append-only o de llaves (regla de datos 4); una v0.5.0 debe
arrancar con esa fila de clase desconocida (V3). SQL literal, sin interpolación.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042_athletes_body_metrics"
down_revision: str | None = "0041_results_session_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "athletes"
TABLE: Final = "body_metrics"
IX_MEMBER: Final = "ix_body_metrics_member_date"
TRIGGERS: Final[tuple[str, ...]] = (
    "body_metrics_guard_insert",
    "body_metrics_guard_update",
    "body_metrics_forbid_delete",
    "body_metrics_forbid_truncate",
)
FN_HEAD: Final = "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$ "

# Forma completa del blob del bus (core/crypto/blob.py): llave UUID en minúsculas, algoritmo
# A256GCM, nonce de 12 bytes (16 caracteres base64url sin relleno) y texto cifrado de al menos 22
# caracteres (la etiqueta GCM de 16 bytes ya los ocupa; L-2 de la revisión de A1).
BLOB_REGEX: Final = (
    "^apx1[.][0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    "[.]A256GCM[.][A-Za-z0-9_-]{16}[.][A-Za-z0-9_-]{22,}$"
)

# Las comprobaciones de blob van DENTRO de cada guarda (sin funciones auxiliares): no hay EXECUTE
# que otorgar a `apex_api` en el esquema `athletes`.
# Estado de la llave `encrypt` de `athlete.metric` a la que apunta el blob `b`; NULL si `b` no
# tiene la forma completa (el `CASE` evita convertir a `uuid` un texto que no lo es: sale la
# guarda, no 22P02). `FOR SHARE OF k` (M-1 de la revisión de A1): un `retire-key` concurrente
# (`FOR UPDATE` de la fila de la llave) espera a que confirme el INSERT o el recifrado que la usó,
# y su conteo ya ve la fila; `apex_api` lo puede (`UPDATE (state, ...)` de `crypto_keys`).
# Texto constante, sin datos de usuario.
STATE_OF: Final = (
    "(CASE WHEN b ~ '" + BLOB_REGEX + "' THEN (SELECT k.state FROM crypto.crypto_keys k "  # noqa: S608
    "WHERE k.id = split_part(b, '.', 2)::uuid AND k.purpose = 'encrypt' "
    "AND k.data_class = 'athlete.metric' FOR SHARE OF k) END)"
)
CREATE_FUNCTIONS: Final[tuple[str, ...]] = (
    "CREATE FUNCTION athletes.guard_body_metrics_insert() RETURNS trigger " + FN_HEAD + "DECLARE "
    "b text; BEGIN "
    "IF NEW.voided_at IS NOT NULL OR NEW.voided_by IS NOT NULL THEN "
    "RAISE EXCEPTION 'athletes.body_metrics: una medicion nunca nace anulada' "
    "USING ERRCODE = 'P0001'; END IF; "
    "FOREACH b IN ARRAY ARRAY[NEW.weight_g, NEW.height_cm, NEW.body_fat_pct, NEW.notes] LOOP "
    "IF b IS NOT NULL AND NOT coalesce(" + STATE_OF + " "
    "IN ('active', 'decrypt_only'), false) THEN "
    "RAISE EXCEPTION 'athletes.body_metrics: blob sin la forma o la llave de la clase' "
    "USING ERRCODE = 'P0001'; END IF; END LOOP; "
    "RETURN NEW; END; $$",
    "CREATE FUNCTION athletes.guard_body_metrics_update() RETURNS trigger " + FN_HEAD + "DECLARE "
    "olds text[]; news text[]; b text; i int; BEGIN "
    "IF NEW.id IS DISTINCT FROM OLD.id "
    "OR NEW.created_at IS DISTINCT FROM OLD.created_at "
    "OR NEW.created_by IS DISTINCT FROM OLD.created_by "
    "OR NEW.member_id IS DISTINCT FROM OLD.member_id "
    "OR NEW.measured_on IS DISTINCT FROM OLD.measured_on "
    "OR NEW.recorded_by IS DISTINCT FROM OLD.recorded_by THEN "
    "RAISE EXCEPTION 'athletes.body_metrics: la medicion registrada no cambia' "
    "USING ERRCODE = 'P0001'; END IF; "
    "IF NEW.updated_at < OLD.updated_at THEN "
    "RAISE EXCEPTION 'athletes.body_metrics: updated_at no retrocede' "
    "USING ERRCODE = 'P0001'; END IF; "
    "olds := ARRAY[OLD.weight_g, OLD.height_cm, OLD.body_fat_pct, OLD.notes]; "
    "news := ARRAY[NEW.weight_g, NEW.height_cm, NEW.body_fat_pct, NEW.notes]; "
    "IF NEW.voided_at IS DISTINCT FROM OLD.voided_at "
    "OR NEW.voided_by IS DISTINCT FROM OLD.voided_by THEN "
    "IF NOT (OLD.voided_at IS NULL AND OLD.voided_by IS NULL "
    "AND NEW.voided_at IS NOT NULL AND NEW.voided_by IS NOT NULL) THEN "
    "RAISE EXCEPTION 'athletes.body_metrics: la anulacion es terminal' "
    "USING ERRCODE = 'P0001'; END IF; "
    "IF news IS DISTINCT FROM olds THEN "
    "RAISE EXCEPTION 'athletes.body_metrics: recifrar y anular no van juntos' "
    "USING ERRCODE = 'P0001'; END IF; END IF; "
    # Recifrado (S9-D31): solo cambia un blob con la misma nulidad, la forma completa, la llave
    # `active` de la clase DISTINTA de la vieja y, en las tres de ancho fijo (i = 1 a 3), el mismo
    # largo. `notes` (i = 4) no es de ancho fijo.
    "FOR i IN 1..4 LOOP "
    "IF news[i] IS DISTINCT FROM olds[i] THEN b := news[i]; "
    "IF (news[i] IS NULL) <> (olds[i] IS NULL) "
    "OR NOT coalesce(" + STATE_OF + " = 'active' "
    "AND split_part(news[i], '.', 2) <> split_part(olds[i], '.', 2) "
    "AND (i = 4 OR length(news[i]) = length(olds[i])), false) THEN "
    "RAISE EXCEPTION 'athletes.body_metrics: solo se recifra con la llave activa y distinta' "
    "USING ERRCODE = 'P0001'; END IF; END IF; END LOOP; "
    "RETURN NEW; END; $$",
    "CREATE FUNCTION athletes.forbid_mutation() RETURNS trigger " + FN_HEAD + "BEGIN "
    "RAISE EXCEPTION 'athletes.% nunca se borran (% prohibido)', TG_TABLE_NAME, TG_OP "
    "USING ERRCODE = 'P0001'; END; $$",
)
CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER body_metrics_guard_insert BEFORE INSERT ON athletes.body_metrics "
    "FOR EACH ROW EXECUTE FUNCTION athletes.guard_body_metrics_insert()",
    "CREATE TRIGGER body_metrics_guard_update BEFORE UPDATE ON athletes.body_metrics "
    "FOR EACH ROW EXECUTE FUNCTION athletes.guard_body_metrics_update()",
    "CREATE TRIGGER body_metrics_forbid_delete BEFORE DELETE ON athletes.body_metrics "
    "FOR EACH ROW EXECUTE FUNCTION athletes.forbid_mutation()",
    "CREATE TRIGGER body_metrics_forbid_truncate BEFORE TRUNCATE ON athletes.body_metrics "
    "FOR EACH STATEMENT EXECUTE FUNCTION athletes.forbid_mutation()",
)
ENABLE_ALWAYS: Final[tuple[str, ...]] = tuple(
    f"ALTER TABLE athletes.body_metrics ENABLE ALWAYS TRIGGER {nombre}" for nombre in TRIGGERS
)
DROP_FUNCTIONS: Final[tuple[str, ...]] = (
    "DROP FUNCTION IF EXISTS athletes.forbid_mutation()",
    "DROP FUNCTION IF EXISTS athletes.guard_body_metrics_update()",
    "DROP FUNCTION IF EXISTS athletes.guard_body_metrics_insert()",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS athletes")
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weight_g", sa.Text(), nullable=True),
        sa.Column("height_cm", sa.Text(), nullable=True),
        sa.Column("body_fat_pct", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("voided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("voided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "weight_g IS NOT NULL OR height_cm IS NOT NULL OR body_fat_pct IS NOT NULL",
            name="at_least_one_measure",
        ),
        sa.CheckConstraint("(voided_at IS NULL) = (voided_by IS NULL)", name="voided_pair"),
        schema=SCHEMA,
    )
    op.create_index(
        IX_MEMBER,
        TABLE,
        ["member_id", sa.text("measured_on DESC"), sa.text("created_at DESC")],
        schema=SCHEMA,
    )
    for sentencia in (*CREATE_FUNCTIONS, *CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)


def downgrade() -> None:
    for nombre in reversed(TRIGGERS):
        op.execute(f"DROP TRIGGER IF EXISTS {nombre} ON athletes.body_metrics")
    for sentencia in DROP_FUNCTIONS:
        op.execute(sentencia)
    op.drop_index(IX_MEMBER, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
    op.execute("DROP SCHEMA IF EXISTS athletes RESTRICT")
