#!/usr/bin/env bash
# Pruebas de infra/backup/lib.sh (S4B-W0-1; S4B-D15, D17, D68, D97). Funciones puras.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"
LIB="$BACKUP_DIR_SRC/lib.sh"

echo "test_lib"
if [ ! -f "$LIB" ]; then
  _fail "existe $LIB"
  finish
  exit
fi
# shellcheck source=/dev/null
source "$LIB"

# 2026-10-21 07:00:05 UTC
EPOCH=1792566005

# --- backup_name y valid_prefix (S4B-D97) ----------------------------------------------
assert_eq "backup_name apex" "apex-20261021-070005" "$(backup_name apex "$EPOCH")"
assert_eq "backup_name pre-deploy" "pre-deploy-20261021-070005" "$(backup_name pre-deploy "$EPOCH")"
assert_eq "backup_name pre-restore" "pre-restore-20261021-070005" "$(backup_name pre-restore "$EPOCH")"
assert_ok "valid_prefix acepta apex" valid_prefix apex
assert_ok "valid_prefix acepta pre-deploy" valid_prefix pre-deploy
assert_ok "valid_prefix acepta pre-restore" valid_prefix pre-restore
assert_fails "valid_prefix rechaza otro" valid_prefix otro
assert_fails "valid_prefix rechaza vacío" valid_prefix ""
assert_fails "valid_prefix rechaza apex-x" valid_prefix apex-x
assert_fails "valid_prefix rechaza ../apex" valid_prefix ../apex

# --- retention_to_delete (S4B-D17, S4B-D68, S4B-D97) -----------------------------------
DIA=86400
AHORA="$EPOCH"
# Veinte juegos apex-* con 1 a 20 días de antigüedad, dos pre-deploy y un pre-restore viejos.
entrada=""
for d in $(seq 1 20); do
  e=$((AHORA - d * DIA))
  entrada+="$e $(backup_name apex "$e")"$'\n'
done
entrada+="$((AHORA - 40 * DIA)) $(backup_name pre-deploy $((AHORA - 40 * DIA)))"$'\n'
entrada+="$((AHORA - 41 * DIA)) $(backup_name pre-deploy $((AHORA - 41 * DIA)))"$'\n'
entrada+="$((AHORA - 42 * DIA)) $(backup_name pre-restore $((AHORA - 42 * DIA)))"$'\n'
ULTIMO="$(backup_name apex $((AHORA - 1 * DIA)))"
borrar="$(printf '%s' "$entrada" | retention_to_delete 14 "$AHORA" "$ULTIMO")"
assert_eq "borra solo los apex de más de 14 días (seis: 15 a 20)" "6" "$(printf '%s\n' "$borrar" | grep -c '^apex-')"
assert_eq "no toca ningún pre-*" "0" "$(printf '%s\n' "$borrar" | grep -c '^pre-' || true)"
assert_lacks "no borra el de 14 días" "$borrar" "$(backup_name apex $((AHORA - 14 * DIA)))"
assert_contains "borra el de 15 días" "$borrar" "$(backup_name apex $((AHORA - 15 * DIA)))"
assert_lacks "no borra el último exitoso" "$borrar" "$ULTIMO"

# El último exitoso nunca se borra aunque sea viejo.
viejo="$(backup_name apex $((AHORA - 30 * DIA)))"
entrada2="$((AHORA - 30 * DIA)) $viejo"$'\n'"$((AHORA - 2 * DIA)) $(backup_name apex $((AHORA - 2 * DIA)))"$'\n'"$((AHORA - 1 * DIA)) $(backup_name apex $((AHORA - 1 * DIA)))"$'\n'
borrar2="$(printf '%s' "$entrada2" | retention_to_delete 14 "$AHORA" "$viejo")"
assert_eq "el último exitoso viejo se conserva" "" "$borrar2"

# Si quedaran menos de dos juegos válidos no borra nada.
entrada3="$((AHORA - 30 * DIA)) $(backup_name apex $((AHORA - 30 * DIA)))"$'\n'"$((AHORA - 1 * DIA)) $(backup_name apex $((AHORA - 1 * DIA)))"$'\n'
borrar3="$(printf '%s' "$entrada3" | retention_to_delete 14 "$AHORA" "$(backup_name apex $((AHORA - 1 * DIA)))")"
assert_eq "con menos de dos juegos válidos restantes no borra nada" "" "$borrar3"
assert_eq "entrada vacía no borra nada" "" "$(printf '' | retention_to_delete 14 "$AHORA" "$ULTIMO")"

