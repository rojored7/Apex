#!/usr/bin/env bash
# Pruebas de infra/backup/manifest.schema.json y de manifest_json (S4B-W0-1; S4B-D80, D97).
# Valida con tests/validate_manifest.py (Python 3 del sistema o `uv run` del api); dentro de
# apex-backup:local no hay Python y las pruebas se saltan con aviso (corren en el host y en CI).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"
SCHEMA="$BACKUP_DIR_SRC/manifest.schema.json"
LIB="$BACKUP_DIR_SRC/lib.sh"
VALIDADOR="$TESTS_DIR/validate_manifest.py"

echo "test_manifest"
if [ ! -f "$SCHEMA" ] || [ ! -f "$LIB" ]; then
  [ -f "$SCHEMA" ] || _fail "existe $SCHEMA"
  [ -f "$LIB" ] || _fail "existe $LIB"
  finish
  exit
fi
if ! have_python; then
  echo "  (saltado: sin Python 3 ni uv; corre en el host y en la CI)"
  finish
  exit
fi
# shellcheck source=/dev/null
source "$LIB"

valida() { py "$VALIDADOR" "$SCHEMA" "$1"; }
H64="$(printf 'a%.0s' $(seq 1 64))"
P64="$(printf 'b%.0s' $(seq 1 64))"

crear() { # <nombre> <created_at> <verify> -> archivo
  local f="$TMP_ROOT/$1.json"
  printf 'db|%s-db.dump.age|1234|%s|%s\nuploads|%s-uploads.tar.age|99|%s|%s\n' "$1" "$H64" "$P64" "$1" "$H64" "$P64" \
    | manifest_json "$1" "$2" apex "$3" "" skipped "" > "$f"
  echo "$f"
}

assert_ok "manifiesto apex válido" valida "$(crear apex-20261021-070005 2026-10-21T07:00:05Z skipped)"
assert_ok "manifiesto pre-deploy válido" valida "$(crear pre-deploy-20261021-070005 2026-10-21T07:00:05Z ok)"
assert_ok "manifiesto pre-restore válido" valida "$(crear pre-restore-20261021-070005 2026-10-21T07:00:05Z failed)"
assert_fails "name otro-... inválido" valida "$(crear otro-20261021-070005 2026-10-21T07:00:05Z skipped)"
assert_fails "name sin fecha inválido" valida "$(crear apex-sin-fecha 2026-10-21T07:00:05Z skipped)"
assert_fails "created_at sin Z inválido" valida "$(crear apex-20261021-070005 2026-10-21T07:00:05 skipped)"
assert_fails "verify fuera de la lista inválido" valida "$(crear apex-20261021-070005 2026-10-21T07:00:05Z quizas)"

# A mano: faltan files, verify ausente, propiedad extra, hash corto.
base='"format_version": 1, "name": "apex-20261021-070005", "created_at": "2026-10-21T07:00:05Z", "database": "apex", "verify": "skipped", "upload": "skipped"'
archivo='{"kind": "db", "name": "apex-20261021-070005-db.dump.age", "size_bytes": 1, "sha256": "'"$H64"'", "plain_sha256": "'"$P64"'"}'
printf '{%s, "files": [%s]}' "$base" "$archivo" > "$TMP_ROOT/ok.json"
assert_ok "manifiesto mínimo escrito a mano válido" valida "$TMP_ROOT/ok.json"
printf '{%s}' "$base" > "$TMP_ROOT/sin-files.json"
assert_fails "faltan files" valida "$TMP_ROOT/sin-files.json"
printf '{%s, "files": []}' "$base" > "$TMP_ROOT/files-vacio.json"
assert_fails "files vacío" valida "$TMP_ROOT/files-vacio.json"
printf '{%s, "files": [%s], "extra": 1}' "$base" "$archivo" > "$TMP_ROOT/extra.json"
assert_fails "propiedad no prevista" valida "$TMP_ROOT/extra.json"
printf '{%s, "files": [{"kind": "db", "name": "x", "size_bytes": 1, "sha256": "abc", "plain_sha256": "%s"}]}' "$base" "$P64" > "$TMP_ROOT/hash.json"
assert_fails "sha256 corto" valida "$TMP_ROOT/hash.json"
printf '{%s, "files": [{"kind": "otro", "name": "x", "size_bytes": 1, "sha256": "%s", "plain_sha256": "%s"}]}' "$base" "$H64" "$P64" > "$TMP_ROOT/kind.json"
assert_fails "kind fuera de la lista" valida "$TMP_ROOT/kind.json"

finish
