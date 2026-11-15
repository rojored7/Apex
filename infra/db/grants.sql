-- Privilegios de los roles de aplicacion (S4B-W0-3; S4B-D7, D9, D61, D71). SQL puro, idempotente y
-- atomico (una sola transaccion): o queda todo o no cambia nada. Se ejecuta como propietario,
-- despues de roles.sql y de las migraciones. Sin privilegios por defecto para objetos futuros: una tabla nueva NO
-- hereda permisos; la migracion que la crea debe clasificarla aqui o el bloque final detiene todo.
--
-- Matriz (inventario de W0-3.1; la copia ejecutable vive en tests/migrations/test_db_grants.py).
-- S = SELECT, I = INSERT, U = UPDATE, D = DELETE; nunca TRUNCATE, TRIGGER ni REFERENCES.
-- apex_backup lee todo por pg_read_all_data y no escribe nada.
--   tabla                           apex_api                          apex_worker
--   attachments.attachments         S I U(key_id, updated_at)         -
--   audit.audit_log                 S I                               S I
--   audit.signatures                S                                 S I
--   audit.verifications             S I                               -
--   auth.one_time_tokens            S I U                             -
--   auth.refresh_tokens             S I U D                           -
--   auth.users                      S I U(email, password_hash, role, S
--                                     deleted_at, locked_at, last_login_at,
--                                     must_change_password, failed_login_count,
--                                     tokens_valid_after, updated_at)
--   classes.attendance              S I U(removed_at, removed_by,     -
--                                     removed_reason, updated_at)
--   classes.class_sessions          S I U(status, cancel_reason,      S I
--                                     cancelled_by, cancelled_at,
--                                     updated_at)
--   classes.class_slots             S I U(weekdays, start_time,       S
--                                     duration_min, capacity,
--                                     default_coach_id, name, valid_from,
--                                     is_active, updated_at)
--   crypto.crypto_jobs              S I U(done, status, error,        S
--                                     started_at, finished_at,
--                                     updated_at)
--   crypto.crypto_keys              S I U(state, rotated_at,          S
--                                     rotated_by, updated_at)
--                                   (public_key: INSERT sí, UPDATE nunca; S6-D81)
--   crypto.crypto_ops               S I                               S I
--   members.member_channel_preferences S I U(active, updated_at)      S
--   members.members                 S I U                             S(id, first_name, last_name, sex,
--                                                                       phone, email, status, deleted_at,
--                                                                       data_consent_at, created_at, updated_at)
--   memberships.membership_freezes  S I                               S
--   memberships.memberships         S I U(end_date, classes_remaining, S U(status, updated_at)
--                                     original_end_date, status,
--                                     cancel_reason, cancelled_by,
--                                     cancelled_at, updated_at)
--   notifications.notification_rules     S I U                        S
--   notifications.notification_templates S I U                        S
--   notifications.notifications          S I U(status, skip_reason,   S I U(status, attempts, last_error,
--                                          sent_at, sent_by,             sent_at, sent_by, skip_reason,
--                                          updated_at)                   updated_at)
--   payments.payments               S I(sin void_reason, voided_by,   -
--                                     voided_at) U(voided, void_reason,
--                                     voided_by, voided_at, updated_at)
--   plans.plans                     S I U                             S
--   public.alembic_version          S                                 -
--   settings.settings_sections      S I U                             S
--   wods.movements                  S I U(name, name_norm, category,  -
--                                     unit, is_active, updated_at)
--   wods.benchmarks                 S I U(name, name_norm,            -
--                                     description, score_type,
--                                     updated_at)
--   wods.wods                       S I U(date, title, score_type,    -
--                                     time_cap_s, benchmark_id,
--                                     description, updated_at)
--   wods.wod_movements              S I D                             -
--   worker.job_runs                 S                                 S I U
-- clasificada: attachments.attachments
-- clasificada: audit.audit_log
-- clasificada: audit.signatures
-- clasificada: audit.verifications
-- clasificada: auth.one_time_tokens
-- clasificada: auth.refresh_tokens
-- clasificada: auth.users
-- clasificada: classes.attendance
-- clasificada: classes.class_sessions
-- clasificada: classes.class_slots
-- clasificada: crypto.crypto_jobs
-- clasificada: crypto.crypto_keys
-- clasificada: crypto.crypto_ops
-- clasificada: members.member_channel_preferences
-- clasificada: members.members
-- clasificada: memberships.membership_freezes
-- clasificada: memberships.memberships
-- clasificada: notifications.notification_rules
-- clasificada: notifications.notification_templates
-- clasificada: notifications.notifications
-- clasificada: payments.payments
-- clasificada: plans.plans
-- clasificada: public.alembic_version
-- clasificada: settings.settings_sections
-- clasificada: wods.benchmarks
-- clasificada: wods.movements
-- clasificada: wods.wod_movements
-- clasificada: wods.wods
-- clasificada: worker.job_runs
--
-- Residuales aceptados (S4B-D61): apex_api puede INSERT en crypto.crypto_keys (ensure_keys) y en
-- audit.audit_log; el UPDATE de crypto_keys se limita (S6-R1) a state, rotated_at, rotated_by y
-- updated_at, y la guarda de 0024 solo admite active -> decrypt_only con las tres condiciones de H-2;
-- nunca retired ni provider ni wrapped_material.
\set ON_ERROR_STOP on
BEGIN;

