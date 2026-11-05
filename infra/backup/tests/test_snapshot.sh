#!/usr/bin/env bash
# Pruebas de la instantánea raft de OpenBao en el respaldo (S5-B13 Rojo; S5-D8, S5-D72, L-2, H-1).
#
# Contrato que fija este archivo (el Verde lo implementa en run.sh, lib.sh y restore.sh):
#   - lib.sh: `snapshot_curl_config <archivo-token> <url>` imprime un archivo de configuración de
#     curl (`-K`) con `url`, `header = "X-Vault-Token: <token>"`, `fail`, `silent`, `show-error` y
#     `max-time`; rechaza (código 1, sin salida) un token vacío o con comillas, saltos de línea o
#     barras invertidas, y una URL que no sea `http://<host>[:<puerto>]/v1/sys/storage/raft/snapshot`.
#     El token entra por el archivo de configuración, NUNCA por el argv (L-2: `ps` lo vería).
#   - lib.sh: `manifest_json` admite un 8.º argumento opcional `name|size_bytes|sha256|verified`
#     (`true`|`false`) que agrega `"openbao_snapshot": {name, size_bytes, sha256, verified}`.
#   - run.sh: lee el token de /run/apex/openbao-backup/token; llama `curl -K <archivo en /tmp>`
#     (jamás `wget --header` ni `-H`/`--header` en el argv); cifra con `age` en tubería (el
#     archivo `<name>-openbao.snap.age` es lo único que toca el disco) y declara su `sha256`;
#     sin el token montado el paso se salta con un log `info` y el respaldo sigue; la retención
#     borra el `.snap.age` junto con su juego.
#   - restore.sh: `--with-openbao` restaura además la instantánea y avisa que exige desellar con
#     las llaves originales; sin la bandera no la toca.
# En el Rojo ninguno de esos puntos existe: las aserciones fallan por su contenido, no por el
# estado del archivo.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

RUN="$BACKUP_DIR_SRC/run.sh"
LIB="$BACKUP_DIR_SRC/lib.sh"
RESTORE="$BACKUP_DIR_SRC/restore.sh"

echo "test_snapshot"
for f in "$RUN" "$LIB" "$RESTORE"; do
  [ -f "$f" ] && _ok "existe $(basename "$f")" || _fail "existe $(basename "$f")"
done
[ -f "$RUN" ] && [ -f "$LIB" ] && [ -f "$RESTORE" ] || { finish; exit; }

run_txt="$(cat "$RUN")"
lib_txt="$(cat "$LIB")"
rst_txt="$(cat "$RESTORE")"
# Líneas de código (sin comentarios) para los patrones prohibidos.
run_code="$(grep -vE '^[[:space:]]*#' "$RUN" || true)"

# --- run.sh: el token nunca va por el argv (L-2) -------------------------------------------------
assert_contains "run.sh lee el token de /run/apex/openbao-backup/token" "$run_txt" "/run/apex/openbao-backup/token"
assert_contains "run.sh pide la ruta de la instantánea raft" "$run_txt" "sys/storage/raft/snapshot"
assert_contains "run.sh llama curl -K con un archivo de configuración" "$run_code" "curl -K"
assert_lacks "run.sh no usa wget" "$run_code" "wget"
if printf '%s\n' "$run_code" | grep -E 'curl[^|;&]*(-H|--header)([[:space:]=]|$)' > /dev/null; then
  _fail "run.sh pone una cabecera en el argv de curl"
else _ok "run.sh no pone cabeceras en el argv de curl"; fi
if printf '%s\n' "$run_code" | grep -E 'X-Vault-Token' > /dev/null; then
  _fail "run.sh nombra X-Vault-Token (debe salir de snapshot_curl_config en lib.sh)"
else _ok "run.sh no nombra X-Vault-Token"; fi
if printf '%s\n' "$run_code" | grep -E '(\$\(cat[^)]*openbao-backup|\$\(<[^)]*openbao-backup)' > /dev/null; then
  _fail "run.sh expande el token con \$(cat ...) (podría acabar en un argv)"
else _ok "run.sh no expande el token con \$(cat ...)"; fi
assert_contains "run.sh usa la configuración generada por snapshot_curl_config" "$run_code" "snapshot_curl_config"
assert_contains "run.sh deja la configuración en un temporal bajo /tmp" "$run_txt" 'TMPD'

