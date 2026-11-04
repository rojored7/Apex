#!/bin/sh
# Entrypoint del servicio dbsetup (S4B-W0-3; S4B-D72, D99): valida las tres contrasenas de rol y
# aplica roles.sql y grants.sql con el propietario (PGHOST, PGUSER, PGPASSWORD y PGDATABASE vienen
# del entorno del contenedor). Se invoca como `/bin/sh /opt/db/apply.sh`, asi que no necesita bit
# de ejecucion. Nunca activa la traza de ejecucion ni pasa contrasenas por -v: roles.sql las lee del
# entorno con \getenv. Los mensajes nombran la variable, jamas su valor.
set -eu

MINIMO=24

verificar() { # nombre de la variable
    valor="$(printenv "$1" || true)"
    if [ -z "$valor" ]; then
        echo "dbsetup: $1 esta vacia o no existe" >&2
        exit 2
    fi
    case "$valor" in
        *cambiar-esto*)
            echo "dbsetup: $1 conserva el valor de ejemplo (cambiar-esto)" >&2
            exit 2
            ;;
    esac
    if [ "${#valor}" -lt "$MINIMO" ]; then
        echo "dbsetup: $1 tiene menos de $MINIMO caracteres" >&2
        exit 2
    fi
    # La contrasena viaja dentro de una URL (DATABASE_URL): solo caracteres que no necesitan escape.
    case "$valor" in
        *[!A-Za-z0-9._~-]*)
            echo "dbsetup: $1 solo admite letras, numeros y . _ ~ - (genere una con: openssl rand -hex 24)" >&2
            exit 2
            ;;
    esac
}

distintas() { # dos nombres de variable
    if [ "$(printenv "$1")" = "$(printenv "$2")" ]; then
        echo "dbsetup: $1 y $2 no pueden ser iguales" >&2
        exit 2
    fi
}

for variable in APEX_API_DB_PASSWORD APEX_WORKER_DB_PASSWORD APEX_BACKUP_DB_PASSWORD; do
    verificar "$variable"
done
distintas APEX_API_DB_PASSWORD APEX_WORKER_DB_PASSWORD
distintas APEX_API_DB_PASSWORD APEX_BACKUP_DB_PASSWORD
distintas APEX_WORKER_DB_PASSWORD APEX_BACKUP_DB_PASSWORD

psql -X -q -v ON_ERROR_STOP=1 -f /opt/db/roles.sql
psql -X -q -v ON_ERROR_STOP=1 -f /opt/db/grants.sql

# El conteo sale del ARRAY `clasificadas` del DO final de grants.sql: la misma lista que valida (S4B-D201).
tablas="$(sed -n '/clasificadas constant text/,/\];/p' /opt/db/grants.sql | grep -o "'[a-z_0-9]*\.[a-z_0-9]*'" | wc -l | tr -d ' ')"
echo "roles aplicados; $tablas tablas clasificadas"