-- 1. Nada para PUBLIC: base, esquema public y todo objeto de la aplicacion.
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database()) \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA attachments, audit, auth, classes, crypto, members, memberships, notifications, payments, plans, settings, wods, worker, public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA attachments, audit, auth, classes, crypto, members, memberships, notifications, payments, plans, settings, wods, worker, public FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA attachments, audit, auth, classes, crypto, members, memberships, notifications, payments, plans, settings, wods, worker FROM PUBLIC;

-- 2. Reiniciar lo que pudieran tener los tres roles (idempotencia ante cambios de la matriz).
REVOKE ALL ON ALL TABLES IN SCHEMA attachments, audit, auth, classes, crypto, members, memberships, notifications, payments, plans, settings, wods, worker, public FROM apex_api, apex_worker, apex_backup;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA attachments, audit, auth, classes, crypto, members, memberships, notifications, payments, plans, settings, wods, worker, public FROM apex_api, apex_worker, apex_backup;

-- 3. Conectar y recorrer los esquemas (sin CREATE en ninguno).
SELECT format('GRANT CONNECT ON DATABASE %I TO apex_api, apex_worker, apex_backup', current_database()) \gexec
GRANT USAGE ON SCHEMA attachments, audit, auth, classes, crypto, members, memberships, notifications, payments, plans, settings, worker TO apex_api, apex_worker, apex_backup;
-- S8-A1 (P-ROL): el worker no ve el esquema `wods` (ni `results`): sin USAGE.
GRANT USAGE ON SCHEMA wods TO apex_api, apex_backup;

-- 4. apex_backup: solo lectura de todo, por membresia con herencia (el rol es NOINHERIT; PG16 exige
--    WITH INHERIT TRUE para que la membresia sirva).
GRANT pg_read_all_data TO apex_backup WITH INHERIT TRUE;