# --- run.sh: cifrado, manifiesto, ausencia del token, retención ----------------------------------
assert_contains "run.sh nombra el archivo <name>-openbao.snap.age" "$run_txt" "-openbao.snap.age"
assert_contains "run.sh cifra la instantánea con age" "$run_code" "age"
assert_contains "run.sh pasa la instantánea de curl a age en tubería" "$(printf '%s\n' "$run_code" | grep -E 'curl' | head -3)" "|"
if printf '%s\n' "$run_code" | grep -E 'openbao\.snap([^.]|$)' > /dev/null; then
  _fail "run.sh escribe una instantánea sin cifrar (openbao.snap sin .age)"
else _ok "run.sh no deja la instantánea en claro"; fi
assert_contains "run.sh entrega la entrada al manifiesto (openbao_snapshot o su argumento)" "$run_txt" "openbao"
assert_contains "run.sh registra con log info que omite la instantánea sin token" "$run_txt" "instantánea de OpenBao omitida"
retencion="$(printf '%s\n' "$run_code" | grep -E 'rm -f' | tr '\n' ' ')"
assert_contains "la retención borra el .snap.age con su juego" "$retencion" "openbao.snap.age"
assert_lacks "run.sh no imprime el token" "$run_code" 'echo "$TOKEN'

# --- restore.sh --------------------------------------------------------------------------------
assert_contains "restore.sh admite --with-openbao" "$rst_txt" "--with-openbao"
assert_contains "restore.sh avisa que exige desellar con las llaves originales" "$rst_txt" "llaves originales"

# --- lib.sh: snapshot_curl_config -------------------------------------------------------------------
if ! printf '%s\n' "$lib_txt" | grep -q 'snapshot_curl_config'; then
  _fail "lib.sh define snapshot_curl_config"
else
  _ok "lib.sh define snapshot_curl_config"
  # shellcheck source=/dev/null
  source "$LIB"
  URL="http://openbao:8200/v1/sys/storage/raft/snapshot"
  TOK="$TMP_ROOT/token"
  printf 'hvs.token-de-prueba-0123456789' > "$TOK"
  cfg="$(snapshot_curl_config "$TOK" "$URL" 2> /dev/null || true)"
  assert_contains "la configuración lleva la cabecera X-Vault-Token" "$cfg" 'header = "X-Vault-Token: hvs.token-de-prueba-0123456789"'
  assert_contains "la configuración lleva la URL" "$cfg" "url = \"$URL\""
  assert_contains "la configuración falla ante HTTP >= 400" "$cfg" "fail"
  assert_contains "la configuración es silenciosa con errores visibles" "$cfg" "show-error"
  assert_contains "la configuración acota el tiempo" "$cfg" "max-time"
  # El salto de línea FINAL de un archivo de token es normal y se recorta; uno interior no.
  printf '%s\n' 'hvs.token-con-newline-final' > "$TOK"
  cfg2="$(snapshot_curl_config "$TOK" "$URL" 2> /dev/null || true)"
  assert_contains "el salto de línea final del token se recorta" "$cfg2" 'X-Vault-Token: hvs.token-con-newline-final"'
  printf 'abc"\nurl = "http://malo/"' > "$TOK"
  assert_fails "un token con comillas o saltos de línea se rechaza" snapshot_curl_config "$TOK" "$URL"
  printf 'a\\b' > "$TOK"
  assert_fails "un token con barra invertida se rechaza" snapshot_curl_config "$TOK" "$URL"
  : > "$TOK"
  assert_fails "un token vacío se rechaza" snapshot_curl_config "$TOK" "$URL"
  assert_fails "un token inexistente se rechaza" snapshot_curl_config "$TMP_ROOT/no-existe" "$URL"
  printf 'hvs.ok' > "$TOK"
  assert_fails "una URL de otra ruta se rechaza" snapshot_curl_config "$TOK" "http://openbao:8200/v1/sys/seal"
  assert_fails "una URL con otro esquema se rechaza" snapshot_curl_config "$TOK" "file:///etc/passwd"
  assert_fails "una URL con credenciales o espacios se rechaza" snapshot_curl_config "$TOK" "http://a@openbao:8200/v1/sys/storage/raft/snapshot x"
  malo="$(snapshot_curl_config "$TOK" "http://openbao:8200/v1/sys/seal" 2> /dev/null || true)"
  assert_eq "rechazar no deja salida (no se filtra el token)" "" "$malo"
