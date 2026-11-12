"""Rotación de llaves desde el api: guardas por rol en `crypto_keys` y `crypto_jobs` (S6-R1).

Revision ID: 0024_crypto_rotation_from_api
Revises: 0023_attachments
Create Date: 2026-11-12

Contexto (S6-D43, S6-D61, S6-D121, H-2, E2, E6): la rotación sale del CLI y corre en el api como
`apex_api`. El rol gana `INSERT` en `crypto.crypto_jobs` y `UPDATE` por columna del progreso (y de
`state`, `rotated_*` en `crypto.crypto_keys`; los `GRANT` viven en `infra/db/grants.sql`). Estas
guardas acotan lo que ese rol puede hacer con ellos. Para el propietario (CLI, `tools`) nada cambia.

- `crypto.guard_keys_update()` (reemplazo del cuerpo de `0015`; misma firma, `SECURITY INVOKER`,
  `SET search_path = pg_catalog`). Sigue siendo la función de `crypto_keys_guard` (BEFORE, fila) y
  de `crypto_keys_forbid_truncate`; suma la rama de `apex_api` y se registra también como
  `crypto_keys_guard_cierre`, un `CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED` (AFTER
  `UPDATE`). `TG_WHEN` distingue las dos pasadas:
  * BEFORE (inmediata): `apex_api` solo pasa una llave `encrypt` de `active` a `decrypt_only`, con
    `rotated_by` un usuario real de `auth.users` distinto del técnico y sin tocar `provider` ni
    `wrapped_material`. Nada sobre filas `sign` o `index` (E2), nunca `retired` ni reactivar.
  * AFTER diferida (al `COMMIT` o a `SET CONSTRAINTS ... IMMEDIATE`): existe otra fila `active` de
    la misma clase y propósito con `version` mayor y un `crypto_jobs` `rotate` `running` de la
    clase. `uq_crypto_keys_active` obliga a pasar la anterior a `decrypt_only` ANTES de insertar la
    nueva, así que esa condición solo puede comprobarse al cierre (S6-D121).
  [DECISIÓN DE DISEÑO] Las comprobaciones de `0003`/`0015` (inmutabilidad, truncado, transiciones
  del propietario) siguen siendo inmediatas: convertir todo el trigger en diferido haría que
  `0003`/`0014`/`0015` y el CLI vieran los errores en el `COMMIT` y no en la sentencia. El trigger
  de restricción se AÑADE; no sustituye a `crypto_keys_guard`.
- `crypto.guard_jobs_insert()` (E6; BEFORE INSERT): `apex_api` solo inserta `kind = rotate`,
  `status = running`, `data_class` no nula, `total > 0`, `done = 0`, `error` nulo y `created_by`
  un usuario real distinto del técnico.
- `crypto.guard_jobs_update()` (BEFORE UPDATE): para `apex_api`, `total` no cambia, `done` no
  decrece, `status = done` exige `done = total` y un job `done` no se reabre. `kind`, `data_class`,
  `created_by` e `id` los frenan el grant por columna y `guard_jobs_mutation` (`0003`).
- Los tres triggers nuevos en `ENABLE ALWAYS` (`tgenabled = 'A'`, como `0014`).

Residual (S6-D61, ver `docs/operacion/llaves.md`): las guardas ven lo confirmado y lo propio de la
transacción; un job `running` de OTRA transacción satisface la condición del job, pero
`uq_crypto_jobs_in_progress` impide dos en curso de la misma clase y `guard_jobs_insert` exige
`total > 0`, `done = 0` y un usuario real.

`downgrade`: restaura el cuerpo de `0015`, borra los tres triggers y las dos funciones nuevas.
"""

# ruff: noqa: S608
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024_crypto_rotation_from_api"
down_revision: str | None = "0023_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ERR = "USING ERRCODE = 'check_violation'"
SYSTEM_USER = "00000000-0000-0000-0000-000000000001"