-- 5. apex_api.
-- S6-C1 (S6-D25): el api sube adjuntos (INSERT) y recifra (UPDATE solo de key_id y updated_at); sin
-- DELETE ni TRUNCATE (el trigger tambien los prohibe); el worker no toca la tabla.
GRANT SELECT, INSERT ON attachments.attachments TO apex_api;
GRANT UPDATE (key_id, updated_at) ON attachments.attachments TO apex_api;
GRANT SELECT, INSERT ON audit.audit_log, audit.verifications TO apex_api;
-- S7-A2 (S7-D18, US-155): franjas del horario; el api inserta y edita por columna (el admin las
-- pausa con is_active); sin DELETE ni TRUNCATE (los triggers tambien los prohiben); worker solo lee.
GRANT SELECT, INSERT ON classes.class_slots TO apex_api;
-- S7-B1 (S7-D18, US-156): sesiones; el api crea extras (INSERT) y las cancela por columna; sin DELETE
-- ni TRUNCATE (los triggers tambien los prohiben) y la guarda impide des-cancelar o reescribir.
GRANT SELECT, INSERT ON classes.class_sessions TO apex_api;
-- S7-C1 (S7-D13, US-159, US-161): asistencia; el api registra (INSERT) y la quita por columna
-- (removed_*); sin DELETE ni TRUNCATE (los triggers tambien los prohiben) y la guarda impide
-- reescribir lo registrado o des-quitar. El worker no la toca.
GRANT SELECT, INSERT ON classes.attendance TO apex_api;
GRANT UPDATE (removed_at, removed_by, removed_reason, updated_at) ON classes.attendance TO apex_api;
GRANT UPDATE (status, cancel_reason, cancelled_by, cancelled_at, updated_at) ON classes.class_sessions TO apex_api;
GRANT UPDATE (weekdays, start_time, duration_min, capacity, default_coach_id, name, valid_from, is_active, updated_at) ON classes.class_slots TO apex_api;
-- S8-A1 (S8-D5, S8-D21, US-165): catalogo de movimientos; el api inserta y edita por columna (se
-- desactivan con is_active); sin DELETE ni TRUNCATE (los triggers tambien los prohiben); el worker no
-- ve el esquema.
GRANT SELECT, INSERT ON wods.movements TO apex_api;
GRANT UPDATE (name, name_norm, category, unit, is_active, updated_at) ON wods.movements TO apex_api;
-- S8-A2 (S8-D6, US-166): catalogo de benchmarks; mismo reparto que los movimientos.
GRANT SELECT, INSERT ON wods.benchmarks TO apex_api;
GRANT UPDATE (name, name_norm, description, score_type, updated_at) ON wods.benchmarks TO apex_api;
-- S8-A3 (S8-D7, US-166): WODs (sin DELETE) y sus movimientos (reemplazo de lista: S I D, E6).
GRANT SELECT, INSERT ON wods.wods TO apex_api;
GRANT UPDATE (date, title, score_type, time_cap_s, benchmark_id, description, updated_at) ON wods.wods TO apex_api;
GRANT SELECT, INSERT, DELETE ON wods.wod_movements TO apex_api;
-- S6-A1 (S6-D7): el api solo lee las firmas (verifica con la clave publica); firma el worker.
GRANT SELECT ON audit.signatures TO apex_api;
GRANT SELECT, INSERT, UPDATE ON auth.one_time_tokens TO apex_api;
GRANT SELECT, INSERT ON auth.users TO apex_api;
-- S5-D203: UPDATE de auth.users solo en las columnas que asigna modules/auth (inventario de W0-3);
-- is_active, member_id, id, created_at y created_by quedan fijos.
GRANT UPDATE (email, password_hash, role, deleted_at, locked_at, last_login_at, must_change_password, failed_login_count, tokens_valid_after, updated_at) ON auth.users TO apex_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth.refresh_tokens TO apex_api;
-- S6-R1 (S6-D43, S6-D61, H-2, E6): la rotacion desde la pantalla corre como apex_api. INSERT de jobs
-- solo con la forma que admite crypto.guard_jobs_insert (migracion 0024); UPDATE por columna del
-- progreso (crypto.guard_jobs_update); kind, data_class y total quedan fijos. En crypto_keys solo
-- state y su rastro: crypto.guard_keys_update (0024) deja pasar unicamente active -> decrypt_only de
-- una llave encrypt con otra active de version mayor, un job running de la clase y un usuario real.
GRANT SELECT, INSERT ON crypto.crypto_jobs TO apex_api;
GRANT UPDATE (done, status, error, started_at, finished_at, updated_at) ON crypto.crypto_jobs TO apex_api;
GRANT SELECT, INSERT ON crypto.crypto_keys TO apex_api;
GRANT UPDATE (state, rotated_at, rotated_by, updated_at) ON crypto.crypto_keys TO apex_api;
GRANT SELECT, INSERT ON crypto.crypto_ops TO apex_api;
GRANT SELECT, INSERT, UPDATE ON members.members TO apex_api;
-- S5-B5 (US-123): upsert de preferencias de canal; sin DELETE (el borrado de socios es logico).
GRANT SELECT, INSERT ON members.member_channel_preferences TO apex_api;
-- S5-D256: UPDATE por columna; el upsert de canales solo cambia active (y updated_at).
GRANT UPDATE (active, updated_at) ON members.member_channel_preferences TO apex_api;
GRANT SELECT, INSERT ON memberships.membership_freezes TO apex_api;
GRANT SELECT, INSERT ON memberships.memberships TO apex_api;
-- S5-B6 (US-120, US-121): plantillas y reglas de aviso; sin DELETE (las reglas se desactivan).
GRANT SELECT, INSERT, UPDATE ON notifications.notification_rules, notifications.notification_templates TO apex_api;
-- S5-B7 (US-124, US-127 a US-130): avisos del dia; genera, omite y marca enviado; sin DELETE.
GRANT SELECT, INSERT ON notifications.notifications TO apex_api;
-- S5-D256: UPDATE por columna; skip y wa-link solo cambian estado, motivo de omision y marca de envio.
GRANT UPDATE (status, skip_reason, sent_at, sent_by, updated_at) ON notifications.notifications TO apex_api;
-- S7-D29: original_end_date (el fin antes del recorte de la ultima clase) tambien lo escribe apex_api.
GRANT UPDATE (end_date, classes_remaining, original_end_date, status, cancel_reason, cancelled_by, cancelled_at, updated_at) ON memberships.memberships TO apex_api;
-- S5-D202: INSERT de pagos por columna; void_reason, voided_by y voided_at solo por la anulacion.
GRANT SELECT ON payments.payments TO apex_api;
GRANT INSERT (id, created_at, updated_at, created_by, membership_id, member_id, amount_cop, method, reference, paid_at, registered_by, voided) ON payments.payments TO apex_api;
GRANT UPDATE (voided, void_reason, voided_by, voided_at, updated_at) ON payments.payments TO apex_api;
GRANT SELECT, INSERT, UPDATE ON plans.plans, settings.settings_sections TO apex_api;
GRANT SELECT ON public.alembic_version TO apex_api;
GRANT SELECT ON worker.job_runs TO apex_api;

