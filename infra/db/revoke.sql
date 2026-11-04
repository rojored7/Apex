-- Deshace roles.sql y grants.sql (S4B-W0-3; S4B-D83: vuelta atras de los roles). Se ejecuta con psql
-- como propietario, conectado a la base de la aplicacion:
--   docker compose --env-file .env --env-file .env.ops -f infra/compose.yml exec -T db \
--     psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f - < infra/db/revoke.sql
-- NUNCA toca `apex_owner` (S5-D144): es el propietario de los esquemas y un DROP OWNED BY lo borraria
-- todo. Solo se eliminan los tres roles de aplicacion.
-- Idempotente: si un rol ya no existe no hace nada. DROP OWNED BY quita los privilegios que el rol
-- tiene en ESTA base (y sobre las bases del cluster); ningun rol es dueno de objetos. Antes de
-- ejecutarlo hay que parar api, worker y backup: DROP ROLE falla con sesiones abiertas de ese rol.
-- NO restaura los REVOKE ... FROM PUBLIC de grants.sql (CONNECT y TEMP sobre la base, CREATE sobre
-- public, privilegios de tablas y funciones): el propietario es superusuario y no los necesita, y
-- ningun otro rol de la aplicacion existe sin los tres que se eliminan. Reponerlos seria abrir
-- privilegios a todo el mundo; si algun dia hiciera falta, se otorgan a mano a un rol concreto.
\set ON_ERROR_STOP on
DO $$
DECLARE
    rol text;
BEGIN
    FOREACH rol IN ARRAY ARRAY['apex_api', 'apex_worker', 'apex_backup'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            EXECUTE format('DROP OWNED BY %I', rol);
        END IF;
        EXECUTE format('DROP ROLE IF EXISTS %I', rol);
    END LOOP;
END
$$;
