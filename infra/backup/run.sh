#!/bin/bash
# run.sh [--prefix apex|pre-deploy|pre-restore]
#
# Un respaldo completo (S4B-W0-1; S4B-D15, D57, D59, D68, D73, D97):
#   - pg_dump en formato custom, en tubería hacia age (sin volcado en claro en disco);
#   - tar de /data/uploads, en tubería hacia age;
#   - dos archivos cifrados del mismo juego y un manifiesto firmado con minisign;
#   - verificación de descifrado si hay identidad de verificación montada (S4B-D59);
#   - subida con `rclone copyto` si hay destino remoto (credencial sin borrado);
#   - retención solo tras un éxito verificado y solo sobre juegos apex-*.
# Con --prefix pre-deploy o pre-restore escribe <prefijo>-<ts>.json y su .minisig y NO toca
# latest.json. Códigos: 0 ok; 1 fallo en tiempo de ejecución o verificación/subida fallida;
# 2 configuración inválida. El log lleva nombres, tamaños y estados; nunca credenciales.
set -euo pipefail
umask 077

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$HERE/lib.sh"

log() { printf 'run.sh: %s\n' "$*"; }
fallo_config() { printf 'run.sh: ERROR %s\n' "$*" >&2; exit 2; }

PREFIX=apex
while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="${2:-}"; shift 2 ;;
    *) fallo_config "argumento desconocido" ;;
  esac
done
valid_prefix "$PREFIX" || fallo_config "prefijo inválido (apex, pre-deploy o pre-restore)"

DATA_ROOT=/data
OUT="$DATA_ROOT/backups"
SIGN_KEY=/run/apex/backup/sign.key
VERIFY_KEY=/run/apex/backup/verify.key

# --- validaciones de arranque ----------------------------------------------------------------
RECIPIENT="${BACKUP_AGE_RECIPIENT:-}"
VERIFY_RECIPIENT="${BACKUP_AGE_VERIFY_RECIPIENT:-}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
REMOTE="${BACKUP_RCLONE_REMOTE:-}"
[ -n "$RECIPIENT" ] || fallo_config "falta BACKUP_AGE_RECIPIENT"
valid_recipient "$RECIPIENT" || fallo_config "BACKUP_AGE_RECIPIENT inválido"
if [ -n "$VERIFY_RECIPIENT" ]; then
  valid_recipient "$VERIFY_RECIPIENT" || fallo_config "BACKUP_AGE_VERIFY_RECIPIENT inválido"
