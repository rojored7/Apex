#!/usr/bin/env bash
# restore.sh <manifiesto.json> -i <identidad age> -P <llave pública minisign> --confirm-database <nombre>
#            [--i-know-this-overwrites]
#            [--i-know-unsigned --sha256-db <hex> --sha256-uploads <hex>]
#
# Restaura un juego de respaldo (S4B-B3a, US-116; S4B-D42, D57, D97, D130 a D133). Orden fijo:
#   argumentos y confirmaciones -> firma (minisign) -> copia privada de los dos .age y sha256 de la
#   COPIA -> inspección del tar (age -d | tar -tv) -> guarda de filas -> extracción de uploads a un
#   directorio de trabajo -> run.sh --prefix pre-restore -> pg_restore -> copia de uploads.
#   Después de la verificación solo se usan las copias: el original puede cambiar sin efecto
#   (TOCTOU). Toda negativa antes de pg_restore sale con 2 sin tocar la base; un fallo en la
#   ejecución (respaldo previo, pg_restore, copia) sale con 1. pg_restore es todo o nada
#   (--single-transaction --exit-on-error) y sin permisos (--no-acl): después de restaurar hay que
#   correr dbsetup sobre la base para volver a dar los permisos de los roles.
# La base y la credencial salen del entorno (PGHOST, PGUSER, PGDATABASE y la contraseña del
# propietario, que llega por --env-file del contenedor): nunca por argumentos ni por la salida.
# APEX_RESTORE_DATA_ROOT (por defecto /data) recibe uploads/; APEX_RESTORE_TMP (por defecto /tmp,
# un tmpfs en el contenedor) es el directorio de trabajo. Imprime el ancla de auditoría
# (through_seq y through_hash) de la base restaurada.
set -euo pipefail
umask 077

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$HERE/lib.sh"

DATA_ROOT="${APEX_RESTORE_DATA_ROOT:-/data}"
TMP_BASE="${APEX_RESTORE_TMP:-/tmp}"
API_UID=10001 # uid del api (api/Dockerfile): dueño de los uploads restaurados

log() { printf 'restore.sh: %s\n' "$*"; }
rechazo() { printf 'restore.sh: ERROR %s\n' "$*" >&2; exit 2; }
fallo() { printf 'restore.sh: ERROR %s\n' "$*" >&2; exit 1; }

# La credencial de la base solo la necesitan psql, pg_restore y run.sh: age, tar y minisign no la heredan.
sin_credencial() { env -u PGPASSWORD "$@"; }

MANIFEST=""
IDENTITY=""
PUBKEY=""
CONFIRM=""
OVERWRITE=0
UNSIGNED=0
SHA_DB_ARG=""
SHA_UP_ARG=""
if [ "$#" -gt 0 ]; then MANIFEST="$1"; shift; fi
while [ "$#" -gt 0 ]; do
  case "$1" in
    -i) IDENTITY="${2:-}"; shift 2 || rechazo "-i necesita un valor" ;;
    -P) PUBKEY="${2:-}"; shift 2 || rechazo "-P necesita un valor" ;;
    --confirm-database) CONFIRM="${2:-}"; shift 2 || rechazo "--confirm-database necesita un valor" ;;
    --sha256-db) SHA_DB_ARG="${2:-}"; shift 2 || rechazo "--sha256-db necesita un valor" ;;
    --sha256-uploads) SHA_UP_ARG="${2:-}"; shift 2 || rechazo "--sha256-uploads necesita un valor" ;;
    --i-know-this-overwrites) OVERWRITE=1; shift ;;
    --i-know-unsigned) UNSIGNED=1; shift ;;
    *) rechazo "argumento desconocido" ;;
  esac
done

: "${PGHOST:?}" "${PGUSER:?}" "${PGDATABASE:?}"
[ -n "$MANIFEST" ] && [ -f "$MANIFEST" ] || rechazo "falta el manifiesto (primer argumento)"
[ -n "$IDENTITY" ] && [ -r "$IDENTITY" ] || rechazo "falta la identidad age (-i) o no se puede leer"
[ -n "$CONFIRM" ] || rechazo "falta --confirm-database <nombre de la base>"
[ "$CONFIRM" = "$PGDATABASE" ] || rechazo "--confirm-database no coincide con la base de destino"
if [ "$UNSIGNED" -eq 1 ]; then
  [[ "$SHA_DB_ARG" =~ ^[0-9a-f]{64}$ ]] && [[ "$SHA_UP_ARG" =~ ^[0-9a-f]{64}$ ]] \
    || rechazo "--i-know-unsigned exige --sha256-db y --sha256-uploads (64 hex cada uno)"
