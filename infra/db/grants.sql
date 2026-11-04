-- Privilegios de los roles de aplicacion (S4B-W0-3; S4B-D7, D9, D61, D71). SQL puro, idempotente y
-- atomico (una sola transaccion): o queda todo o no cambia nada. Se ejecuta como propietario,
-- despues de roles.sql y de las migraciones. Sin privilegios por defecto para objetos futuros: una tabla nueva NO
-- hereda permisos; la migracion que la crea debe clasificarla aqui o el bloque final detiene todo.
--
-- Matriz (inventario de W0-3.1; la copia ejecutable vive en tests/migrations/test_db_grants.py).
-- S = SELECT, I = INSERT, U = UPDATE, D = DELETE; nunca TRUNCATE, TRIGGER ni REFERENCES.
-- apex_backup lee todo por pg_read_all_data y no escribe nada.
--   tabla                           apex_api                          apex_worker
--   audit.audit_log                 S I                               S I
--   audit.verifications             S I                               -
--   auth.one_time_tokens            S I U                             -
--   auth.refresh_tokens             S I U D                           -
--   auth.users                      S I U(email, password_hash, role, S
--                                     deleted_at, locked_at, last_login_at,
--                                     must_change_password, failed_login_count,
--                                     tokens_valid_after, updated_at)
--   crypto.crypto_jobs              S                                 S
--   crypto.crypto_keys              S I U(updated_at)                 S
--   crypto.crypto_ops               S I                               S I
--   members.members                 S I U                             S(id, first_name, last_name, sex,
--                                                                       phone, email, status, deleted_at,
--                                                                       data_consent_at, created_at, updated_at)
--   memberships.membership_freezes  S I                               S
--   memberships.memberships         S I U(end_date, classes_remaining, S U(status, updated_at)
--                                     status, cancel_reason, cancelled_by,
--                                     cancelled_at, updated_at)
--   payments.payments               S I(sin void_reason, voided_by,   -
--                                     voided_at) U(voided, void_reason,
--                                     voided_by, voided_at, updated_at)
--   plans.plans                     S I U                             S
--   public.alembic_version          S                                 -
--   settings.settings_sections      S I U                             S
--   worker.job_runs                 S                                 S I U
-- clasificada: audit.audit_log
-- clasificada: audit.verifications
-- clasificada: auth.one_time_tokens
-- clasificada: auth.refresh_tokens
-- clasificada: auth.users
-- clasificada: crypto.crypto_jobs
-- clasificada: crypto.crypto_keys
-- clasificada: crypto.crypto_ops
-- clasificada: members.members
-- clasificada: memberships.membership_freezes
-- clasificada: memberships.memberships
-- clasificada: payments.payments
-- clasificada: plans.plans
-- clasificada: public.alembic_version
-- clasificada: settings.settings_sections
-- clasificada: worker.job_runs
--
-- Residuales aceptados (S4B-D61): apex_api puede INSERT en crypto.crypto_keys (ensure_keys) y en
-- audit.audit_log; el UPDATE de crypto_keys se limita a updated_at (necesario para SELECT ... FOR
-- SHARE), nunca a state.
\set ON_ERROR_STOP on
BEGIN;

-- 1. Nada para PUBLIC: base, esquema public y todo objeto de la aplicacion.
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database()) \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA audit, auth, crypto, members, memberships, payments, plans, settings, worker, public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA audit, auth, crypto, members, memberships, payments, plans, settings, worker, public FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA audit, auth, crypto, members, memberships, payments, plans, settings, worker FROM PUBLIC;

-- 2. Reiniciar lo que pudieran tener los tres roles (idempotencia ante cambios de la matriz).
REVOKE ALL ON ALL TABLES IN SCHEMA audit, auth, crypto, members, memberships, payments, plans, settings, worker, public FROM apex_api, apex_worker, apex_backup;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA audit, auth, crypto, members, memberships, payments, plans, settings, worker, public FROM apex_api, apex_worker, apex_backup;

-- 3. Conectar y recorrer los esquemas (sin CREATE en ninguno).
SELECT format('GRANT CONNECT ON DATABASE %I TO apex_api, apex_worker, apex_backup', current_database()) \gexec
GRANT USAGE ON SCHEMA audit, auth, crypto, members, memberships, payments, plans, settings, worker TO apex_api, apex_worker, apex_backup;

-- 4. apex_backup: solo lectura de todo, por membresia con herencia (el rol es NOINHERIT; PG16 exige
--    WITH INHERIT TRUE para que la membresia sirva).
GRANT pg_read_all_data TO apex_backup WITH INHERIT TRUE;