fi
valid_keep_days "$KEEP_DAYS" || fallo_config "BACKUP_KEEP_DAYS debe ser un entero de 3 a 365"
KEEP_DAYS=$((10#$KEEP_DAYS))
if [ -n "$REMOTE" ]; then
  valid_remote "$REMOTE" || fallo_config "BACKUP_RCLONE_REMOTE inválido"
fi
# La firma es obligatoria (S4B-D57): sin llave legible y no vacía no hay respaldo.
if [ ! -f "$SIGN_KEY" ] || [ ! -r "$SIGN_KEY" ] || [ ! -s "$SIGN_KEY" ]; then
  fallo_config "falta la llave de firma (BACKUP_SIGN_KEY_FILE montada en $SIGN_KEY)"
fi
: "${PGHOST:?}" "${PGUSER:?}" "${PGDATABASE:?}"
# S4B-D73: las credenciales salen del entorno general y entran solo al de la herramienta que las usa
# (asignación prefijo, sin `env` en el argv); age, tar y minisign no las heredan.
_PGPW="${PGPASSWORD:-}"; unset PGPASSWORD
_RC_TYPE="${RCLONE_CONFIG_APEX_TYPE:-s3}"; _RC_PROVIDER="${RCLONE_CONFIG_APEX_PROVIDER:-}"
_RC_ENDPOINT="${RCLONE_CONFIG_APEX_ENDPOINT:-}"; _RC_KEYID="${RCLONE_CONFIG_APEX_ACCESS_KEY_ID:-}"
_RC_SECRET="${RCLONE_CONFIG_APEX_SECRET_ACCESS_KEY:-}"
unset RCLONE_CONFIG_APEX_TYPE RCLONE_CONFIG_APEX_PROVIDER RCLONE_CONFIG_APEX_ENDPOINT RCLONE_CONFIG_APEX_ACCESS_KEY_ID RCLONE_CONFIG_APEX_SECRET_ACCESS_KEY
rclone_apex() {
  RCLONE_CONFIG_APEX_TYPE="$_RC_TYPE" RCLONE_CONFIG_APEX_PROVIDER="$_RC_PROVIDER" RCLONE_CONFIG_APEX_ENDPOINT="$_RC_ENDPOINT"     RCLONE_CONFIG_APEX_ACCESS_KEY_ID="$_RC_KEYID" RCLONE_CONFIG_APEX_SECRET_ACCESS_KEY="$_RC_SECRET"     rclone copyto --immutable --log-level ERROR "$@"
}

RECIPIENTS=(-r "$RECIPIENT")
[ -z "$VERIFY_RECIPIENT" ] || [ "$VERIFY_RECIPIENT" = "$RECIPIENT" ] || RECIPIENTS+=(-r "$VERIFY_RECIPIENT")

# --- candado, temporales y limpieza ----------------------------------------------------------
mkdir -p "$OUT"
exec 9> "$OUT/.run.lock"
flock -n 9 || { log "ERROR otra corrida de respaldo está en curso"; exit 1; }
TMPD="$(mktemp -d /tmp/backup.XXXXXX)"
cleanup() {
  rm -rf "$TMPD"
  rm -f "$OUT"/*.partial "$OUT"/latest.json.tmp "$OUT"/latest.json.minisig.tmp 2> /dev/null || true
}
trap cleanup EXIT

EPOCH="$(date -u +%s)"
NAME="$(backup_name "$PREFIX" "$EPOCH")"
CREATED_AT="$(date -u -d "@$EPOCH" +%Y-%m-%dT%H:%M:%SZ)"
DB_FILE="$NAME-db.dump.age"
UP_FILE="$NAME-uploads.tar.age"
[ ! -e "$OUT/$DB_FILE" ] && [ ! -e "$OUT/$UP_FILE" ] || { log "ERROR ya existe un juego $NAME"; exit 1; }
log "inicio $NAME"

# hash_stream <archivo de salida del hash> -> deja una FIFO lista en $TMPD/<nombre>.fifo
# Las dos tuberías calculan el sha256 del texto en claro con una FIFO (sin sustitución de
# procesos, para poder esperar al hash).
dump_a_age() { # <fifo> <destino parcial>
  PGPASSWORD="$_PGPW" pg_dump --format=custom --no-owner -h "$PGHOST" -U "$PGUSER" "$PGDATABASE" \
    | tee "$1" | age "${RECIPIENTS[@]}" -o "$2"
}
tar_a_age() { # <fifo> <destino parcial>
  tar -C "$DATA_ROOT" -cf - uploads | tee "$1" | age "${RECIPIENTS[@]}" -o "$2"
}

cifrar() { # <tipo db|uploads> <archivo final>
  local tipo="$1" final="$2" fifo="$TMPD/$1.fifo" hashf="$TMPD/$1.plain.sha" spid rc=0
  mkfifo "$fifo"
  sha256sum < "$fifo" | cut -d' ' -f1 > "$hashf" &
  spid=$!
  if [ "$tipo" = db ]; then dump_a_age "$fifo" "$OUT/$final.partial" || rc=$?; else tar_a_age "$fifo" "$OUT/$final.partial" || rc=$?; fi
  wait "$spid" || rc=$?
  if [ "$rc" -ne 0 ]; then
    log "ERROR falló el cifrado de $tipo (código $rc)"
    rm -f "$OUT/$DB_FILE" "$OUT/$UP_FILE"
    exit 1
  fi
  mv "$OUT/$final.partial" "$OUT/$final"
  chmod 640 "$OUT/$final"
}

cifrar db "$DB_FILE"
cifrar uploads "$UP_FILE"

sha_de() { sha256sum "$1" | cut -d' ' -f1; }
tam_de() { stat -c %s "$1"; }
DB_SHA="$(sha_de "$OUT/$DB_FILE")"; DB_SIZE="$(tam_de "$OUT/$DB_FILE")"; DB_PLAIN="$(cat "$TMPD/db.plain.sha")"
UP_SHA="$(sha_de "$OUT/$UP_FILE")"; UP_SIZE="$(tam_de "$OUT/$UP_FILE")"; UP_PLAIN="$(cat "$TMPD/uploads.plain.sha")"
log "db $DB_FILE $DB_SIZE bytes; uploads $UP_FILE $UP_SIZE bytes"

# --- verificación de descifrado (S4B-D59) -------------------------------------------------------
VERIFY=skipped
VERIFIED_AT=""
if [ -f "$VERIFY_KEY" ] && [ -r "$VERIFY_KEY" ] && [ -s "$VERIFY_KEY" ]; then
  VERIFY=ok
  for par in "$DB_FILE:$DB_PLAIN" "$UP_FILE:$UP_PLAIN"; do
    arch="${par%%:*}"; esperado="${par##*:}"
    obtenido="$(age -d -i "$VERIFY_KEY" "$OUT/$arch" 2> /dev/null | sha256sum | cut -d' ' -f1 || true)"
    [ "$obtenido" = "$esperado" ] || VERIFY=failed
  done
  VERIFIED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  log "verificación de descifrado: $VERIFY"
fi

# --- subida (S4B-D68): solo copyto, credencial sin borrado -----------------------------------------
UPLOAD=skipped
UPLOAD_ERROR=""
if [ -n "$REMOTE" ]; then
  UPLOAD=ok
  for arch in "$DB_FILE" "$UP_FILE"; do
    if ! errtxt="$(rclone_apex "$OUT/$arch" "$REMOTE/$arch" 2>&1)"; then
      UPLOAD=failed
      UPLOAD_ERROR="$(printf '%s' "$errtxt" | sanitize_error)"
    fi
  done
  log "subida: $UPLOAD"
fi

# --- manifiesto firmado -----------------------------------------------------------------------------
if [ "$PREFIX" = apex ] && [ "$VERIFY" != failed ]; then
  # Un respaldo cuya verificación falló no reemplaza el puntero firmado al último juego bueno (M4).
  MANIFEST="$OUT/latest.json"
  TMP_MANIFEST="$OUT/latest.json.tmp"
  TMP_SIG="$OUT/latest.json.minisig.tmp"
else
  MANIFEST="$OUT/$NAME.json"
  TMP_MANIFEST="$OUT/$NAME.json.tmp"
  TMP_SIG="$OUT/$NAME.json.minisig.tmp"
fi
printf 'db|%s|%s|%s|%s\nuploads|%s|%s|%s|%s\n' \
  "$DB_FILE" "$DB_SIZE" "$DB_SHA" "$DB_PLAIN" "$UP_FILE" "$UP_SIZE" "$UP_SHA" "$UP_PLAIN" \
  | manifest_json "$NAME" "$CREATED_AT" "$PGDATABASE" "$VERIFY" "$VERIFIED_AT" "$UPLOAD" "$UPLOAD_ERROR" > "$TMP_MANIFEST"
minisign -S -s "$SIGN_KEY" -m "$TMP_MANIFEST" -x "$TMP_SIG" > /dev/null
chmod 640 "$TMP_MANIFEST" "$TMP_SIG"
mv "$TMP_MANIFEST" "$MANIFEST"
mv "$TMP_SIG" "$MANIFEST.minisig"
log "manifiesto $(basename "$MANIFEST") firmado"
if [ -n "$REMOTE" ] && [ "$UPLOAD" != failed ]; then
  # El manifiesto y su firma se suben después (llevan el estado de la subida); un fallo aquí solo se
  # registra, sin alterar el manifiesto ya firmado. --immutable no aplica a latest.json: se sube con nombre propio.
  for m in "$MANIFEST" "$MANIFEST.minisig"; do
    if ! rclone_apex "$m" "$REMOTE/$NAME.$(basename "$m" | sed 's/^[^.]*.//')" > /dev/null 2>&1; then
      log "aviso: no se pudo subir $(basename "$m") al remoto"
    fi
  done
fi

# --- retención: solo tras éxito verificado y solo juegos apex-* -------------------------------------
if [ "$PREFIX" = apex ] && [ "$VERIFY" != failed ] && [ "$UPLOAD" != failed ] \
  && [ -f "$OUT/$DB_FILE" ] && [ -f "$OUT/$UP_FILE" ] \
  && [ "$(sha_de "$OUT/$DB_FILE")" = "$DB_SHA" ] && [ "$(sha_de "$OUT/$UP_FILE")" = "$UP_SHA" ]; then
  lista=""
  for f in "$OUT"/apex-*-db.dump.age; do
    [ -e "$f" ] || continue
    set_name="$(basename "$f" -db.dump.age)"
    [[ "$set_name" =~ ^apex-[0-9]{8}-[0-9]{6}$ ]] || continue
    [ -f "$OUT/$set_name-uploads.tar.age" ] || continue
    ts="${set_name#apex-}"
    fecha="${ts:0:4}-${ts:4:2}-${ts:6:2} ${ts:9:2}:${ts:11:2}:${ts:13:2}"
    e="$(date -u -d "$fecha" +%s 2> /dev/null || true)"
    [ -n "$e" ] || continue
    lista+="$e $set_name"$'\n'
  done
  while read -r viejo; do
    [ -n "$viejo" ] || continue
    rm -f "$OUT/$viejo-db.dump.age" "$OUT/$viejo-uploads.tar.age"
    log "retención: borrado el juego $viejo"
  done < <(printf '%s' "$lista" | retention_to_delete "$KEEP_DAYS" "$EPOCH" "$NAME")
fi

if [ "$VERIFY" = failed ] || [ "$UPLOAD" = failed ]; then
  log "ERROR terminado con fallas (verify=$VERIFY upload=$UPLOAD)"
  exit 1
fi
log "listo $NAME"