else
  [ -n "$PUBKEY" ] && [ -r "$PUBKEY" ] || rechazo "falta la llave pública de firma (-P); sin ella solo --i-know-unsigned"
fi

# Directorio de trabajo privado (0700): copias de los .age y extracción de uploads. Se borra al salir.
WORK="$(mktemp -d "$TMP_BASE/restore.XXXXXX")"
chmod 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT

# --- firma del manifiesto ---------------------------------------------------------------------
if [ "$UNSIGNED" -eq 1 ]; then
  log "AVISO: se restaura SIN verificar la firma; solo valen los sha256 que usted indicó"
else
  [ -f "$MANIFEST.minisig" ] || rechazo "falta la firma $(basename "$MANIFEST").minisig"
  sin_credencial minisign -V -m "$MANIFEST" -x "$MANIFEST.minisig" -p "$PUBKEY" > /dev/null 2>&1 \
    || rechazo "la firma del manifiesto no es válida"
  log "firma del manifiesto verificada"
fi

# --- archivos del manifiesto: copia privada y sha256 de la copia (M1: sin TOCTOU) -------------------
campo() { # <tipo> <campo>: valor de una cadena del renglón `"kind": "<tipo>"` del manifiesto
  grep -F "\"kind\": \"$1\"" "$MANIFEST" | head -1 \
    | sed -nE "s/.*\"$2\": \"([^\"]*)\".*/\1/p"
}
DB_NAME="$(campo db name)"
UP_NAME="$(campo uploads name)"
DB_SHA="$(campo db sha256)"
UP_SHA="$(campo uploads sha256)"
[[ "$DB_NAME" =~ ^[A-Za-z0-9-]+-db\.dump\.age$ ]] || rechazo "el manifiesto no nombra bien el archivo de la base"
[[ "$UP_NAME" =~ ^[A-Za-z0-9-]+-uploads\.tar\.age$ ]] || rechazo "el manifiesto no nombra bien el archivo de uploads"
if [ "$UNSIGNED" -eq 1 ]; then DB_SHA="$SHA_DB_ARG"; UP_SHA="$SHA_UP_ARG"; fi
[[ "$DB_SHA" =~ ^[0-9a-f]{64}$ ]] && [[ "$UP_SHA" =~ ^[0-9a-f]{64}$ ]] || rechazo "sha256 inválido en el manifiesto"
SET_DIR="$(cd "$(dirname "$MANIFEST")" && pwd)"
[ -f "$SET_DIR/$DB_NAME" ] && [ -f "$SET_DIR/$UP_NAME" ] || rechazo "faltan los archivos del juego junto al manifiesto"
DB_FILE="$WORK/db.dump.age"
UP_FILE="$WORK/uploads.tar.age"
cp "$SET_DIR/$DB_NAME" "$DB_FILE" && cp "$SET_DIR/$UP_NAME" "$UP_FILE" || fallo "no se pudieron copiar los archivos del juego"
[ "$(sha256sum < "$DB_FILE" | cut -d' ' -f1)" = "$DB_SHA" ] || rechazo "el sha256 del archivo de la base no coincide"
[ "$(sha256sum < "$UP_FILE" | cut -d' ' -f1)" = "$UP_SHA" ] || rechazo "el sha256 del archivo de uploads no coincide"
log "sha256 de los dos archivos verificado (sobre una copia privada)"

# --- inspección del tar antes de tocar nada -------------------------------------------------------
if ! sin_credencial age -d -i "$IDENTITY" "$UP_FILE" | tar -tvf - | valid_tar_listing; then
  rechazo "el tar de uploads trae entradas no permitidas (enlaces, rutas absolutas, '..', fuera de uploads/, demasiadas o demasiado grandes) o no se pudo leer"
fi
log "tar de uploads inspeccionado"