KEYS_UPGRADE_SQL = f"""
CREATE OR REPLACE FUNCTION crypto.guard_keys_update() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$
DECLARE
    material_cambia boolean;
    proveedor_cambia boolean;
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'crypto.crypto_keys: las llaves nunca se borran' {ERR};
    END IF;
    IF TG_WHEN = 'AFTER' THEN
        -- Pasada diferida (crypto_keys_guard_cierre): las condiciones de H-2 sobre el estado final.
        IF current_user = 'apex_api' AND NEW.state IS DISTINCT FROM OLD.state THEN
            IF NOT EXISTS (
                SELECT 1 FROM crypto.crypto_keys k
                WHERE k.purpose = NEW.purpose AND k.data_class = NEW.data_class
                  AND k.state = 'active' AND k.version > NEW.version
            ) THEN
                RAISE EXCEPTION 'crypto.crypto_keys: falta la llave nueva active de la clase'
                    {ERR};
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM crypto.crypto_jobs j
                WHERE j.kind = 'rotate' AND j.status = 'running'
                  AND j.data_class = NEW.data_class
            ) THEN
                RAISE EXCEPTION 'crypto.crypto_keys: falta el job de rotación running de la clase'
                    {ERR};
            END IF;
        END IF;
        RETURN NULL;
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.purpose IS DISTINCT FROM OLD.purpose
       OR NEW.data_class IS DISTINCT FROM OLD.data_class
       OR NEW.algorithm IS DISTINCT FROM OLD.algorithm
       OR NEW.version IS DISTINCT FROM OLD.version
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
        RAISE EXCEPTION 'crypto.crypto_keys: solo cambian state, rotated_*, '
            'provider y wrapped_material' {ERR};
    END IF;
    IF current_user = 'apex_api' THEN
        IF NOT (OLD.purpose = 'encrypt' AND OLD.state = 'active'
                AND NEW.state = 'decrypt_only') THEN
            RAISE EXCEPTION 'crypto.crypto_keys: el api solo pasa una llave encrypt de active '
                'a decrypt_only' {ERR};
        END IF;
        IF NEW.provider IS DISTINCT FROM OLD.provider
           OR NEW.wrapped_material IS DISTINCT FROM OLD.wrapped_material THEN
            RAISE EXCEPTION 'crypto.crypto_keys: el api no cambia provider ni wrapped_material'
                {ERR};
        END IF;
        IF NEW.rotated_at IS NULL OR NEW.rotated_by IS NULL
           OR NEW.rotated_by = '{SYSTEM_USER}'::uuid
           OR NOT EXISTS (SELECT 1 FROM auth.users u WHERE u.id = NEW.rotated_by) THEN
            RAISE EXCEPTION 'crypto.crypto_keys: rotated_at y rotated_by reales' {ERR};
        END IF;
        RETURN NEW;
    END IF;
    material_cambia := NEW.wrapped_material IS DISTINCT FROM OLD.wrapped_material;
    proveedor_cambia := NEW.provider IS DISTINCT FROM OLD.provider;
    IF proveedor_cambia AND NOT material_cambia THEN
        RAISE EXCEPTION 'crypto.crypto_keys: provider solo cambia junto con wrapped_material'
            {ERR};
    END IF;
    IF material_cambia THEN
        IF length(NEW.wrapped_material) = 0 THEN
            RAISE EXCEPTION 'crypto.crypto_keys: wrapped_material no puede quedar vacío' {ERR};
        END IF;
        IF NEW.provider NOT IN ('local', 'openbao') THEN
            RAISE EXCEPTION 'crypto.crypto_keys: proveedor no permitido (%)', NEW.provider {ERR};
        END IF;
        IF NEW.state IS DISTINCT FROM OLD.state THEN
            RAISE EXCEPTION 'crypto.crypto_keys: state no cambia junto con wrapped_material'
                {ERR};
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.state IS DISTINCT FROM OLD.state AND NOT (
        (OLD.state = 'active' AND NEW.state IN ('decrypt_only', 'retired'))
        OR (OLD.state = 'decrypt_only' AND NEW.state = 'retired')
    ) THEN
        RAISE EXCEPTION 'crypto.crypto_keys: transición de estado no permitida (% -> %)',
            OLD.state, NEW.state {ERR};
    END IF;
    RETURN NEW;
END;
$$
"""

# Cuerpo literal de `0015` (los archivos de versión no se importan entre sí).
KEYS_DOWNGRADE_SQL = f"""
CREATE OR REPLACE FUNCTION crypto.guard_keys_update() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    material_cambia boolean;
    proveedor_cambia boolean;
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'crypto.crypto_keys: las llaves nunca se borran' {ERR};
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.purpose IS DISTINCT FROM OLD.purpose
       OR NEW.data_class IS DISTINCT FROM OLD.data_class
       OR NEW.algorithm IS DISTINCT FROM OLD.algorithm
       OR NEW.version IS DISTINCT FROM OLD.version
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
        RAISE EXCEPTION 'crypto.crypto_keys: solo cambian state, rotated_*, '
            'provider y wrapped_material' {ERR};
    END IF;
    material_cambia := NEW.wrapped_material IS DISTINCT FROM OLD.wrapped_material;
    proveedor_cambia := NEW.provider IS DISTINCT FROM OLD.provider;
    IF proveedor_cambia AND NOT material_cambia THEN
        RAISE EXCEPTION 'crypto.crypto_keys: provider solo cambia junto con wrapped_material'
            {ERR};
    END IF;
    IF material_cambia THEN
        IF length(NEW.wrapped_material) = 0 THEN
            RAISE EXCEPTION 'crypto.crypto_keys: wrapped_material no puede quedar vacío' {ERR};
        END IF;
        IF NEW.provider NOT IN ('local', 'openbao') THEN
            RAISE EXCEPTION 'crypto.crypto_keys: proveedor no permitido (%)', NEW.provider {ERR};
        END IF;
        IF NEW.state IS DISTINCT FROM OLD.state THEN
            RAISE EXCEPTION 'crypto.crypto_keys: state no cambia junto con wrapped_material'
                {ERR};
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.state IS DISTINCT FROM OLD.state AND NOT (
        (OLD.state = 'active' AND NEW.state IN ('decrypt_only', 'retired'))
        OR (OLD.state = 'decrypt_only' AND NEW.state = 'retired')
    ) THEN
        RAISE EXCEPTION 'crypto.crypto_keys: transición de estado no permitida (% -> %)',
            OLD.state, NEW.state {ERR};
    END IF;
    RETURN NEW;
END;
$$
"""