# Días con cero a la izquierda no se leen como octal.
borrar4="$(printf '%s' "$entrada" | retention_to_delete 014 "$AHORA" "$ULTIMO")"
assert_eq "retention_to_delete 014 equivale a 14 días" "6" "$(printf '%s
' "$borrar4" | grep -c '^apex-')"

# --- sanitize_error (S4B-D68) ------------------------------------------------------------
sucio='Failed to copy: PUT https://bucket.s3.amazonaws.com/apex-1.age?X-Amz-Signature=abcdef0123456789&X-Amz-Credential=AKIAIOSFODNN7EXAMPLE/20261021 AccessKeyId=AKIAIOSFODNN7EXAMPLE secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'
limpio="$(printf '%s' "$sucio" | sanitize_error)"
assert_lacks "sanitize_error quita la URL" "$limpio" "https://"
assert_lacks "sanitize_error quita AKIA" "$limpio" "AKIAIOSFODNN7EXAMPLE"
assert_lacks "sanitize_error quita X-Amz-Signature" "$limpio" "abcdef0123456789"
assert_lacks "sanitize_error quita la clave secreta" "$limpio" "wJalrXUtnFEMI"
assert_contains "sanitize_error conserva el mensaje" "$limpio" "Failed to copy"
largo="$(printf 'ab cd %.0s' $(seq 1 100) | sanitize_error)"
assert_eq "sanitize_error recorta a 200 caracteres" "200" "${#largo}"

# --- validaciones de entrada (S4B-D68) -----------------------------------------------------
PUB="age1$(printf 'q%.0s' $(seq 1 58))"
assert_ok "valid_recipient acepta age1 + 58" valid_recipient "$PUB"
assert_fails "valid_recipient rechaza un plugin" valid_recipient "age1yubikey1qgyzuhr7hqy9ccrdw9yhrdz7z9mhcfkw4ds0nnvqdlvl7c3cd0nz2r3sj5a"
assert_fails "valid_recipient rechaza 57 caracteres" valid_recipient "age1$(printf 'q%.0s' $(seq 1 57))"
assert_fails "valid_recipient rechaza vacío" valid_recipient ""
assert_fails "valid_recipient rechaza mayúsculas" valid_recipient "age1$(printf 'Q%.0s' $(seq 1 58))"

assert_ok "valid_keep_days acepta 14" valid_keep_days 14
assert_ok "valid_keep_days acepta 3" valid_keep_days 3
assert_ok "valid_keep_days acepta 365" valid_keep_days 365
assert_fails "valid_keep_days rechaza 0" valid_keep_days 0
assert_fails "valid_keep_days rechaza -1" valid_keep_days -1
assert_fails "valid_keep_days rechaza abc" valid_keep_days abc
assert_fails "valid_keep_days rechaza 366" valid_keep_days 366
assert_fails "valid_keep_days rechaza 2" valid_keep_days 2
assert_fails "valid_keep_days rechaza vacío" valid_keep_days ""

assert_ok "valid_remote acepta apex:bucket/ruta" valid_remote "apex:bucket/ruta"
assert_fails "valid_remote rechaza otro:x" valid_remote "otro:x"
assert_fails "valid_remote rechaza apex:../x" valid_remote "apex:../x"
assert_fails "valid_remote rechaza 201 caracteres" valid_remote "apex:$(printf 'a%.0s' $(seq 1 201))"
assert_ok "valid_remote acepta 200 caracteres" valid_remote "apex:$(printf 'a%.0s' $(seq 1 200))"
assert_fails "valid_remote rechaza espacios" valid_remote "apex:bucket/mi ruta"

# --- manifest_json: salida con campos escapados -------------------------------------------
M="$(printf 'db|apex-20261021-070005-db.dump.age|1234|%s|%s\n' "$(printf 'a%.0s' $(seq 1 64))" "$(printf 'b%.0s' $(seq 1 64))" \
  | manifest_json apex-20261021-070005 2026-10-21T07:00:05Z apex skipped "" skipped 'mal "texto"')"
assert_contains "manifest_json lleva format_version" "$M" '"format_version": 1'
assert_contains "manifest_json escapa las comillas" "$M" 'mal \"texto\"'
assert_contains "manifest_json lleva el archivo" "$M" '"kind": "db"'

finish
