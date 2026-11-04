"""Guarda de `crypto.crypto_keys` que permite migrar de proveedor y re-envolver (S5-D4).

Revision ID: 0015_crypto_provider_migration
Revises: 0014_audit_log_triggers_always
Create Date: 2026-11-04

- `CREATE OR REPLACE FUNCTION crypto.guard_keys_update()`: además de lo que `0003` ya permitía
  (`state` y `rotated_*`), deja que una llave (también `sign`, S5-D18 ampliada) cambie de proveedor
  (`local <-> openbao`) siempre junto con un `wrapped_material` nuevo, o cambie solo
  `wrapped_material` (re-envoltura), nunca vacío. `provider` sin material nuevo, `state` junto con
  `wrapped_material`, `version`, `data_class`, `algorithm`, `purpose` y `created_*` siguen
  rechazados. Misma firma, `SECURITY INVOKER`, mismo ERRCODE
  `check_violation`.
- No toca los triggers (`crypto_keys_guard` y `crypto_keys_forbid_truncate` siguen en `'A'`
  desde `0014`): `CREATE OR REPLACE` conserva el `OID` de la función. No crea tablas ni columnas.
- Quién puede: los `GRANT` no cambian. `apex_api` y `apex_worker` no tienen `UPDATE` de
  `provider` ni de `wrapped_material`; migra el propietario (`tools`).

`downgrade`: la función recupera el cuerpo literal de `0003`.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015_crypto_provider_migration"
down_revision: str | None = "0014_audit_log_triggers_always"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ERR = "USING ERRCODE = 'check_violation'"

UPGRADE_SQL = f"""
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

# Cuerpo literal de `0003` (los archivos de versión no se importan entre sí).
DOWNGRADE_SQL = f"""
CREATE OR REPLACE FUNCTION crypto.guard_keys_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'crypto.crypto_keys: las llaves nunca se borran' {ERR};
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.purpose IS DISTINCT FROM OLD.purpose
       OR NEW.data_class IS DISTINCT FROM OLD.data_class
       OR NEW.algorithm IS DISTINCT FROM OLD.algorithm
       OR NEW.provider IS DISTINCT FROM OLD.provider
       OR NEW.version IS DISTINCT FROM OLD.version
       OR NEW.wrapped_material IS DISTINCT FROM OLD.wrapped_material
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
        RAISE EXCEPTION 'crypto.crypto_keys: solo cambia state y rotated_*' {ERR};
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


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
