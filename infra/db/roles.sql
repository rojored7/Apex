SET log_min_error_statement = panic;
SET log_statement = 'none';
SET log_min_duration_statement = -1;
SET log_duration = off;
-- Roles de aplicacion de APEX (S4B-W0-3; S4B-D7, D56, D72). Se ejecuta con psql como el
-- propietario de la base, desde infra/db/apply.sh (servicio dbsetup) o a mano con el mismo entorno.
-- Cada contrasena entra por su variable de entorno (\getenv): nunca por -v ni por la linea de
-- comandos. Los dos SET de arriba evitan que el servidor registre la sentencia con la contrasena.
-- Idempotente: crea el rol si no existe y SIEMPRE vuelve a fijar atributos, limites y contrasena.
-- Los privilegios por tabla viven en grants.sql; deshacer todo es revoke.sql.
\set ON_ERROR_STOP on
\getenv api_pw APEX_API_DB_PASSWORD
\getenv worker_pw APEX_WORKER_DB_PASSWORD
\getenv backup_pw APEX_BACKUP_DB_PASSWORD

SELECT format('CREATE ROLE %I LOGIN', r.nombre)
FROM (VALUES ('apex_api'), ('apex_worker'), ('apex_backup')) AS r (nombre)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r.nombre)
\gexec

-- Sin superusuario, sin crear bases ni roles, sin herencia automatica, sin saltar RLS ni replicar.
-- CONNECTION LIMIT: api 20 (pool del engine), worker 5, backup 2.
SELECT format('ALTER ROLE apex_api WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS NOREPLICATION LOGIN CONNECTION LIMIT 20 PASSWORD %L', :'api_pw')
\gexec
SELECT format('ALTER ROLE apex_worker WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS NOREPLICATION LOGIN CONNECTION LIMIT 5 PASSWORD %L', :'worker_pw')
\gexec
SELECT format('ALTER ROLE apex_backup WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS NOREPLICATION LOGIN CONNECTION LIMIT 2 PASSWORD %L', :'backup_pw')
\gexec

-- Mismos valores por defecto que Settings (DB_STATEMENT_TIMEOUT_MS y DB_IDLE_IN_TX_TIMEOUT_MS).
ALTER ROLE apex_api SET statement_timeout = 30000;
ALTER ROLE apex_api SET idle_in_transaction_session_timeout = 60000;
ALTER ROLE apex_worker SET statement_timeout = 30000;
ALTER ROLE apex_worker SET idle_in_transaction_session_timeout = 60000;
ALTER ROLE apex_backup SET statement_timeout = 30000;
ALTER ROLE apex_backup SET idle_in_transaction_session_timeout = 60000;
