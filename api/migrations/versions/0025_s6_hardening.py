"""Endurecimiento heredado del Sprint 6 (S7-D3; S6-D130, S6-D133; M-6, L-6).

Revision ID: 0025_s6_hardening
Revises: 0024_crypto_rotation_from_api
Create Date: 2026-11-14

Cada paso lleva una consulta previa de solo lectura que ABORTA la migración, nombrando la regla y
el conteo de filas que la violan (nunca valores), antes de endurecer. Alembic es transaccional: si
aborta, no queda nada a medias. Las mismas consultas están en `docs/RUNBOOK.md` §12 (L-6) para
correrlas antes de desplegar.

- (a) FK `fk_attachments_key_id` de `attachments.attachments.key_id` a `crypto.crypto_keys(id)`
  `ON DELETE RESTRICT` (`NOT VALID` y luego `VALIDATE`). Es una FK de un módulo hacia `core`, no
  entre módulos; la decisión «sin FK entre esquemas» de `0023` se corrige aquí.
- (b) `ck_crypto_keys_sign_iff_public_key`: `(purpose = 'sign') = (public_key IS NOT NULL)`,
  en lugar del unidireccional `ck_crypto_keys_sign_public_key`.
- (c) `ck_attachments_photo_not_sensitive`: `kind <> 'photo' OR NOT sensitive`.
- (d) `crypto.guard_keys_update()`: `public_key` no nula es inmutable para todo rol (completar un
  nulo sigue permitido, D99). La regla va solo en la pasada `BEFORE UPDATE`, después de las ramas
  `DELETE/TRUNCATE` y de `TG_WHEN = 'AFTER'` (M-6).
- (e) `crypto.guard_jobs_update()`: la rama de `apex_api` exige `OLD.kind = 'rotate'` y que `kind`
  no cambie (hoy podría reabrir un job `migrate_provider` o `rewrap` del CLI).

`SET LOCAL lock_timeout = '5s'`: la FK y los CHECK toman candados de tabla breves; con el api
parado nadie compite, y si alguien lo hace la migración falla en vez de esperar.

`downgrade`: quita la FK y los dos CHECK nuevos, repone `ck_crypto_keys_sign_public_key` y los
cuerpos de `0024` (copiados como constantes: una migración no importa otra).
"""

# ruff: noqa: S608
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_s6_hardening"
down_revision: str | None = "0024_crypto_rotation_from_api"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ERR = "USING ERRCODE = 'check_violation'"
SYSTEM_USER = "00000000-0000-0000-0000-000000000001"

# (regla, consulta previa de solo lectura) en el orden en que se aplican.
PRECHECKS: tuple[tuple[str, str], ...] = (
    (
        "fk_attachments_key_id",
        "SELECT count(*) FROM attachments.attachments a WHERE a.key_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM crypto.crypto_keys k WHERE k.id = a.key_id)",
    ),
    (
        "sign_iff_public_key",
        "SELECT count(*) FROM crypto.crypto_keys "
        "WHERE (purpose = 'sign') <> (public_key IS NOT NULL)",
    ),
    (
        "photo_not_sensitive",
        "SELECT count(*) FROM attachments.attachments WHERE kind = 'photo' AND sensitive",
    ),
)

# Cuerpos literales de `0024` (para `downgrade`; la regla nueva no está).
KEYS_0024_SQL = f"""
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

JOBS_0024_SQL = f"""
CREATE OR REPLACE FUNCTION crypto.guard_jobs_update() RETURNS trigger
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

# (d) La regla de `public_key` entra justo antes de las columnas inmutables: tras las ramas
# DELETE/TRUNCATE y AFTER, así que solo se evalúa en el BEFORE UPDATE, para todo rol.
_ANCLA_KEYS = "    IF NEW.id IS DISTINCT FROM OLD.id\n"
_REGLA_KEYS = f"""    IF OLD.public_key IS NOT NULL
       AND NEW.public_key IS DISTINCT FROM OLD.public_key THEN
        RAISE EXCEPTION 'crypto.crypto_keys: public_key no nula es inmutable' {ERR};
    END IF;
"""
KEYS_0025_SQL = KEYS_0024_SQL.replace(_ANCLA_KEYS, _REGLA_KEYS + _ANCLA_KEYS, 1)

