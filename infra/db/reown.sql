-- Pasa la propiedad de la base de la aplicacion a `apex_owner` en un servidor EXISTENTE (S5-D146).
-- `REASSIGN OWNED BY apex TO apex_owner` NO sirve: `apex` (POSTGRES_USER) es el superusuario de
-- arranque y PostgreSQL rechaza reasignar sus objetos ("required by the database system"). Este
-- script cambia el dueño objeto por objeto y deja intactos los objetos de extension (btree_gist
-- sigue a nombre de `apex`) y los triggers (tgenabled no cambia).
-- Se corre UNA vez, como superusuario, con el stack PARADO (api, worker, web, backup), con un
-- respaldo verificado, y SOLO en la base de la aplicacion (POSTGRES_DB):
--   docker compose --env-file .env --env-file .env.ops -f infra/compose.yml run --rm --no-deps \
--     --entrypoint psql dbsetup -X -v ON_ERROR_STOP=1 -f /opt/db/reown.sql
-- Requiere que `apex_owner` exista (lo crea infra/db/initdb/10-apex-owner.sh; en un volumen viejo
-- se corre a mano, RUNBOOK §12). Idempotente: lo que ya es de `apex_owner` no se toca.
-- Vuelta atras: REASSIGN OWNED BY apex_owner TO <propietario actual>; (en la misma base).
\set ON_ERROR_STOP on
DO $$
DECLARE
    esquemas constant text[] := ARRAY['audit', 'auth', 'crypto', 'members', 'memberships',
                                      'payments', 'plans', 'settings', 'worker'];
    o record;
    cambios integer := 0;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'apex_owner') THEN
        RAISE EXCEPTION 'el rol apex_owner no existe: ejecute antes infra/db/initdb/10-apex-owner.sh (RUNBOOK 12)';
    END IF;
    IF NOT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
        RAISE EXCEPTION 'reown.sql debe correr como superusuario (corre como %)', current_user;
    END IF;

    IF (SELECT datdba::regrole::text FROM pg_database WHERE datname = current_database()) <> 'apex_owner' THEN
        EXECUTE format('ALTER DATABASE %I OWNER TO apex_owner', current_database());
        cambios := cambios + 1;
    END IF;

    -- Esquemas de la aplicacion (public sigue siendo de pg_database_owner).
    FOR o IN
        SELECT n.nspname FROM pg_namespace n
        WHERE n.nspname = ANY (esquemas) AND n.nspowner <> 'apex_owner'::regrole
        ORDER BY n.nspname
    LOOP
        EXECUTE format('ALTER SCHEMA %I OWNER TO apex_owner', o.nspname);
        cambios := cambios + 1;
    END LOOP;

    -- Tablas, vistas, secuencias propias y tipos compuestos de los esquemas de la aplicacion y
    -- public.alembic_version. Fuera: indices y TOAST (siguen a su tabla), secuencias de columnas
    -- serial o identity (siguen a su tabla) y todo lo que pertenece a una extension.
    FOR o IN
        SELECT c.oid, n.nspname, c.relname, c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE (n.nspname = ANY (esquemas) OR (n.nspname = 'public' AND c.relname = 'alembic_version'))
          AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S', 'c')
          AND c.relowner <> 'apex_owner'::regrole
          AND NOT EXISTS (
              SELECT 1 FROM pg_depend d
              WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid
                AND (d.deptype = 'e' OR (c.relkind = 'S' AND d.deptype IN ('a', 'i')))
          )
        ORDER BY (c.relkind = 'S'), n.nspname, c.relname
    LOOP
        EXECUTE format(
            'ALTER %s %I.%I OWNER TO apex_owner',
            CASE o.relkind
                WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' WHEN 'S' THEN 'SEQUENCE'
                WHEN 'f' THEN 'FOREIGN TABLE' WHEN 'c' THEN 'TYPE' ELSE 'TABLE'
            END,
            o.nspname, o.relname);
        cambios := cambios + 1;
    END LOOP;

    -- Funciones y procedimientos (incluidas las funciones de trigger).
    FOR o IN
        SELECT p.oid, p.prokind, p.oid::regprocedure::text AS firma
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = ANY (esquemas)
          AND p.proowner <> 'apex_owner'::regrole
          AND NOT EXISTS (
              SELECT 1 FROM pg_depend d
              WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e'
          )
        ORDER BY 3
    LOOP
        EXECUTE format(
            'ALTER %s %s OWNER TO apex_owner',
            CASE o.prokind WHEN 'p' THEN 'PROCEDURE' WHEN 'a' THEN 'AGGREGATE' ELSE 'FUNCTION' END,
            o.firma);
        cambios := cambios + 1;
    END LOOP;

    -- Tipos propios (enum, dominio, rango); los de fila y los arreglos siguen a su tabla.
    FOR o IN
        SELECT n.nspname, t.typname
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = ANY (esquemas)
          AND t.typtype IN ('e', 'd', 'r')
          AND t.typowner <> 'apex_owner'::regrole
          AND NOT EXISTS (
              SELECT 1 FROM pg_depend d
              WHERE d.classid = 'pg_type'::regclass AND d.objid = t.oid AND d.deptype = 'e'
          )
        ORDER BY 1, 2
    LOOP
        EXECUTE format('ALTER TYPE %I.%I OWNER TO apex_owner', o.nspname, o.typname);
        cambios := cambios + 1;
    END LOOP;

    RAISE NOTICE 'reown: % objetos pasados a apex_owner en %', cambios, current_database();
END
$$;