fi

# --- lib.sh: revoke_curl_config (S5-D181: revocar la raiz efimera del init nuevo) -----------------------
if printf '%s\n' "$lib_txt" | grep -q 'revoke_curl_config'; then
  _ok "lib.sh define revoke_curl_config"
  # shellcheck source=/dev/null
  source "$LIB"
  RURL="http://openbao:8200/v1/auth/token/revoke-self"
  RTOK="$TMP_ROOT/rtoken"
  printf 'hvs.raiz-efimera-0123' > "$RTOK"
  rcfg="$(revoke_curl_config "$RTOK" "$RURL" 2> /dev/null || true)"
  assert_contains "revoke: la configuracion lleva la URL" "$rcfg" "url = \"$RURL\""
  assert_contains "revoke: la configuracion lleva el token como cabecera" "$rcfg" 'header = "X-Vault-Token: hvs.raiz-efimera-0123"'
  assert_contains "revoke: es un POST" "$rcfg" 'request = "POST"'
  assert_fails "revoke: una URL de snapshot se rechaza" revoke_curl_config "$RTOK" "http://openbao:8200/v1/sys/storage/raft/snapshot"
  assert_fails "revoke: otra ruta de auth se rechaza" revoke_curl_config "$RTOK" "http://openbao:8200/v1/auth/token/create"
  printf 'a"b' > "$RTOK"
  assert_fails "revoke: un token con comillas se rechaza" revoke_curl_config "$RTOK" "$RURL"
  assert_fails "snapshot_curl_config no acepta la ruta de revoke" snapshot_curl_config "$RTOK" "$RURL"
else
  _fail "lib.sh define revoke_curl_config"
fi

# --- run.sh: OpenBao sellado (S5-D180) -----------------------------------------------------------------
assert_contains "run.sh avisa con un mensaje especifico si OpenBao esta sellado" "$run_txt" "OpenBao sellado: desellar para reanudar snapshots y retención"

# --- lib.sh: manifest_json con openbao_snapshot ------------------------------------------------------
if printf '%s\n' "$lib_txt" | grep -q 'manifest_json'; then
  # shellcheck source=/dev/null
  source "$LIB"
  H64="$(printf 'a%.0s' $(seq 1 64))"; P64="$(printf 'b%.0s' $(seq 1 64))"; S64="$(printf 'c%.0s' $(seq 1 64))"
  n=apex-20261021-070005
  con="$(printf 'db|%s-db.dump.age|1234|%s|%s\n' "$n" "$H64" "$P64" \
    | manifest_json "$n" 2026-10-21T07:00:05Z apex ok 2026-10-21T07:02:05Z skipped "" "$n-openbao.snap.age|777|$S64|true" 2> /dev/null || true)"
  assert_contains "manifest_json con 8.º argumento agrega openbao_snapshot" "$con" '"openbao_snapshot"'
  assert_contains "openbao_snapshot lleva name" "$con" "\"name\": \"$n-openbao.snap.age\""
  assert_contains "openbao_snapshot lleva size_bytes entero" "$con" '"size_bytes": 777'
  assert_contains "openbao_snapshot lleva sha256" "$con" "\"sha256\": \"$S64\""
  assert_contains "openbao_snapshot lleva verified booleano" "$con" '"verified": true'
  sin="$(printf 'db|%s-db.dump.age|1234|%s|%s\n' "$n" "$H64" "$P64" \
    | manifest_json "$n" 2026-10-21T07:00:05Z apex ok 2026-10-21T07:02:05Z skipped "" 2> /dev/null || true)"
  assert_lacks "sin el 8.º argumento no hay openbao_snapshot" "$sin" "openbao_snapshot"
  falso="$(printf 'db|%s-db.dump.age|1234|%s|%s\n' "$n" "$H64" "$P64" \
    | manifest_json "$n" 2026-10-21T07:00:05Z apex ok 2026-10-21T07:02:05Z skipped "" "$n-openbao.snap.age|777|$S64|false" 2> /dev/null || true)"
  assert_contains "verified=false se escribe como false" "$falso" '"verified": false'
fi

finish