# --- guarda de filas ---------------------------------------------------------------------------------
# query_to_xml evita que el planificador exija que existan las tablas (una base recién creada no las
# tiene). auth.users excluye al usuario técnico de sistema (lo inserta la migración 0004).
CONSULTA="SELECT coalesce(sum(CASE WHEN to_regclass(split_part(t, '|', 1)) IS NULL THEN 0 ELSE (xpath('/row/c/text()', query_to_xml('SELECT count(*) AS c FROM ' || split_part(t, '|', 1) || split_part(t, '|', 2), false, true, '')))[1]::text::bigint END), 0) FROM unnest(ARRAY['members.members|', 'payments.payments|', 'audit.audit_log|', 'auth.users| WHERE id <> ''00000000-0000-0000-0000-000000000001''', 'crypto.crypto_keys|', 'settings.settings_sections|']) AS t"
FILAS="$(psql -X -At -v ON_ERROR_STOP=1 -c "$CONSULTA" 2> /dev/null)" || fallo "no se pudo consultar la base de destino"
FILAS="$(printf '%s' "$FILAS" | tr -d '[:space:]')"
[[ "$FILAS" =~ ^[0-9]+$ ]] || fallo "la consulta de la base de destino devolvió algo inesperado"
if [ "$FILAS" -gt 0 ] && [ "$OVERWRITE" -ne 1 ]; then
  rechazo "la base de destino tiene datos ($FILAS filas en socios, pagos, auditoría, usuarios, llaves y ajustes); use una base vacía o repita con --i-know-this-overwrites"
fi

# --- uploads a un directorio de trabajo ANTES de tocar la base (un tar malo no deja la base cambiada) ---
mkdir -m 700 "$WORK/extraido"
sin_credencial age -d -i "$IDENTITY" "$UP_FILE" \
  | tar -x -C "$WORK/extraido" --no-same-owner --no-same-permissions -f - \
  || rechazo "no se pudieron extraer los uploads; la base no se tocó"
[ -d "$WORK/extraido/uploads" ] || rechazo "el tar no trajo la carpeta uploads/; la base no se tocó"

# --- respaldo previo obligatorio (S4B-D97) -------------------------------------------------------------
log "tomando el respaldo previo (pre-restore)"
"$HERE/run.sh" --prefix pre-restore || fallo "no se pudo tomar el respaldo previo; la base no se tocó"

# --- restauración de la base: todo o nada, sin permisos (dbsetup los repone) -------------------------------
log "restaurando la base $PGDATABASE"
sin_credencial age -d -i "$IDENTITY" "$DB_FILE" \
  | pg_restore --clean --if-exists --no-owner --no-acl --single-transaction --exit-on-error -d "$PGDATABASE" \
  || fallo "pg_restore falló y se deshizo entero; el respaldo previo pre-restore sigue en la carpeta de respaldos"

# --- uploads: copia con dueño y permisos del api; no se retiran huérfanos de /data/uploads ------------------
mkdir -p "$DATA_ROOT/uploads"
cp -R "$WORK/extraido/uploads/." "$DATA_ROOT/uploads/" || fallo "no se pudieron copiar los uploads a $DATA_ROOT/uploads"
chmod -R u+rwX,go-rwx "$DATA_ROOT/uploads" || fallo "no se pudieron fijar los permisos de los uploads"
if [ "$(id -u)" = 0 ] || [ "$(id -u)" = "$API_UID" ]; then
  chown -R "$API_UID:$API_UID" "$DATA_ROOT/uploads" || fallo "no se pudo fijar el dueño de los uploads"
fi
log "uploads restaurados (los archivos que ya estaban en $DATA_ROOT/uploads y no vienen en el respaldo no se retiran)"

# --- ancla de auditoría para comparar con la cadena restaurada ----------------------------------------------------
ANCLA="$(psql -X -At -F ' ' -c "SELECT through_seq, through_hash FROM audit.verifications ORDER BY created_at DESC LIMIT 1" 2> /dev/null || true)"
if [ -n "$ANCLA" ]; then
  log "ancla de auditoría: through_seq=${ANCLA%% *} through_hash=${ANCLA##* }"
else
  log "ancla de auditoría: la base restaurada no trae verificaciones"
fi
log "listo; ahora corra dbsetup sobre esta base (los permisos no vienen en el volcado), restaure la KEK (restore-kek) y arranque la api"
