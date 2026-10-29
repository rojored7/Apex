#!/usr/bin/env bash
# Revisión estática de los scripts de infra/backup (S4B-W0-1; S4B-D19, D57, D68, D73, D78).
# Sin shellcheck (GPL, no disponible): `bash -n` y reglas por patrón.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

echo "test_scripts_static"
SCRIPTS=()
for f in "$BACKUP_DIR_SRC"/*.sh "$TESTS_DIR"/*.sh; do
  [ -f "$f" ] && SCRIPTS+=("$f")
done
RUN="$BACKUP_DIR_SRC/run.sh"
ENTRY="$BACKUP_DIR_SRC/entrypoint.sh"
for esperado in run.sh lib.sh entrypoint.sh healthcheck.sh; do
  [ -f "$BACKUP_DIR_SRC/$esperado" ] && _ok "existe $esperado" || _fail "existe $esperado"
done
[ -f "$RUN" ] || { finish; exit; }

for f in "${SCRIPTS[@]}"; do
  assert_ok "bash -n $(basename "$f")" bash -n "$f"
done

# Patrones prohibidos en cualquier script de producción (no en las pruebas).
PROD=()
for f in "$BACKUP_DIR_SRC"/*.sh; do PROD+=("$f"); done
prohibido() { # <descripcion> <regex>
  local desc="$1" re="$2" hallado=""
  for f in "${PROD[@]}"; do
    if grep -nE -- "$re" "$f" | grep -vE '^[0-9]+:[[:space:]]*#' > /dev/null; then hallado="$hallado $(basename "$f")"; fi
  done
  [ -z "$hallado" ] && _ok "sin $desc" || _fail "$desc en:$hallado"
}
prohibido "set -x" '(^|[[:space:];])set -[a-z]*x'
prohibido "down -v" 'down[[:space:]]+(-v|--volumes)'
prohibido "volume rm" 'volume[[:space:]]+rm'
prohibido "push" '(^|[[:space:];|&])git[[:space:]]+push|docker[[:space:]]+push'
prohibido "--force" '(^|[[:space:]])--force([[:space:]=]|$)'
prohibido "rclone sync" 'rclone[[:space:]]+sync'
prohibido "rclone delete" 'rclone[[:space:]]+delete'
prohibido "rclone purge" 'rclone[[:space:]]+purge'
prohibido "rclone deletefile" 'rclone[[:space:]]+deletefile'
prohibido "-vv" '(^|[[:space:]])-vv([[:space:]]|$)'
prohibido "--dump" '(^|[[:space:]])--dump([[:space:]=]|$)'
prohibido "echo de PGPASSWORD" '(echo|printf)[^#|]*(PGPASSWORD|RCLONE_CONFIG_APEX_SECRET_ACCESS_KEY|AGE-SECRET-KEY)'
prohibido "rclone con -v" 'rclone[^#|]*[[:space:]]-v([[:space:]]|$)'

# run.sh: modo estricto, umask y copyto sin borrado.
cuerpo="$(cat "$RUN")"
assert_contains "run.sh con set -euo pipefail" "$cuerpo" "set -euo pipefail"
assert_contains "run.sh con umask 077" "$cuerpo" "umask 077"
assert_contains "run.sh sube con rclone copyto" "$cuerpo" "rclone copyto"
assert_contains "run.sh con --log-level ERROR" "$cuerpo" "--log-level ERROR"
assert_contains "run.sh firma con minisign -S" "$cuerpo" "minisign -S"
assert_contains "run.sh limpia con trap" "$cuerpo" "trap "
assert_contains "run.sh acepta --prefix" "$cuerpo" "--prefix"
assert_contains "run.sh exige firma (salida 2)" "$cuerpo" "exit 2"
assert_contains "run.sh no toca latest.json con pre-*" "$cuerpo" "latest.json"
assert_contains "run.sh pasa PGPASSWORD solo a pg_dump (asignación prefijo)" "$cuerpo" 'PGPASSWORD="$_PGPW" pg_dump'
assert_lacks "run.sh no usa env PGPASSWORD (argv visible)" "$cuerpo" 'env PGPASSWORD='
assert_contains "run.sh usa --immutable" "$cuerpo" "--immutable"

# entrypoint.sh: inerte pero visible sin destinatario.
if [ -f "$ENTRY" ]; then
  assert_contains "entrypoint avisa 'backup deshabilitado'" "$(cat "$ENTRY")" "backup deshabilitado: falta BACKUP_AGE_RECIPIENT"
  assert_contains "entrypoint arranca supercronic" "$(cat "$ENTRY")" "supercronic"
fi

finish