-- 6. apex_worker (jobs diarios: vencimientos, avisos, comprobacion de respaldos).
GRANT SELECT, INSERT ON audit.audit_log, crypto.crypto_ops TO apex_worker;
-- S6-A1 (S6-D3): el worker firma la cadena (sign_audit); append-only, sin UPDATE ni DELETE.
GRANT SELECT, INSERT ON audit.signatures TO apex_worker;
GRANT SELECT ON auth.users, classes.class_slots, crypto.crypto_jobs, crypto.crypto_keys, memberships.membership_freezes, plans.plans, settings.settings_sections TO apex_worker;
-- S5-D34, D204: el worker descifra avisos (crypto_keys) y lee del socio solo lo minimo; sin document,
-- document_idx, birth_date ni emergency_contact. sex entra por names_for (S5-D121).
GRANT SELECT (id, first_name, last_name, sex, phone, email, status, deleted_at, data_consent_at, created_at, updated_at) ON members.members TO apex_worker;
GRANT SELECT ON memberships.memberships TO apex_worker;
-- S7-B1 (S7-D18): el job generate_sessions crea las sesiones; no las actualiza ni las borra.
GRANT SELECT, INSERT ON classes.class_sessions TO apex_worker;
-- S5-B5: el job notify lee los canales efectivos (members.service.channels_for).
GRANT SELECT ON members.member_channel_preferences TO apex_worker;
-- S5-B6 (S5-D34): el job notify lee plantillas y reglas; no siembra ni edita.
GRANT SELECT ON notifications.notification_rules, notifications.notification_templates TO apex_worker;
-- S5-B7 (S5-D34): el job notify genera avisos y solo actualiza el resultado del envio (S5-D222: skip_reason para canal_no_configurado).
GRANT SELECT, INSERT ON notifications.notifications TO apex_worker;
GRANT UPDATE (status, attempts, last_error, sent_at, sent_by, skip_reason, updated_at) ON notifications.notifications TO apex_worker;
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
        'attachments.attachments', 'audit.audit_log', 'audit.signatures', 'audit.verifications', 'auth.one_time_tokens', 'auth.refresh_tokens',
        'auth.users', 'classes.attendance', 'classes.class_sessions', 'classes.class_slots', 'crypto.crypto_jobs', 'crypto.crypto_keys',
        'crypto.crypto_ops',
        'members.member_channel_preferences', 'members.members',
        'memberships.membership_freezes', 'memberships.memberships',
        'notifications.notification_rules', 'notifications.notification_templates',
        'notifications.notifications',
        'payments.payments', 'plans.plans', 'public.alembic_version',
        'settings.settings_sections', 'wods.benchmarks', 'wods.movements', 'wods.wod_movements',
        'wods.wods', 'worker.job_runs'];
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