# (e) La rama de `apex_api` solo admite jobs `rotate`.
_ANCLA_JOBS = "    IF current_user = 'apex_api' THEN\n"
_REGLA_JOBS = f"""    IF current_user = 'apex_api' THEN
        IF OLD.kind IS DISTINCT FROM 'rotate' OR NEW.kind IS DISTINCT FROM OLD.kind THEN
            RAISE EXCEPTION 'crypto.crypto_jobs: el api solo toca jobs rotate' {ERR};
        END IF;
"""
JOBS_0025_SQL = JOBS_0024_SQL.replace(_ANCLA_JOBS, _REGLA_JOBS, 1)

if KEYS_0025_SQL == KEYS_0024_SQL or JOBS_0025_SQL == JOBS_0024_SQL:  # pragma: no cover
    raise RuntimeError("0025: el ancla de la regla nueva no está en el cuerpo de 0024")


def _verificar_previas() -> None:
    """Aborta nombrando la regla y el conteo; nunca imprime valores de las filas."""
    bind = op.get_bind()
    for regla, consulta in PRECHECKS:
        cuenta = bind.execute(sa.text(consulta)).scalar_one()
        if cuenta:
            raise RuntimeError(
                f"0025_s6_hardening aborta: la regla {regla} la violan {cuenta} fila(s); "
                "corríjase antes de migrar (docs/RUNBOOK.md §12, consultas previas de 0025)"
            )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    _verificar_previas()
    op.execute(
        "ALTER TABLE attachments.attachments ADD CONSTRAINT fk_attachments_key_id "
        "FOREIGN KEY (key_id) REFERENCES crypto.crypto_keys (id) ON DELETE RESTRICT NOT VALID"
    )
    op.execute("ALTER TABLE attachments.attachments VALIDATE CONSTRAINT fk_attachments_key_id")
    op.execute("ALTER TABLE crypto.crypto_keys DROP CONSTRAINT ck_crypto_keys_sign_public_key")
    op.execute(
        "ALTER TABLE crypto.crypto_keys ADD CONSTRAINT ck_crypto_keys_sign_iff_public_key "
        "CHECK ((purpose = 'sign') = (public_key IS NOT NULL)) NOT VALID"
    )
    op.execute(
        "ALTER TABLE crypto.crypto_keys VALIDATE CONSTRAINT ck_crypto_keys_sign_iff_public_key"
    )
    op.execute(
        "ALTER TABLE attachments.attachments ADD CONSTRAINT ck_attachments_photo_not_sensitive "
        "CHECK (kind <> 'photo' OR NOT sensitive) NOT VALID"
    )
    op.execute(
        "ALTER TABLE attachments.attachments VALIDATE CONSTRAINT ck_attachments_photo_not_sensitive"
    )
    op.execute(KEYS_0025_SQL)
    op.execute(JOBS_0025_SQL)


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(JOBS_0024_SQL)
    op.execute(KEYS_0024_SQL)
    op.execute(
        "ALTER TABLE attachments.attachments DROP CONSTRAINT ck_attachments_photo_not_sensitive"
    )
    op.execute("ALTER TABLE crypto.crypto_keys DROP CONSTRAINT ck_crypto_keys_sign_iff_public_key")
    op.execute(
        "ALTER TABLE crypto.crypto_keys ADD CONSTRAINT ck_crypto_keys_sign_public_key "
        "CHECK ((purpose <> 'sign') OR (public_key IS NOT NULL))"
    )
    op.execute("ALTER TABLE attachments.attachments DROP CONSTRAINT fk_attachments_key_id")
