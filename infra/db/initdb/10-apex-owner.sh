#!/bin/bash
# Crea `apex_owner`, propietario NOSUPERUSER de la base de la aplicacion (S5-W0-4; S5-D6, D62, D89, D101; M-12).
# Es un script de `docker-entrypoint-initdb.d`: el entrypoint de postgres lo ejecuta UNA vez, al
# inicializar un volumen vacio, como el superusuario POSTGRES_USER por el socket local, con
# POSTGRES_USER, POSTGRES_DB y APEX_OWNER_DB_PASSWORD en el entorno. Sin bit de ejecucion el
# entrypoint lo carga con `source` (un `exit` o un `:?` abortan la inicializacion: falla cerrado);
# tambien se puede correr con `bash -s`. Solo corre con el volumen vacio: en un volumen viejo el rol
# no existe y `migrate` falla con `role apex_owner does not exist` (RUNBOOK 12, reown.sql).
# Idempotente: crea el rol solo si falta y SIEMPRE vuelve a fijar atributos y contrasena; la
# propiedad de la base se reasigna siempre. Sin traza de ejecucion y sin la contrasena en el texto
# del script: entra por el entorno, se lee con \getenv y se cita con :'owner_pw'; los SET de la
# sesion evitan que el servidor registre la sentencia o el error (como infra/db/roles.sql).
# Atributos: sin superusuario, sin crear bases ni roles, sin replicar ni saltar RLS. Como dueno de
# la base puede crear esquemas y extensiones "trusted" (btree_gist, S5-D101) y hacer `alembic
# upgrade head`; no puede SET session_replication_role ni COPY ... TO PROGRAM (42501).
# `public` pertenece a pg_database_owner: el dueno de la base conserva CREATE en ese esquema y
# grants.sql cierra el de PUBLIC y el de los tres roles de aplicacion (S5-D140).
set -eu

: "${POSTGRES_USER:?POSTGRES_USER vacio}"
: "${POSTGRES_DB:?POSTGRES_DB vacio}"
: "${APEX_OWNER_DB_PASSWORD:?APEX_OWNER_DB_PASSWORD vacio}"
# Un valor de ejemplo no es una contrasena (deploy.sh y dbsetup aplican la misma regla).
case "$APEX_OWNER_DB_PASSWORD" in
    *cambiar-esto*)
        echo "10-apex-owner.sh: APEX_OWNER_DB_PASSWORD conserva el valor de ejemplo (cambiar-esto)" >&2
        exit 1
        ;;
esac

# La contrasena viaja por la entorno hacia psql, nunca por la linea de comandos ni por -v: se lee
# con \getenv dentro de la sesion (igual que roles.sql).
psql -X -q -v ON_ERROR_STOP=1 -v db="$POSTGRES_DB" -U "$POSTGRES_USER" -d postgres <<'SQL'
SET log_min_error_statement = panic;
SET log_statement = 'none';
SET log_min_duration_statement = -1;
SET log_duration = off;
\getenv owner_pw APEX_OWNER_DB_PASSWORD

SELECT 'CREATE ROLE apex_owner LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'apex_owner')
\gexec

SELECT format('ALTER ROLE apex_owner WITH NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION NOBYPASSRLS LOGIN CONNECTION LIMIT 5 PASSWORD %L', :'owner_pw')
\gexec

SELECT format('ALTER DATABASE %I OWNER TO apex_owner', :'db')
\gexec
SQL