-- 5. apex_api.
GRANT SELECT, INSERT ON audit.audit_log, audit.verifications TO apex_api;
GRANT SELECT, INSERT, UPDATE ON auth.one_time_tokens TO apex_api;
GRANT SELECT, INSERT ON auth.users TO apex_api;
-- S5-D203: UPDATE de auth.users solo en las columnas que asigna modules/auth (inventario de W0-3);
-- is_active, member_id, id, created_at y created_by quedan fijos.
GRANT UPDATE (email, password_hash, role, deleted_at, locked_at, last_login_at, must_change_password, failed_login_count, tokens_valid_after, updated_at) ON auth.users TO apex_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth.refresh_tokens TO apex_api;
GRANT SELECT ON crypto.crypto_jobs TO apex_api;
GRANT SELECT, INSERT ON crypto.crypto_keys TO apex_api;
GRANT UPDATE (updated_at) ON crypto.crypto_keys TO apex_api;
GRANT SELECT, INSERT ON crypto.crypto_ops TO apex_api;
GRANT SELECT, INSERT, UPDATE ON members.members TO apex_api;
GRANT SELECT, INSERT ON memberships.membership_freezes TO apex_api;
GRANT SELECT, INSERT ON memberships.memberships TO apex_api;
GRANT UPDATE (end_date, classes_remaining, status, cancel_reason, cancelled_by, cancelled_at, updated_at) ON memberships.memberships TO apex_api;
-- S5-D202: INSERT de pagos por columna; void_reason, voided_by y voided_at solo por la anulacion.
GRANT SELECT ON payments.payments TO apex_api;
GRANT INSERT (id, created_at, updated_at, created_by, membership_id, member_id, amount_cop, method, reference, paid_at, registered_by, voided) ON payments.payments TO apex_api;
GRANT UPDATE (voided, void_reason, voided_by, voided_at, updated_at) ON payments.payments TO apex_api;
GRANT SELECT, INSERT, UPDATE ON plans.plans, settings.settings_sections TO apex_api;
GRANT SELECT ON public.alembic_version TO apex_api;
GRANT SELECT ON worker.job_runs TO apex_api;

-- 6. apex_worker (jobs diarios: vencimientos, avisos, comprobacion de respaldos).
GRANT SELECT, INSERT ON audit.audit_log, crypto.crypto_ops TO apex_worker;
GRANT SELECT ON auth.users, crypto.crypto_jobs, crypto.crypto_keys, memberships.membership_freezes, plans.plans, settings.settings_sections TO apex_worker;
-- S5-D34, D204: el worker descifra avisos (crypto_keys) y lee del socio solo lo minimo; sin document,
-- document_idx, birth_date ni emergency_contact. sex entra por names_for (S5-D121).
GRANT SELECT (id, first_name, last_name, sex, phone, email, status, deleted_at, data_consent_at, created_at, updated_at) ON members.members TO apex_worker;
GRANT SELECT ON memberships.memberships TO apex_worker;
GRANT UPDATE (status, updated_at) ON memberships.memberships TO apex_worker;
GRANT SELECT, INSERT, UPDATE ON worker.job_runs TO apex_worker;

-- 7. Fallo cerrado: todo objeto con almacenamiento de CUALQUIER esquema que no sea del sistema
--    (tablas, particionadas, vistas, vistas materializadas, secuencias y tablas foraneas) debe estar
--    en la lista `clasificada` de arriba (copiada aqui literalmente). Un esquema nuevo cuenta. Solo
--    se excusan los objetos que pertenecen a una extension (pg_depend, deptype e). Si algo falta, la
--    transaccion entera se revierte.
DO $$
DECLARE
    clasificadas constant text[] := ARRAY[
        'audit.audit_log', 'audit.verifications', 'auth.one_time_tokens', 'auth.refresh_tokens',
        'auth.users', 'crypto.crypto_jobs', 'crypto.crypto_keys', 'crypto.crypto_ops',
        'members.members', 'memberships.membership_freezes', 'memberships.memberships',
        'payments.payments', 'plans.plans', 'public.alembic_version',
        'settings.settings_sections', 'worker.job_runs'];
    sin_clasificar text;
BEGIN
    SELECT string_agg(n.nspname || '.' || c.relname, ', ' ORDER BY n.nspname, c.relname)
      INTO sin_clasificar
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
       AND n.nspname !~ '^(pg_|information_schema$)'
       AND NOT EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid
                          AND d.deptype = 'e')
       AND (n.nspname || '.' || c.relname) <> ALL (clasificadas);
    IF sin_clasificar IS NOT NULL THEN
        RAISE EXCEPTION 'tabla sin clasificar: %', sin_clasificar;
    END IF;
END
$$;

COMMIT;