JOBS_INSERT_SQL = f"""
CREATE FUNCTION crypto.guard_jobs_insert() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$
BEGIN
    IF current_user = 'apex_api' THEN
        IF NEW.kind IS DISTINCT FROM 'rotate'
           OR NEW.status IS DISTINCT FROM 'running'
           OR NEW.data_class IS NULL
           OR NEW.total IS NULL OR NEW.total <= 0
           OR NEW.done IS DISTINCT FROM 0
           OR NEW.error IS NOT NULL
           OR NEW.created_by IS NULL
           OR NEW.created_by = '{SYSTEM_USER}'::uuid
           OR NOT EXISTS (SELECT 1 FROM auth.users u WHERE u.id = NEW.created_by) THEN
            RAISE EXCEPTION 'crypto.crypto_jobs: el api solo abre jobs rotate running con total '
                'positivo, done en cero y un usuario real' {ERR};
        END IF;
    END IF;
    RETURN NEW;
END;
$$
"""

JOBS_UPDATE_SQL = f"""
CREATE FUNCTION crypto.guard_jobs_update() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$
BEGIN
    IF current_user = 'apex_api' THEN
        IF NEW.total IS DISTINCT FROM OLD.total THEN
            RAISE EXCEPTION 'crypto.crypto_jobs: total no cambia' {ERR};
        END IF;
        IF NEW.done < OLD.done THEN
            RAISE EXCEPTION 'crypto.crypto_jobs: done no decrece' {ERR};
        END IF;
        IF NEW.status = 'done' AND NEW.done IS DISTINCT FROM NEW.total THEN
            RAISE EXCEPTION 'crypto.crypto_jobs: done exige done igual a total' {ERR};
        END IF;
        IF (NEW.status = 'running' AND NEW.error IS NOT NULL)
           OR (NEW.status = 'failed' AND NEW.error IS NULL) THEN
            RAISE EXCEPTION 'crypto.crypto_jobs: running sin error y failed con error' {ERR};
        END IF;
        IF OLD.status = 'done' AND NEW.status IS DISTINCT FROM 'done' THEN
            RAISE EXCEPTION 'crypto.crypto_jobs: un job done no se reabre' {ERR};
        END IF;
    END IF;
    RETURN NEW;
END;
$$
"""

UPGRADE_STATEMENTS = (
    KEYS_UPGRADE_SQL,
    "CREATE CONSTRAINT TRIGGER crypto_keys_guard_cierre AFTER UPDATE ON crypto.crypto_keys "
    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION crypto.guard_keys_update()",
    "ALTER TABLE crypto.crypto_keys ENABLE ALWAYS TRIGGER crypto_keys_guard_cierre",
    JOBS_INSERT_SQL,
    "CREATE TRIGGER crypto_jobs_guard_insert BEFORE INSERT ON crypto.crypto_jobs "
    "FOR EACH ROW EXECUTE FUNCTION crypto.guard_jobs_insert()",
    "ALTER TABLE crypto.crypto_jobs ENABLE ALWAYS TRIGGER crypto_jobs_guard_insert",
    JOBS_UPDATE_SQL,
    "CREATE TRIGGER crypto_jobs_guard_update BEFORE UPDATE ON crypto.crypto_jobs "
    "FOR EACH ROW EXECUTE FUNCTION crypto.guard_jobs_update()",
    "ALTER TABLE crypto.crypto_jobs ENABLE ALWAYS TRIGGER crypto_jobs_guard_update",
)

DOWNGRADE_STATEMENTS = (
    "DROP TRIGGER IF EXISTS crypto_jobs_guard_update ON crypto.crypto_jobs",
    "DROP TRIGGER IF EXISTS crypto_jobs_guard_insert ON crypto.crypto_jobs",
    "DROP TRIGGER IF EXISTS crypto_keys_guard_cierre ON crypto.crypto_keys",
    "DROP FUNCTION IF EXISTS crypto.guard_jobs_update()",
    "DROP FUNCTION IF EXISTS crypto.guard_jobs_insert()",
    KEYS_DOWNGRADE_SQL,
)


def upgrade() -> None:
    for sentencia in UPGRADE_STATEMENTS:
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in DOWNGRADE_STATEMENTS:
        op.execute(sentencia)
