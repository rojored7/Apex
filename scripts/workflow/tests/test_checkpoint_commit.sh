#!/usr/bin/env bash
# Pruebas de checkpoint-commit.sh (US-008, T3).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
GATE="$WORKFLOW_DIR/slice-gate.sh"
CHECKPOINT="$WORKFLOW_DIR/checkpoint-commit.sh"

echo "test_checkpoint_commit"
REPO="$(mk_repo)"
cd "$REPO"
use_stubs
stub_tool uv 0
stub_git_wrapper

assert_exit 0 "-h sale con 0" bash "$CHECKPOINT" -h
assert_exit 2 "sin mensaje sale con 2" bash "$CHECKPOINT"

# En main falla y no crea commit, incluso con sello.
"$REAL_GIT" switch -q main
bash "$GATE" core/config tests/core/test_config.py > /dev/null
PREV="$(head_of "$REPO")"
assert_nonzero "en main falla" bash "$CHECKPOINT" "control"
assert_no_new_commit "$REPO" "$PREV" "en main"
"$REAL_GIT" switch -q feat/x
rm -f "$REPO/.git/apex/slice-gate.ok"

# Sin sello falla.
PREV="$(head_of "$REPO")"
assert_nonzero "sin sello falla" bash "$CHECKPOINT" "sin sello"
assert_no_new_commit "$REPO" "$PREV" "sin sello"

# Sello de otro estado del árbol: el gate pasó, luego cambió un archivo.
bash "$GATE" core/config tests/core/test_config.py > /dev/null
printf 'VALOR = 2\n' > "$REPO/api/src/app/core/config.py"
assert_nonzero "sello de otro estado falla" bash "$CHECKPOINT" "cambio posterior"
assert_no_new_commit "$REPO" "$PREV" "sello viejo"

# Un archivo nuevo sin seguimiento después del gate también invalida el sello.
bash "$GATE" core/config tests/core/test_config.py > /dev/null
printf 'NUEVO = 1\n' > "$REPO/api/src/app/core/nuevo.py"
assert_nonzero "archivo nuevo tras el gate falla" bash "$CHECKPOINT" "archivo nuevo"
assert_no_new_commit "$REPO" "$PREV" "archivo nuevo"

# Sello vigente: crea el commit, no hace push y borra el sello.
bash "$GATE" core/config tests/core/test_config.py > /dev/null
clear_log
assert_exit 0 "con sello vigente crea el commit" bash "$CHECKPOINT" "S0-B1: US-011, US-013"
ULTIMO="$("$REAL_GIT" log -1 --pretty=%s)"
if [ "$ULTIMO" = "chore(checkpoint): S0-B1: US-011, US-013" ]; then _ok "mensaje chore(checkpoint)"; else _fail "mensaje inesperado: $ULTIMO"; fi
assert_log_lacks "git push"
assert_file_missing "$REPO/.git/apex/slice-gate.ok"
if [ -z "$("$REAL_GIT" status --porcelain)" ]; then _ok "árbol limpio tras el checkpoint"; else _fail "quedaron cambios sin confirmar"; fi

# Sin sello no se puede repetir.
assert_nonzero "segundo checkpoint sin gate falla" bash "$CHECKPOINT" "repetido"

cd "$REPO_ROOT"
finish
